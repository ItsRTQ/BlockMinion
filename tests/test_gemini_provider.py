"""GeminiCliProvider: a fake `gemini` binary records what it was asked and prints Gemini CLI stream-json."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from mod_orchestra.provider import GeminiCliProvider, TaskEnvelope, parse_gemini_stream, live_summary, _role_prompt

FAKE = r'''
import json, os, sys
from pathlib import Path
prompt = sys.stdin.read()
cfg = json.loads(Path(__file__).with_name("fake_gemini.config.json").read_text())   # the provider strips the env, so config travels by file
cap = Path(cfg["capture"])
settings = Path.cwd() / ".gemini" / "settings.json"
mcp = Path.cwd() / ".agents" / "mcp_config.json"; task = Path.cwd() / ".agents" / "craftctl_task.md"
cap.write_text(json.dumps({"argv": sys.argv[1:], "stdin": prompt, "cwd": str(Path.cwd()),
                           "settings": settings.read_text() if settings.is_file() else None,
                           "mcp_config": mcp.read_text() if mcp.is_file() else None, "task_file": task.read_text() if task.is_file() else None,
                           "env_home": os.environ.get("HOME") or os.environ.get("USERPROFILE")}))
mode = cfg.get("mode", "ok")
if mode == "agy_events":   # agy 1.5.x: {"event": ...} lines and one result event that carries the whole answer
    answer = "Proposed the spec.\n\n```handoff\n" + json.dumps(cfg.get("handoff", {})) + "\n```\n"
    print(json.dumps({"input_tokens": 4058, "output_tokens": 6277, "thinking_tokens": 3991}) + "}}")   # stray tail of a previous record
    print(json.dumps({"event": "result", "result": {"conversation_id": "conv-1", "status": "SUCCESS", "response": answer,
                                                    "duration_seconds": 95.1, "num_turns": 1, "usage": {"input_tokens": 18380, "output_tokens": 8215}}}))
    sys.exit(0)
if mode == "plain":   # agy < 1.1.8 style: no JSON events, just the answer
    print("Done.\n```handoff\n" + json.dumps(cfg.get("handoff", {})) + "\n```"); sys.exit(0)
print(json.dumps({"type": "init", "session_id": "sess-1", "model": "gemini-test"}))
print(json.dumps({"type": "tool_use", "tool_name": "run_shell_command", "tool_id": "t1", "parameters": {"command": "./gradlew build"}}))
print(json.dumps({"type": "tool_result", "tool_id": "t1", "status": "success", "output": "BUILD SUCCESSFUL"}))
if mode == "ok":
    task = cfg.get("handoff", {})
    print(json.dumps({"type": "message", "role": "assistant", "content": "Done. ", "delta": True}))
    print(json.dumps({"type": "message", "role": "assistant", "content": "```handoff\n" + json.dumps(task) + "\n```", "delta": True}))
    print(json.dumps({"type": "result", "status": "success", "stats": {"input_tokens": 10, "output_tokens": 5, "tool_calls": 1}}))
    sys.exit(0)
if mode == "turns":
    print(json.dumps({"type": "message", "role": "assistant", "content": "still working"}))
    print(json.dumps({"type": "error", "message": "turn limit"}))
    sys.exit(53)
'''


def make_fake(dirpath: Path, name: str = "gemini") -> Path:
    script = dirpath / "fake_gemini.py"
    if not script.exists():
        script.write_text(FAKE, encoding="utf8")
    if os.name == "nt":
        bat = dirpath / f"{name}.cmd"; bat.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf8"); return bat
    sh = dirpath / name; sh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf8")
    sh.chmod(sh.stat().st_mode | stat.S_IEXEC); return sh


HANDOFF = {"task": "p:CODE:x", "status": "DONE", "scope": "s", "changed_files": ["src/A.java"], "checks_run": [{"command": "./gradlew build", "exit_code": 0}],
           "evidence": {"level": "BUILD_PASS", "pointer": "build/libs"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "none"}


class TestParser(unittest.TestCase):
    def test_folds_messages_and_result(self):
        raw = "\n".join([json.dumps({"type": "init", "session_id": "s", "model": "m"}), "noise line",
                         json.dumps({"type": "message", "role": "user", "content": "ignored"}),
                         json.dumps({"type": "message", "role": "assistant", "content": "a", "delta": True}),
                         json.dumps({"type": "message", "role": "assistant", "content": [{"type": "text", "text": "b"}]}),
                         json.dumps({"type": "result", "status": "success", "stats": {"input_tokens": 1}})])
        rec = parse_gemini_stream(raw)
        self.assertEqual((rec["text"], rec["session_id"], rec["model"], rec["status"], rec["result_seen"]), ("ab", "s", "m", "success", True))
        self.assertEqual(rec["errors"], [])

    def test_partial_log_and_errors(self):
        rec = parse_gemini_stream(json.dumps({"type": "error", "message": "boom"}))
        self.assertEqual((rec["text"], rec["result_seen"], rec["errors"]), ("", False, ["boom"]))

    def test_agy_event_format_result_carries_the_answer(self):
        h = {"task": "p:CODE:x", "status": "DONE"}
        resp = "Done.\n```handoff\n" + json.dumps(h) + "\n```"
        raw = "\n".join(['{"input_tokens":1}}', json.dumps({"event": "result", "result": {"conversation_id": "c1", "status": "SUCCESS", "response": resp,
                                                                                   "num_turns": 2, "usage": {"input_tokens": 5, "output_tokens": 7}}})])
        rec = parse_gemini_stream(raw)
        self.assertEqual((rec["session_id"], rec["status"], rec["result_seen"], rec["text"]), ("c1", "success", True, resp))
        self.assertEqual(rec["stats"], {"input_tokens": 5, "output_tokens": 7, "turns": 2})
        self.assertEqual(live_summary(raw), ["■ finished: success · 2 turns · 5/7 tokens"])
        # the Claude Code result shape is untouched (its "result" is a string)
        self.assertEqual(live_summary(json.dumps({"type": "result", "subtype": "success", "num_turns": 3, "total_cost_usd": 0.5, "result": "x"})),
                         ["■ finished: success · 3 turns · $0.50"])

    def test_live_summary_reads_gemini_events(self):
        raw = "\n".join([json.dumps({"type": "tool_use", "tool_name": "write_file", "tool_id": "1", "parameters": {"file_path": "a.java"}}),
                         json.dumps({"type": "tool_result", "tool_id": "1", "status": "error", "error": {"message": "nope"}}),
                         json.dumps({"type": "message", "role": "assistant", "content": "hello"}),
                         json.dumps({"type": "result", "status": "success", "stats": {"input_tokens": 3, "output_tokens": 4}})])
        lines = live_summary(raw)
        self.assertEqual(lines, ["→ write_file a.java", "   ✗ nope", "… hello", "■ finished: success · 3/4 tokens"])

    def test_role_prompt_inlines_skill(self):
        text = _role_prompt("designer")
        self.assertIn("# You are the `designer` worker", text); self.assertIn("# Preloaded skill: blockbench", text)
        with self.assertRaises(Exception):
            _role_prompt("nope")


class TestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.ws = base / "ws"; self.ws.mkdir()
        (base / "bin").mkdir(); self.binary = make_fake(base / "bin")
        self.capture = base / "capture.json"
        self.cfg = base / "bin" / "fake_gemini.config.json"
        self.configure()
        self.log = base / "run.log"

    def configure(self, mode="ok"):
        self.cfg.write_text(json.dumps({"capture": str(self.capture), "handoff": HANDOFF, "mode": mode}))

    def envelope(self, role="coder"):
        return TaskEnvelope(project_id="p", task_id="p:CODE:x", role=role, title="t", workspace=self.ws, packet="PACKET-TEXT", extra_instructions="EXTRA-TEXT")

    def test_runs_headless_with_prompt_on_stdin_and_settings_in_workspace(self):
        prov = GeminiCliProvider(binary=str(self.binary), timeout=60)
        self.assertTrue(prov.available())
        res = prov.run(self.envelope(), self.log)
        self.assertEqual(res.exit_code, 0, res.raw_output); self.assertEqual(res.errors, [])
        self.assertEqual(res.handoff["status"], "DONE"); self.assertEqual(res.session_id, "sess-1"); self.assertEqual(res.turns, 1)
        cap = json.loads(self.capture.read_text())
        self.assertEqual(cap["argv"][:1], ["--prompt"]); self.assertIn("--output-format", cap["argv"]); self.assertIn("stream-json", cap["argv"])
        self.assertIn("--approval-mode", cap["argv"]); self.assertIn("yolo", cap["argv"]); self.assertIn("--skip-trust", cap["argv"])
        self.assertIn("# You are the `coder` worker", cap["stdin"]); self.assertIn("PACKET-TEXT", cap["stdin"]); self.assertIn("EXTRA-TEXT", cap["stdin"])
        self.assertIn("```handoff", cap["stdin"]); self.assertLess(cap["stdin"].index("# You are"), cap["stdin"].index("PACKET-TEXT"))
        self.assertEqual(Path(cap["cwd"]).resolve(), self.ws.resolve())
        settings = json.loads(cap["settings"])
        self.assertEqual(set(settings["mcpServers"]), {"minecraft-orchestra"}); self.assertEqual(settings["mcp"]["allowed"], ["minecraft-orchestra"])
        self.assertTrue(settings["mcpServers"]["minecraft-orchestra"]["trust"]); self.assertIn("CRAFTCTL_HOME", settings["mcpServers"]["minecraft-orchestra"]["env"])
        self.assertFalse((self.ws / ".gemini").exists(), "settings written for the run are removed afterwards")
        self.assertTrue(cap["env_home"])

    def test_designer_gets_blockbench_and_existing_settings_are_merged_and_restored(self):
        (self.ws / ".gemini").mkdir(); original = json.dumps({"theme": "dark", "mcpServers": {"mine": {"command": "x"}}})
        (self.ws / ".gemini/settings.json").write_text(original)
        GeminiCliProvider(binary=str(self.binary), timeout=60).run(self.envelope("designer"), self.log)
        settings = json.loads(json.loads(self.capture.read_text())["settings"])
        self.assertEqual(set(settings["mcpServers"]), {"mine", "minecraft-orchestra", "blockbench"})
        self.assertEqual(settings["mcp"]["allowed"], ["blockbench", "minecraft-orchestra"]); self.assertEqual(settings["theme"], "dark")
        self.assertEqual((self.ws / ".gemini/settings.json").read_text(), original)

    def test_turn_limit_exit_is_reported(self):
        self.configure("turns")
        res = GeminiCliProvider(binary=str(self.binary), timeout=60).run(self.envelope(), self.log)
        self.assertEqual(res.exit_code, 53); self.assertIsNone(res.handoff)
        self.assertTrue(any("turn limit exceeded" in e for e in res.errors)); self.assertTrue(any("gemini error: turn limit" in e for e in res.errors))
        self.assertTrue(any("no ```handoff block" in e for e in res.errors))

    def test_model_flag_and_missing_binary(self):
        os.environ["CRAFTCTL_GEMINI_MODEL"] = "gemini-x"; self.addCleanup(lambda: os.environ.pop("CRAFTCTL_GEMINI_MODEL", None))
        GeminiCliProvider(binary=str(self.binary), timeout=60).run(self.envelope(), self.log)
        argv = json.loads(self.capture.read_text())["argv"]; self.assertEqual(argv[argv.index("--model") + 1], "gemini-x")
        with self.assertRaises(Exception):
            GeminiCliProvider(binary="", timeout=60).run(self.envelope(), self.log)


class TestAntigravityRun(TestRun):
    """Same fake binary under the agy name: Antigravity flags, .agents/mcp_config.json, task file, plain-text fallback."""

    def setUp(self):
        super().setUp()
        self.binary = make_fake(Path(self.tmp.name) / "bin", "agy")

    def provider(self):
        from mod_orchestra.provider import AntigravityCliProvider
        return AntigravityCliProvider(binary=str(self.binary), timeout=60)

    def test_runs_headless_with_prompt_on_stdin_and_settings_in_workspace(self):
        res = self.provider().run(self.envelope(), self.log)
        self.assertEqual(res.exit_code, 0, res.raw_output); self.assertEqual(res.errors, []); self.assertEqual(res.handoff["status"], "DONE")
        cap = json.loads(self.capture.read_text())
        self.assertIn("--dangerously-skip-permissions", cap["argv"]); self.assertNotIn("--approval-mode", cap["argv"]); self.assertNotIn("--skip-trust", cap["argv"])
        self.assertEqual(cap["argv"][cap["argv"].index("--print-timeout") + 1], "60s")
        self.assertIn(".agents/craftctl_task.md", cap["argv"][1])
        self.assertIn("PACKET-TEXT", cap["stdin"]); self.assertEqual(cap["task_file"], cap["stdin"])
        mcp = json.loads(cap["mcp_config"]); self.assertEqual(set(mcp["mcpServers"]), {"minecraft-orchestra"})
        self.assertEqual(set(mcp["mcpServers"]["minecraft-orchestra"]), {"command", "args", "env"})   # no Gemini-only keys
        self.assertIsNone(cap["settings"])
        self.assertFalse((self.ws / ".agents").exists(), "task file and mcp config are removed afterwards")

    def test_designer_gets_blockbench_and_existing_settings_are_merged_and_restored(self):
        (self.ws / ".agents").mkdir(); original = json.dumps({"mcpServers": {"mine": {"command": "x"}}})
        (self.ws / ".agents/mcp_config.json").write_text(original)
        self.provider().run(self.envelope("designer"), self.log)
        mcp = json.loads(json.loads(self.capture.read_text())["mcp_config"])
        self.assertEqual(set(mcp["mcpServers"]), {"mine", "minecraft-orchestra", "blockbench"})
        self.assertEqual((self.ws / ".agents/mcp_config.json").read_text(), original)
        self.assertFalse((self.ws / ".agents/craftctl_task.md").exists())

    def test_turn_limit_exit_is_reported(self):
        self.configure("turns")
        res = self.provider().run(self.envelope(), self.log)
        self.assertEqual(res.exit_code, 53); self.assertIsNone(res.handoff); self.assertTrue(any("agy error: turn limit" in e for e in res.errors))

    def test_model_flag_and_missing_binary(self):
        with self.assertRaises(Exception):
            from mod_orchestra.provider import AntigravityCliProvider
            AntigravityCliProvider(binary="", timeout=60).run(self.envelope(), self.log)

    def test_agy_1_5_event_stream_yields_the_handoff(self):
        self.configure("agy_events")
        res = self.provider().run(self.envelope(), self.log)
        self.assertEqual(res.errors, []); self.assertEqual(res.handoff["status"], "DONE")
        self.assertEqual((res.session_id, res.turns), ("conv-1", 1))

    def test_plain_text_output_still_yields_the_handoff(self):
        self.configure("plain")
        res = self.provider().run(self.envelope(), self.log)
        self.assertEqual(res.handoff["status"], "DONE"); self.assertEqual(res.errors, [])


class TestSelection(unittest.TestCase):
    def test_provider_by_name(self):
        from mod_orchestra.dispatch import provider_by_name
        self.assertEqual(provider_by_name("gemini-cli").name, "gemini-cli"); self.assertEqual(provider_by_name("gemini").name, "gemini-cli")
        self.assertEqual(provider_by_name(None).name, "claude-code"); self.assertEqual(provider_by_name("fake").name, "fake")
        self.assertEqual(provider_by_name("agy").name, "antigravity-cli"); self.assertEqual(provider_by_name("antigravity-cli").name, "antigravity-cli")
        with self.assertRaises(Exception):
            provider_by_name("codex")


if __name__ == "__main__":
    unittest.main()


class TestRuntimeSetting(unittest.TestCase):
    """The runtime saved from the UI wins over CRAFTCTL_PROVIDER, which wins over the default."""

    def setUp(self):
        from mod_orchestra.state import Store
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "s.sqlite")
        self.addCleanup(lambda: os.environ.pop("CRAFTCTL_PROVIDER", None))

    def test_precedence(self):
        from mod_orchestra.dispatch import provider_name_for, provider_for
        os.environ.pop("CRAFTCTL_PROVIDER", None)
        self.assertEqual(provider_name_for(self.store), "claude-code")
        os.environ["CRAFTCTL_PROVIDER"] = "gemini-cli"
        self.assertEqual(provider_name_for(self.store), "gemini-cli")
        self.store.set_global("provider", "claude-code")
        self.assertEqual(provider_name_for(self.store), "claude-code"); self.assertEqual(provider_for(self.store).name, "claude-code")
        self.store.set_global("provider", None)
        self.assertEqual(provider_name_for(self.store), "gemini-cli")
        self.assertEqual(provider_name_for(None), "gemini-cli")

    def test_global_settings_roundtrip(self):
        self.assertIsNone(self.store.get_global("provider"))
        self.store.set_global("provider", "gemini-cli"); self.assertEqual(self.store.get_global("provider"), "gemini-cli")
        self.store.set_global("provider", None); self.assertIsNone(self.store.get_global("provider"))
