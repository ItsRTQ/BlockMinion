"""R5 repair loop (v1 criterion 4), fault fixtures, and dedicated-server smoke."""
import json
import os
import re
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import build as build_mod, smoke as smoke_mod, workflow
from mod_orchestra.dispatch import dispatch, orchestrate
from mod_orchestra.faults import inject_fault, FAULTS
from mod_orchestra.provider import FakeProvider
from mod_orchestra.repair import open_repair_task, MAX_ATTEMPTS
from mod_orchestra.state import Store, StateError

GOOD = {"task": "t", "status": "DONE", "scope": "s", "changed_files": [], "checks_run": [{"command": "./gradlew build", "exit_code": 0}],
        "evidence": {"level": "BUILD_PASS", "pointer": "jar"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "none"}


def reply(obj):
    return "```handoff\n" + json.dumps(obj) + "\n```\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="R", mod_id="r_mod", package="com.x.r", idea="items: gem; blocks: ore")
        workflow.plan_project(self.store, "r_mod"); workflow.approve_spec(self.store, "r_mod"); workflow.generate_project(self.store, "r_mod")
        self.root = Path(proj["root"])

    def fake_gradle(self, exit_code):
        f = Path(self.tmp.name) / f"gradle{exit_code}.sh"
        f.write_text(f"#!/bin/sh\nmkdir -p build/libs; echo j > build/libs/r_mod-1.0.0.jar; echo 'error: cannot find symbol'; exit {exit_code}\n")
        f.chmod(f.stat().st_mode | stat.S_IEXEC); return f

    def tasks(self):
        return {t["id"]: t for t in self.store.tasks("r_mod")}

    def fake_server(self, lines, exit_code=0):
        f = Path(self.tmp.name) / "server.sh"
        body = "\n".join(f"echo '{l}'" for l in lines)
        f.write_text(f"#!/bin/sh\n{body}\nread cmd\necho \"got $cmd\"\nexit {exit_code}\n")
        f.chmod(f.stat().st_mode | stat.S_IEXEC); return f


@unittest.skipIf(os.name == "nt", "POSIX shell fixtures")
class RepairLoop(Base):
    def controller_build(self, exit_code):
        a = build_mod.request_build(self.store, "r_mod"); self.store.decide_approval(a["id"], True)
        with patch.object(build_mod, "_gradle_launcher", return_value=self.fake_gradle(exit_code)):
            return build_mod.build_project(self.store, "r_mod", a["id"])

    def test_failed_controller_build_opens_repair_task_for_debugger(self):
        out = self.controller_build(1)
        self.assertEqual(out["status"], "BUILD_FAILED")
        self.assertEqual(out["repair"]["task"], "r_mod:REPAIR:1")
        t = self.tasks()["r_mod:REPAIR:1"]
        self.assertEqual((t["role"], t["state"]), ("debugger", "READY"))
        self.assertIn("REPAIR_OPENED", [e["kind"] for e in self.store.events("r_mod")])

    def test_repair_packet_carries_diagnosis_and_log(self):
        self.controller_build(1)
        fake = FakeProvider(reply(GOOD | {"task": "r_mod:REPAIR:1"}))
        dispatch(self.store, "r_mod", task_id="r_mod:REPAIR:1", provider=fake)
        extra = fake.envelopes[0].extra_instructions
        self.assertIn("Build failure diagnosis", extra); self.assertIn("cannot find symbol", extra); self.assertIn("Repair contract", extra)

    def test_debugger_done_closes_episode_and_rebuild_is_possible(self):
        self.controller_build(1)
        out = dispatch(self.store, "r_mod", task_id="r_mod:REPAIR:1", provider=FakeProvider(reply(GOOD | {"task": "r_mod:REPAIR:1", "changed_files": ["build.gradle"]})))
        self.assertEqual(out["task_state"], "DONE")
        self.assertEqual(self.controller_build(0)["status"], "BUILD_PASS")
        self.assertEqual(self.store.project("r_mod")["status"], "BUILD_PASSED_GAME_UNTESTED")

    def test_worker_reporting_build_failed_opens_next_repair_until_exhausted(self):
        self.controller_build(1)
        for n in range(1, MAX_ATTEMPTS + 1):
            out = dispatch(self.store, "r_mod", task_id=f"r_mod:REPAIR:{n}",
                           provider=FakeProvider(reply(GOOD | {"task": f"r_mod:REPAIR:{n}", "status": "FAILED", "risks": ["still broken"],
                                                               "evidence": {"level": "BUILD_FAILED", "pointer": "log"}, "checks_run": [{"command": "./gradlew build", "exit_code": 1}]})))
            self.assertEqual(out["task_state"], "FAILED")
            if n < MAX_ATTEMPTS:
                self.assertEqual(out["repair"]["task"], f"r_mod:REPAIR:{n + 1}")
            else:
                self.assertTrue(out["repair"]["exhausted"])
        self.assertIn("REPAIR_EXHAUSTED", [e["kind"] for e in self.store.events("r_mod")])
        self.assertEqual(sum(1 for t in self.tasks() if ":REPAIR:" in t), MAX_ATTEMPTS)

    def test_orchestrate_runs_the_repair_without_a_human_and_stops_when_exhausted(self):
        self.controller_build(1)
        calls = {"n": 0}
        class FlakyDebugger(FakeProvider):
            def run(self, envelope, log_path):
                calls["n"] += 1
                ok = calls["n"] >= 2  # first repair attempt fails, second succeeds
                self.reply = reply(GOOD | {"task": envelope.task_id} if ok else
                                   GOOD | {"task": envelope.task_id, "status": "FAILED", "evidence": {"level": "BUILD_FAILED", "pointer": "x"},
                                           "checks_run": [{"command": "./gradlew build", "exit_code": 1}], "risks": ["nope"]})
                return super().run(envelope, log_path)
        out = orchestrate(self.store, "r_mod", max_runs=6, provider=FlakyDebugger(""))
        states = [r["task_state"] for r in out["runs"]]
        self.assertEqual(states, ["FAILED", "DONE"], states)  # stops right after the repair succeeds
        self.assertIn("confirm with the trusted build", out["stopped_because"])
        self.assertEqual(self.tasks()["r_mod:REPAIR:2"]["state"], "DONE")

    def test_game_task_is_never_dispatched_to_an_agent(self):
        # host run 5: a qa worker on GAME cost $2.11 and produced no acceptable evidence. GAME is now the user's task.
        from mod_orchestra.dispatch import pick_task, DISPATCHABLE_ROLES
        self.assertNotIn("user", DISPATCHABLE_ROLES); self.assertNotIn("controller", DISPATCHABLE_ROLES)
        self.controller_build(0)
        tasks = self.tasks(); self.assertEqual(tasks["r_mod:GAME"]["role"], "user"); self.assertEqual(tasks["r_mod:BUILD"]["state"], "DONE")
        with self.assertRaisesRegex(StateError, "No READY task"):
            pick_task(self.store, "r_mod", None)


@unittest.skipIf(os.name == "nt", "POSIX shell fixtures")
class Faults(Base):
    def test_each_fault_lands_and_keeps_manifest_valid(self):
        from mod_orchestra.fabric import validate_generated
        for name in FAULTS:
            out = inject_fault(self.store, "r_mod", name)
            self.assertTrue(out["file"]); self.assertEqual(validate_generated(self.root)["status"], "PASS", name)
        java = (self.root / "src/main/java/com/x/r/ModMain.java").read_text()
        self.assertNotIn("import net.minecraft.world.item.Item;", java); self.assertIn("new ResourceLocation(", java)
        loot = json.loads((self.root / "src/main/resources/data/r_mod/loot_table/blocks/ore.json").read_text())
        self.assertEqual(loot["pools"][0]["entries"][0]["name"], "r_mod:this_item_does_not_exist")
        self.assertEqual(self.store.project("r_mod")["status"], "SOURCE_GENERATED_UNVERIFIED")

    def test_unknown_fault_rejected(self):
        with self.assertRaisesRegex(StateError, "Unknown fault"):
            inject_fault(self.store, "r_mod", "nope")


@unittest.skipIf(os.name == "nt", "POSIX shell fixtures")
class ServerSmoke(Base):

    def build_pass(self):
        from mod_orchestra.evidence import record_evidence
        jar = self.root / "build/libs/r_mod-1.0.0.jar"; jar.parent.mkdir(parents=True, exist_ok=True); jar.write_bytes(b"j")
        record_evidence(self.store, "r_mod", "BUILD_PASS", actor="user", jar=jar)

    def test_mod_error_filter_ignores_the_data_fixer_notice(self):
        text = "\n".join(["[main/ERROR] (Minecraft) No data fixer registered for critter",
                          "[main/ERROR] (Minecraft) No data fixer registered for critter_test_stalker",
                          "[Server thread/ERROR] (Minecraft) Couldn't parse element minecraft:loot_table/critter:entities/x - Unknown registry key",
                          "[Server thread/INFO] (Minecraft) critter loaded"])
        hits = smoke_mod._mod_errors(text, "critter")
        self.assertEqual(len(hits), 1); self.assertIn("Couldn't parse element", hits[0])

    def test_smoke_requires_build_pass_and_approval(self):
        with self.assertRaisesRegex(StateError, "needs a BUILD_PASS"):
            smoke_mod.request_smoke(self.store, "r_mod")
        self.build_pass()
        a = smoke_mod.request_smoke(self.store, "r_mod")
        self.assertEqual(a["kind"], "run_dedicated_server_smoke"); self.assertIn("EULA", a["description"])
        with self.assertRaisesRegex(StateError, "approved server smoke"):
            smoke_mod.server_smoke(self.store, "r_mod", a["id"])

    def test_boot_pass_records_server_evidence_and_stops_server(self):
        self.build_pass()
        a = smoke_mod.request_smoke(self.store, "r_mod"); self.store.decide_approval(a["id"], True)
        srv = self.fake_server(["[main/INFO] (FabricLoader) Loading 3 mods:", "\t- r_mod 1.0.0", "[Server thread/INFO] (Minecraft) Done (1.2s)! For help, type \"help\""])
        with patch.object(smoke_mod, "_gradle_launcher", return_value=srv):
            out = smoke_mod.server_smoke(self.store, "r_mod", a["id"])
        self.assertEqual(out["status"], "SERVER_BOOT_PASS"); self.assertTrue(out["ready"]); self.assertTrue(out["mod_loaded"])
        self.assertIn("got stop", Path(out["log"]).read_text())
        self.assertIn("SERVER_BOOT_PASS", [e["level"] for e in self.store.evidence("r_mod")])
        self.assertTrue((self.root / "run" / "eula.txt").is_file())

    def test_mod_error_in_log_opens_repair(self):
        self.build_pass()
        a = smoke_mod.request_smoke(self.store, "r_mod"); self.store.decide_approval(a["id"], True)
        srv = self.fake_server(["\t- r_mod 1.0.0", "[Server thread/ERROR] (Minecraft) Failed to load loot table r_mod:blocks/ore: Unknown item r_mod:this_item_does_not_exist",
                                "[Server thread/INFO] (Minecraft) Done (1.2s)! For help, type \"help\""])
        with patch.object(smoke_mod, "_gradle_launcher", return_value=srv):
            out = smoke_mod.server_smoke(self.store, "r_mod", a["id"])
        self.assertEqual(out["status"], "SERVER_BOOT_FAILED"); self.assertEqual(len(out["mod_errors"]), 1)
        self.assertEqual(out["repair"]["task"], "r_mod:REPAIR:1")
        self.assertNotIn("SERVER_BOOT_PASS", [e["level"] for e in self.store.evidence("r_mod")])

    def test_smoke_properties_have_no_flat_preset(self):
        self.build_pass()
        a = smoke_mod.request_smoke(self.store, "r_mod"); self.store.decide_approval(a["id"], True)
        srv = self.fake_server(["\t- r_mod 1.0.0", "[Server thread/INFO] (Minecraft) Done (1.2s)! For help, type \"help\""])
        with patch.object(smoke_mod, "_gradle_launcher", return_value=srv):
            smoke_mod.server_smoke(self.store, "r_mod", a["id"])
        self.assertNotIn("level-type", (self.root / "run" / "server.properties").read_text())

    def test_run_client_reports_mod_loaded_and_next_steps(self):
        self.build_pass()
        srv = self.fake_server(["[main/INFO] (FabricLoader) Loading 56 mods:", "\t- r_mod 1.0.0"])
        with patch.object(smoke_mod, "_gradle_launcher", return_value=srv):
            out = smoke_mod.run_client(self.store, "r_mod")
        self.assertTrue(out["mod_loaded"]); self.assertEqual(out["mods_loaded"], 56)
        self.assertIn("craftctl evidence r_mod CLIENT_BOOT_PASS", out["next"][0])

    def test_server_crash_before_done_opens_repair(self):
        self.build_pass()
        a = smoke_mod.request_smoke(self.store, "r_mod"); self.store.decide_approval(a["id"], True)
        f = Path(self.tmp.name) / "crash.sh"; f.write_text("#!/bin/sh\necho '\t- r_mod 1.0.0'\necho 'java.lang.RuntimeException: boom in r_mod'\nexit 1\n"); f.chmod(0o755)
        with patch.object(smoke_mod, "_gradle_launcher", return_value=f):
            out = smoke_mod.server_smoke(self.store, "r_mod", a["id"])
        self.assertEqual(out["status"], "SERVER_BOOT_FAILED"); self.assertFalse(out["ready"]); self.assertEqual(out["repair"]["task"], "r_mod:REPAIR:1")


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(os.name == "nt", "POSIX shell fixtures")
class FullAutopilot(Base):
    """User-authorised gates: Autopilot goes from approved spec through generate, build and server smoke."""
    def test_policy_crosses_gates_until_the_client(self):
        from mod_orchestra.dispatch import autopilot_policy
        from mod_orchestra import smoke as smoke_mod
        self.store.set_setting("r_mod", "autopilot", {"approve_spec": True, "generate": True, "build": True, "server_smoke": True})
        self.assertTrue(autopilot_policy(self.store, "r_mod")["build"])
        # scaffold/content tasks are DONE by generate in setUp; BUILD/GAME are tasks a worker does not need here
        srv = self.fake_server(["\t- r_mod 1.0.0", "[Server thread/INFO] (Minecraft) Done (1.2s)! For help, type \"help\""])
        with patch.object(build_mod, "_gradle_launcher", return_value=self.fake_gradle(0)), patch.object(smoke_mod, "_gradle_launcher", return_value=srv):
            out = orchestrate(self.store, "r_mod", max_runs=4, provider=FakeProvider(reply(GOOD)))
        self.assertEqual([g["gate"] for g in out["gates"]], ["build", "server_smoke"])
        self.assertEqual(out["gates"][0]["status"], "BUILD_PASS"); self.assertEqual(out["gates"][1]["status"], "SERVER_BOOT_PASS")
        self.assertIn("ready for your eyes", out["stopped_because"])
        self.assertEqual(self.store.project("r_mod")["status"], "BUILD_PASSED_GAME_UNTESTED")

    def test_build_failure_under_autopilot_runs_the_repair_and_rebuilds(self):
        self.store.set_setting("r_mod", "autopilot", {"build": True})
        calls = {"n": 0}
        def launcher(root):
            calls["n"] += 1
            return self.fake_gradle(1 if calls["n"] == 1 else 0)
        with patch.object(build_mod, "_gradle_launcher", side_effect=launcher):
            out = orchestrate(self.store, "r_mod", max_runs=4, provider=FakeProvider(reply(GOOD | {"task": "r_mod:REPAIR:1"})))
        self.assertEqual([g["status"] for g in out["gates"]], ["BUILD_FAILED", "BUILD_PASS"])
        self.assertEqual([r["task"] for r in out["runs"]], ["r_mod:REPAIR:1"])
        self.assertIn("server smoke", out["stopped_because"])

    def test_questions_always_stop(self):
        from mod_orchestra import workflow as wf
        wf.new_project(self.store, name="Q", mod_id="q_mod", package="com.x.q", idea="a mod about something vague")
        self.store.set_setting("q_mod", "autopilot", {"approve_spec": True, "generate": True})
        h = {"task": "q_mod:SPEC", "status": "WAITING_USER", "scope": "s", "changed_files": [], "checks_run": [], "evidence": {"level": "NONE", "pointer": "-"},
             "risks": [], "unknowns": [], "needs_user": [], "next_agent": "planner", "spec": {"features": [{"kind": "item", "identifier": "thing", "label": "Thing"}]}, "questions": ["Which colour?"]}
        out = orchestrate(self.store, "q_mod", max_runs=3, provider=FakeProvider(reply(h)))
        self.assertIn("questions for you", out["stopped_because"]); self.assertEqual(out["gates"], [])
        self.assertEqual(self.store.project("q_mod")["spec_state"], "DRAFT")


class PlannerTasksNeverDispatched(unittest.TestCase):
    def test_old_role_rows_are_migrated_and_guarded(self):
        from mod_orchestra.dispatch import pick_task, _dispatchable_now
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            workflow.new_project(store, name="P", mod_id="p_mod", package="com.x.p", idea="items: gem")
            workflow.plan_project(store, "p_mod"); workflow.approve_spec(store, "p_mod")
            # simulate a pre-v6 row: SCAFFOLD as coder, leased by a worker
            with store.tx() as con:
                con.execute("UPDATE tasks SET role='coder', state='WAITING_USER' WHERE id='p_mod:SCAFFOLD'")
            # the id-based guard refuses regardless of role
            t = next(x for x in store.tasks("p_mod") if x["id"] == "p_mod:SCAFFOLD")
            self.assertFalse(_dispatchable_now(store, "p_mod", t))
            with self.assertRaisesRegex(StateError, "controller/user work"):
                pick_task(store, "p_mod", "p_mod:SCAFFOLD")
            # and the migration SQL repairs the row on a fresh open
            from mod_orchestra.state import MIGRATIONS
            sql = MIGRATIONS[-1][2]
            with store.tx() as con:
                con.executescript(sql)
            t = next(x for x in store.tasks("p_mod") if x["id"] == "p_mod:SCAFFOLD")
            self.assertEqual((t["role"], t["state"]), ("controller", "READY"))
