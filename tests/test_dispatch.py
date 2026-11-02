"""R2 dispatch: envelope, handoff validation, outcome mapping, provider failure, Claude Code command."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import dispatch as dmod, provider as pmod, workflow
from mod_orchestra.dispatch import dispatch
from mod_orchestra.provider import (ClaudeCodeProvider, FakeProvider, TaskEnvelope, extract_handoff, validate_handoff,
                                    _load_agent_definitions, RESOURCES)
from mod_orchestra.state import Store, StateError

GOOD = {"task": "t", "status": "DONE", "scope": "s", "changed_files": ["a"], "checks_run": [{"command": "./gradlew build", "exit_code": 0}],
        "evidence": {"level": "BUILD_PASS", "pointer": "build/libs/x.jar"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "qa"}


def reply(obj):
    return "work done\n```handoff\n" + json.dumps(obj) + "\n```\n"


class HandoffSchema(unittest.TestCase):
    def test_good_handoff_passes(self):
        self.assertEqual(validate_handoff(GOOD), [])

    def test_missing_fields_and_bad_status(self):
        self.assertTrue(any("missing field" in e for e in validate_handoff({"task": "t"})))
        self.assertTrue(any("status must be" in e for e in validate_handoff(GOOD | {"status": "SHIPPED"})))

    def test_worker_cannot_claim_game_evidence(self):
        for level in ("CLIENT_BOOT_PASS", "SERVER_BOOT_PASS", "CONTENT_VERIFIED", "VERIFIED"):
            errs = validate_handoff(GOOD | {"evidence": {"level": level}})
            self.assertTrue(any("not something a worker can claim" in e for e in errs), level)

    def test_build_pass_requires_gradle_exit_zero(self):
        errs = validate_handoff(GOOD | {"checks_run": [{"command": "./gradlew build", "exit_code": 1}]})
        self.assertTrue(any("BUILD_PASS requires" in e for e in errs))
        errs = validate_handoff(GOOD | {"checks_run": []})
        self.assertTrue(any("BUILD_PASS requires" in e for e in errs))

    def test_done_may_list_the_users_next_steps(self):
        # host run bOAtZ3sP-qm9: a coder finishes and names the trusted-build commands for the user. Legitimate.
        self.assertEqual(validate_handoff(GOOD | {"needs_user": ["craftctl request-build x", "craftctl build x"]}), [])

    def test_extract_takes_last_block_and_reports_bad_json(self):
        text = "```handoff\n{bad\n```\n" + reply(GOOD)
        obj, errs = extract_handoff(text)
        self.assertEqual(errs, []); self.assertEqual(obj["status"], "DONE")
        self.assertEqual(extract_handoff("```handoff\n{bad\n```")[1][0][:26], "handoff block is not valid")
        self.assertIn("no ```handoff block", extract_handoff("nothing")[1][0])


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        workflow.new_project(self.store, name="D", mod_id="d_mod", package="com.x.d", idea="items: gem")
        workflow.plan_project(self.store, "d_mod")
        # Agents receive ad-hoc work (ADD_*, MODEL, REPAIR, SPEC); SCAFFOLD/CONTENT/BUILD/GAME belong to the controller/user.
        self.store.add_task("d_mod", "d_mod:FEATURE", "coder", "ad-hoc coder work", after=["d_mod:SPEC"])

    def state(self, tid):
        return next(t for t in self.store.tasks("d_mod") if t["id"] == tid)

    def test_requires_approved_spec_except_for_the_spec_task(self):
        with self.assertRaisesRegex(StateError, "user-approved spec"):
            dispatch(self.store, "d_mod", task_id="d_mod:FEATURE", provider=FakeProvider(reply(GOOD)))
        out = dispatch(self.store, "d_mod", task_id="d_mod:SPEC", provider=FakeProvider(reply(GOOD | {"task": "d_mod:SPEC"})))
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("no `spec` proposal", out["error"])

    def test_done_handoff_completes_task_and_records_run(self):
        workflow.approve_spec(self.store, "d_mod")
        out = dispatch(self.store, "d_mod", provider=FakeProvider(reply(GOOD | {"task": "d_mod:FEATURE"})))
        self.assertEqual(out["task"], "d_mod:FEATURE"); self.assertEqual(out["task_state"], "DONE")
        self.assertEqual(self.state("d_mod:FEATURE")["state"], "DONE")
        run = self.store.runs("d_mod")[0]
        self.assertEqual((run["state"], run["provider"], run["handoff"]["status"]), ("DONE", "fake", "DONE"))
        self.assertTrue(Path(out["log"]).is_file())
        kinds = [e["kind"] for e in self.store.events("d_mod")]
        self.assertIn("RUN_STARTED", kinds); self.assertIn("RUN_FINISHED", kinds); self.assertIn("TASK_COMPLETED", kinds)

    def test_waiting_user_and_blocked_and_failed_map_to_task_states(self):
        workflow.approve_spec(self.store, "d_mod")
        cases = [("WAITING_USER", GOOD | {"status": "WAITING_USER", "needs_user": ["craftctl request-build d_mod"]}),
                 ("BLOCKED", GOOD | {"status": "BLOCKED", "unknowns": ["API unclear"]}),
                 ("FAILED", GOOD | {"status": "FAILED", "risks": ["could not compile"]})]
        for expected, h in cases:
            self.store.requeue("d_mod:FEATURE", "test") if self.state("d_mod:FEATURE")["state"] != "READY" else None
            out = dispatch(self.store, "d_mod", task_id="d_mod:FEATURE", provider=FakeProvider(reply(h)))
            self.assertEqual(out["task_state"], expected, expected)

    def test_invalid_handoff_fails_task_with_reason(self):
        workflow.approve_spec(self.store, "d_mod")
        out = dispatch(self.store, "d_mod", provider=FakeProvider(reply(GOOD | {"evidence": {"level": "CONTENT_VERIFIED"}})))
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("not something a worker can claim", out["error"])
        self.assertIn("not something a worker can claim", self.state("d_mod:FEATURE")["last_error"])
        self.assertEqual(self.store.requeue("d_mod:FEATURE", "retry")["state"], "READY")

    def test_provider_crash_releases_lease_and_records_failed_run(self):
        workflow.approve_spec(self.store, "d_mod")
        class Boom(FakeProvider):
            def run(self, envelope, log_path):
                raise RuntimeError("claude exploded")
        with self.assertRaisesRegex(RuntimeError, "exploded"):
            dispatch(self.store, "d_mod", provider=Boom(""))
        self.assertEqual(self.state("d_mod:FEATURE")["state"], "READY")
        self.assertEqual(self.store.runs("d_mod")[0]["state"], "FAILED")

    def test_envelope_carries_packet_and_workspace(self):
        workflow.approve_spec(self.store, "d_mod")
        fake = FakeProvider(reply(GOOD))
        dispatch(self.store, "d_mod", provider=fake)
        env = fake.envelopes[0]
        self.assertEqual(env.role, "coder"); self.assertIn("Bounded task handoff", env.packet)
        self.assertEqual(env.workspace, Path(self.store.project("d_mod")["root"]))

    def test_add_task_then_dispatch_it(self):
        workflow.approve_spec(self.store, "d_mod")
        self.store.add_task("d_mod", "d_mod:SAPPHIRE", "coder", "Add a sapphire item")
        out = dispatch(self.store, "d_mod", task_id="d_mod:SAPPHIRE", provider=FakeProvider(reply(GOOD | {"task": "d_mod:SAPPHIRE"})))
        self.assertEqual(out["task_state"], "DONE")


class ClaudeCodeCommand(unittest.TestCase):
    def test_agent_definitions_inline_skills_and_tools(self):
        agents = _load_agent_definitions()
        self.assertEqual(len(agents), 12)
        self.assertIn("# Preloaded skill: coder", agents["coder"]["prompt"])
        self.assertIn("# Preloaded skill: recipes", agents["coder"]["prompt"])
        self.assertIn("mcp__minecraft-orchestra__orchestra_generate_source", agents["coder"]["tools"])
        self.assertNotIn("Edit", agents["release"].get("tools", []))

    def test_packaged_resources_match_dot_claude(self):
        root = Path(__file__).resolve().parents[1]
        for rel in ["settings.json", "hooks/guard.py"] + [f"agents/{p.name}" for p in (root / ".claude/agents").glob("*.md")] \
                   + [f"skills/{p.parent.name}/SKILL.md" for p in (root / ".claude/skills").glob("*/SKILL.md")]:
            # Compare text, not bytes: core.autocrlf may leave one copy CRLF and the other LF in the working tree.
            self.assertEqual((root / ".claude" / rel).read_text(encoding="utf-8"), (RESOURCES / rel).read_text(encoding="utf-8"),
                             f"resources out of sync: {rel}")

    def test_command_line_and_materialized_files(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        ws = Path(tmp.name) / "ws"; ws.mkdir()
        captured = {}
        def fake_run(cmd, *, cwd, log, timeout, env, stdin_text=None):
            captured.update(cmd=cmd, cwd=cwd, env=env, timeout=timeout, stdin=stdin_text)
            for i, a in enumerate(cmd):
                if a == "--settings": captured["settings"] = json.loads(Path(cmd[i + 1]).read_text())
                if a == "--agents": captured["agents"] = json.loads(Path(cmd[i + 1]).read_text())
                if a == "--mcp-config": captured["mcp"] = json.loads(Path(cmd[i + 1]).read_text())
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("$ claude\n" + json.dumps({"result": reply(GOOD), "session_id": "s1", "total_cost_usd": 0.02, "num_turns": 3}))
            return {"pid": 1, "exit_code": 0, "killed": False, "timeout_s": timeout, "duration_s": 1.0, "cmd": cmd}
        with patch.object(pmod, "run_logged", fake_run):
            prov = ClaudeCodeProvider(binary="claude-fake")
            env = TaskEnvelope("d_mod", "d_mod:X", "coder", "t", ws, "# packet")
            res = prov.run(env, ws / ".mod-orchestra/runs/r.log")
        cmd = captured["cmd"]
        self.assertEqual(cmd[:2], ["claude-fake", "-p"]); self.assertIn("--agent", cmd); self.assertEqual(cmd[cmd.index("--agent") + 1], "coder")
        for flag in ("--agents", "--settings", "--mcp-config", "--strict-mcp-config", "--max-turns", "--output-format", "--permission-mode"):
            self.assertIn(flag, cmd)
        self.assertEqual(captured["cwd"], ws)
        self.assertNotIn("Output contract", " ".join(cmd), "prompt must travel via stdin, not the command line")
        self.assertIn("Output contract (mandatory)", captured["stdin"])
        deny = " ".join(captured["settings"]["permissions"]["deny"])
        self.assertIn("craftctl decide", deny); self.assertIn("craftctl dispatch", deny)
        self.assertIn("guard.py", captured["settings"]["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
        self.assertEqual(captured["mcp"]["mcpServers"]["minecraft-orchestra"]["args"], ["-m", "mod_orchestra.cli", "mcp"])
        self.assertIn("CRAFTCTL_HOME", captured["env"])
        self.assertEqual((res.session_id, res.cost_usd, res.turns, res.errors), ("s1", 0.02, 3, []))
        self.assertEqual(res.handoff["status"], "DONE")

    def test_parse_envelope_survives_header_after_output_and_noise_before(self):
        # Reproduces host run F3ooCkRVv_dq: JSON first, then the (buffered) command header holding the prompt,
        # whose example handoff block is NOT valid JSON. Also stderr noise before the envelope.
        from mod_orchestra.provider import parse_claude_json, HANDOFF_INSTRUCTIONS
        envelope = {"result": reply(GOOD), "session_id": "s", "total_cost_usd": 0.94, "num_turns": 7, "permission_denials": []}
        raw = "warning: something\n" + json.dumps(envelope) + "\n$ claude -p --agent coder " + HANDOFF_INSTRUCTIONS + "\n"
        out = parse_claude_json(raw)
        self.assertEqual(out["session_id"], "s")
        handoff, errs = extract_handoff(out["result"])
        self.assertEqual(errs, []); self.assertEqual(handoff["status"], "DONE")
        self.assertIsNone(parse_claude_json("no json here {not: json}"))

    def test_broker_header_precedes_child_output_and_stdin_is_fed(self):
        import os, stat
        if os.name == "nt":
            self.skipTest("POSIX shell script")
        from mod_orchestra.broker import run_logged
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        d = Path(tmp.name); sh = d / "echo.sh"; sh.write_text("#!/bin/sh\ncat\n"); sh.chmod(sh.stat().st_mode | stat.S_IEXEC)
        r = run_logged([str(sh), "x" * 500], cwd=d, log=d / "log", timeout=10, stdin_text="PROMPT-VIA-STDIN")
        lines = (d / "log").read_text().splitlines()
        self.assertTrue(lines[0].startswith("$ "), "header first"); self.assertLess(len(lines[0]), 300, "long args truncated")
        self.assertEqual(lines[1], "PROMPT-VIA-STDIN"); self.assertEqual(r["exit_code"], 0)

    def test_missing_binary_is_a_clear_error(self):
        with patch.object(pmod.shutil, "which", return_value=None), patch.dict("os.environ", {}, clear=False):
            import os; os.environ.pop("CRAFTCTL_CLAUDE_BIN", None)
            prov = ClaudeCodeProvider()
            with self.assertRaisesRegex(StateError, "not found on PATH"):
                prov.run(TaskEnvelope("p", "t", "coder", "t", Path("."), ""), Path(tempfile.mkdtemp()) / "l.log")


if __name__ == "__main__":
    unittest.main()


class Orchestrate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        workflow.new_project(self.store, name="O", mod_id="o_mod", package="com.x.o", idea="items: gem; blocks: ore")
        workflow.plan_project(self.store, "o_mod"); workflow.approve_spec(self.store, "o_mod")
        self.store.add_task("o_mod", "o_mod:WORK:1", "coder", "first ad-hoc task")
        self.store.add_task("o_mod", "o_mod:WORK:2", "coder", "second ad-hoc task", after=["o_mod:WORK:1"])

    def test_runs_until_no_ready_tasks(self):
        from mod_orchestra.dispatch import orchestrate
        class Echo(FakeProvider):  # every task reports DONE with its own id
            def run(self, envelope, log_path):
                self.reply = reply(GOOD | {"task": envelope.task_id})
                return super().run(envelope, log_path)
        out = orchestrate(self.store, "o_mod", max_runs=10, provider=Echo(""))
        # with no gates pre-authorised, Autopilot stops at the first gate it cannot cross and says which
        self.assertEqual(out["stopped_because"], "spec approved — generate the source"); self.assertEqual(out["gates"], [])
        self.assertEqual([r["task"] for r in out["runs"]], ["o_mod:WORK:1", "o_mod:WORK:2"])
        self.assertTrue(all(r["task_state"] == "DONE" for r in out["runs"]))

    def test_stops_when_user_is_needed(self):
        from mod_orchestra.dispatch import orchestrate
        out = orchestrate(self.store, "o_mod", max_runs=10, provider=FakeProvider(reply(GOOD | {"status": "WAITING_USER", "needs_user": ["craftctl request-build o_mod"]})))
        self.assertEqual(len(out["runs"]), 1)
        self.assertIn("WAITING_USER on o_mod:WORK:1: craftctl request-build o_mod", out["stopped_because"])

    def test_budgets_stop_the_loop(self):
        from mod_orchestra.dispatch import orchestrate
        class Echo(FakeProvider):
            def run(self, envelope, log_path):
                self.reply = reply(GOOD | {"task": envelope.task_id}); return super().run(envelope, log_path)
        out = orchestrate(self.store, "o_mod", max_runs=2, provider=Echo(""))
        self.assertEqual(out["stopped_because"], "max_runs (2) reached"); self.assertEqual(len(out["runs"]), 2)

    def test_stale_running_run_is_reconciled_after_restart(self):
        from mod_orchestra.dispatch import reconcile_stale_runs, STALE_RUN_AFTER
        run = self.store.create_run("o_mod", "o_mod:WORK:1", "coder", "claude-code")
        with self.store.tx() as con:
            con.execute("UPDATE runs SET created_at=? WHERE id=?", (__import__("time").time() - STALE_RUN_AFTER - 10, run["id"]))
        self.assertEqual(reconcile_stale_runs(self.store, "o_mod"), [run["id"]])
        self.assertEqual(self.store.runs("o_mod")[0]["state"], "FAILED")
        self.assertEqual(reconcile_stale_runs(self.store, "o_mod"), [])


class ManifestRevisions(unittest.TestCase):
    """A worker's reported changes become a manifest revision; unreported changes stay CHANGED."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="M", mod_id="m_mod", package="com.x.m", idea="items: gem")
        workflow.plan_project(self.store, "m_mod"); workflow.approve_spec(self.store, "m_mod"); workflow.generate_project(self.store, "m_mod")
        self.root = Path(proj["root"]); self.java = self.root / "src/main/java/com/x/m/ModMain.java"

    def test_reported_edit_is_accepted_and_build_can_be_requested(self):
        from mod_orchestra import build as build_mod
        from mod_orchestra.fabric import validate_generated
        self.java.write_text(self.java.read_text() + "\n// sapphire\n")
        new = self.root / "src/main/resources/assets/m_mod/models/item/sapphire.json"; new.parent.mkdir(parents=True, exist_ok=True); new.write_text("{}")
        self.assertEqual(validate_generated(self.root)["status"], "FAIL")
        self.store.add_task("m_mod", "m_mod:SAPPHIRE", "coder", "add sapphire")
        h = GOOD | {"task": "m_mod:SAPPHIRE", "status": "WAITING_USER", "needs_user": ["craftctl request-build m_mod"],
                    "changed_files": ["src/main/java/com/x/m/ModMain.java", "src/main/resources/assets/m_mod/models/item/sapphire.json", "does/not/exist.txt"],
                    "evidence": {"level": "STATIC", "pointer": "x"}}
        out = dispatch(self.store, "m_mod", task_id="m_mod:SAPPHIRE", provider=FakeProvider(reply(h)))
        self.assertEqual(out["task_state"], "WAITING_USER")
        acc = out["handoff"]["accepted_changes"]
        self.assertEqual(acc["accepted"], ["src/main/java/com/x/m/ModMain.java", "src/main/resources/assets/m_mod/models/item/sapphire.json"])
        self.assertEqual(acc["unchanged_or_missing"], ["does/not/exist.txt"])
        v = validate_generated(self.root)
        self.assertEqual((v["status"], v["revisions"]), ("PASS", 1))
        self.assertEqual(build_mod.request_build(self.store, "m_mod")["kind"], "execute_gradle_build")
        self.assertIn("CHANGES_ACCEPTED", [e["kind"] for e in self.store.events("m_mod")])

    def test_unreported_edit_stays_changed(self):
        from mod_orchestra.fabric import validate_generated
        self.java.write_text(self.java.read_text() + "\n// sneaky\n")
        self.store.add_task("m_mod", "m_mod:X", "coder", "x")
        h = GOOD | {"task": "m_mod:X", "changed_files": ["build.gradle"]}  # claims a file it did not touch, hides the real one
        dispatch(self.store, "m_mod", task_id="m_mod:X", provider=FakeProvider(reply(h)))
        v = validate_generated(self.root)
        self.assertEqual(v["status"], "FAIL"); self.assertIn("CHANGED: src/main/java/com/x/m/ModMain.java", v["problems"])

    def test_runtime_paths_are_never_accepted_and_old_entries_are_ignored(self):
        # host run 5 (E2): qa reported run/eula.txt and run/server.properties; the server rewrites them on every boot.
        from mod_orchestra.fabric import accept_changes, validate_generated
        import json as _json
        (self.root / "run").mkdir(); (self.root / "run/eula.txt").write_text("eula=true")
        out = accept_changes(self.root, run_id="r", actor="a", changed=["run/eula.txt", "build/libs/x.jar"])
        self.assertEqual(out["accepted"], []); self.assertEqual(out["unchanged_or_missing"], ["run/eula.txt", "build/libs/x.jar"])
        mf = self.root / ".mod-orchestra/generation-manifest.json"; m = _json.loads(mf.read_text())
        m.setdefault("revisions", []).append({"run": "old", "actor": "a", "at": 0, "files": {"run/server.properties": "0" * 64}})
        mf.write_text(_json.dumps(m))
        self.assertEqual(validate_generated(self.root)["status"], "PASS")

    def test_path_escape_in_changed_files_is_ignored(self):
        from mod_orchestra.fabric import accept_changes
        out = accept_changes(self.root, run_id="r", actor="a", changed=["../../etc/passwd", "/etc/passwd"])
        self.assertEqual(out["accepted"], [])

    def test_task_edits_are_the_union_of_its_runs(self):
        # host run kgk-WNuFojfD: an earlier run wrote the files, the final run only verified (changed_files: []).
        from mod_orchestra.fabric import validate_generated
        self.java.write_text(self.java.read_text() + "\n// sapphire\n")
        self.store.add_task("m_mod", "m_mod:S", "coder", "s")
        first = GOOD | {"task": "m_mod:S", "status": "WAITING_USER", "needs_user": ["x"], "changed_files": ["src/main/java/com/x/m/ModMain.java"],
                        "evidence": {"level": "STATIC", "pointer": "x"}}
        with patch("mod_orchestra.dispatch.accept_changes", side_effect=lambda *a, **k: {"accepted": [], "unchanged_or_missing": []}):
            dispatch(self.store, "m_mod", task_id="m_mod:S", provider=FakeProvider(reply(first)))  # simulate pre-fix: nothing accepted
        self.assertEqual(validate_generated(self.root)["status"], "FAIL")
        self.store.requeue("m_mod:S", "again")
        out = dispatch(self.store, "m_mod", task_id="m_mod:S", provider=FakeProvider(reply(GOOD | {"task": "m_mod:S", "changed_files": []})))
        self.assertEqual(out["task_state"], "DONE")
        self.assertEqual(out["handoff"]["accepted_changes"]["accepted"], ["src/main/java/com/x/m/ModMain.java"])
        self.assertEqual(validate_generated(self.root)["status"], "PASS")

    def test_user_can_accept_a_runs_changes_manually(self):
        from mod_orchestra.dispatch import accept_run_changes
        from mod_orchestra.fabric import validate_generated
        self.java.write_text(self.java.read_text() + "\n// manual\n")
        self.store.add_task("m_mod", "m_mod:U", "coder", "u")
        h = GOOD | {"task": "m_mod:U", "status": "FAILED", "risks": ["controller bug"], "changed_files": ["src/main/java/com/x/m/ModMain.java"]}
        out = dispatch(self.store, "m_mod", task_id="m_mod:U", provider=FakeProvider(reply(h)))
        self.assertEqual(out["task_state"], "FAILED"); self.assertEqual(validate_generated(self.root)["status"], "FAIL")
        acc = accept_run_changes(self.store, out["run"])
        self.assertEqual(acc["accepted"], ["src/main/java/com/x/m/ModMain.java"])
        self.assertEqual(validate_generated(self.root)["status"], "PASS")
        with self.assertRaisesRegex(StateError, "Run not found"):
            accept_run_changes(self.store, "nope")


class RebuildAfterRevision(unittest.TestCase):
    """Host run 4 (D7): after an agent revision the project must be rebuildable and prior evidence must not carry over."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="R", mod_id="r_mod", package="com.x.r", idea="items: gem")
        workflow.plan_project(self.store, "r_mod"); workflow.approve_spec(self.store, "r_mod"); workflow.generate_project(self.store, "r_mod")
        self.root = Path(proj["root"]); self.java = self.root / "src/main/java/com/x/r/ModMain.java"

    def test_revision_resets_status_and_allows_request_build_again(self):
        from mod_orchestra import build as build_mod
        from mod_orchestra.evidence import record_evidence
        jar = self.root / "build/libs/r_mod-1.0.0.jar"; jar.parent.mkdir(parents=True); jar.write_bytes(b"j")
        record_evidence(self.store, "r_mod", "BUILD_PASS", actor="user", jar=jar)
        for lvl in ("CLIENT_BOOT_PASS", "SERVER_BOOT_PASS", "CONTENT_VERIFIED"):
            record_evidence(self.store, "r_mod", lvl, actor="user")
        self.assertEqual(self.store.project("r_mod")["status"], "GAME_VERIFIED")
        # agent edits + accepted
        self.java.write_text(self.java.read_text() + "\n// sapphire\n")
        self.store.add_task("r_mod", "r_mod:S", "coder", "s")
        out = dispatch(self.store, "r_mod", task_id="r_mod:S", provider=FakeProvider(reply(GOOD | {"task": "r_mod:S", "changed_files": ["src/main/java/com/x/r/ModMain.java"]})))
        self.assertEqual(out["task_state"], "DONE")
        self.assertEqual(self.store.project("r_mod")["status"], "SOURCE_GENERATED_UNVERIFIED", "old evidence was for another manifest")
        self.assertIn("VERIFICATION_RESET", [e["kind"] for e in self.store.events("r_mod")])
        # rebuild path open again; game evidence on the new source needs a new BUILD_PASS first
        self.assertEqual(build_mod.request_build(self.store, "r_mod")["kind"], "execute_gradle_build")
        with self.assertRaisesRegex(StateError, "needs a prior BUILD_PASS on this exact source"):
            record_evidence(self.store, "r_mod", "CLIENT_BOOT_PASS", actor="user")
        record_evidence(self.store, "r_mod", "BUILD_PASS", actor="user", jar=jar)
        self.assertEqual(self.store.project("r_mod")["status"], "BUILD_PASSED_GAME_UNTESTED")


class StreamJsonParsing(unittest.TestCase):
    def test_result_event_wins_and_live_summary_reads_tool_calls(self):
        from mod_orchestra.provider import parse_claude_json, live_summary
        log = "\n".join([
            "$ claude -p --output-format stream-json",
            json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Reading the spec"}, {"type": "tool_use", "name": "Read", "input": {"file_path": "spec.json"}}]}}),
            json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "No such file"}]}}),
            json.dumps({"type": "result", "subtype": "success", "num_turns": 3, "total_cost_usd": 0.12, "session_id": "s1", "result": "```handoff\n{}\n```"}),
        ])
        env = parse_claude_json(log)
        self.assertEqual(env["type"], "result"); self.assertEqual(env["session_id"], "s1")
        live = live_summary(log)
        self.assertEqual(live[0], "… Reading the spec"); self.assertEqual(live[1], "→ Read spec.json"); self.assertTrue(live[2].startswith("   ✗ No such file"))
        self.assertIn("■ finished: success · 3 turns · $0.12", live[-1])

    def test_plain_json_envelope_still_parses(self):
        from mod_orchestra.provider import parse_claude_json
        self.assertEqual(parse_claude_json('header\n{"result": "x", "session_id": "a", "total_cost_usd": 0.1}\n')["session_id"], "a")
