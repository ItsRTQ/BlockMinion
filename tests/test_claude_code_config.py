"""R2: Claude Code adapter files are consistent and the guard enforces USER-ONLY gates."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from mod_orchestra.capabilities import CAPABILITIES

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".claude/agents"
SKILLS = ROOT / ".claude/skills"
GUARD = ROOT / ".claude/hooks/guard.py"
USER_ONLY = ("approve-spec", "request-build", "decide", "build", "evidence", "delete", "release", "new", "requeue", "add-task", "dispatch", "orchestrate", "autopilot", "accept-changes", "break", "server-smoke", "request-smoke", "add-recipe", "remove-recipe", "add-drop", "add-mob", "remove-mob", "add-material", "remove-material", "add-food", "remove-food", "set-tab", "run-client", "answer", "interpret-suite")


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf8")
    assert text.startswith("---\n"), path
    block = text.split("---\n", 2)[1]
    out = {}
    key = None
    for line in block.splitlines():
        if re.match(r"^[a-zA-Z]+:", line):
            key, _, val = line.partition(":"); val = val.strip()
            # Claude Code parses this block as YAML: an unquoted scalar containing ": " is a
            # mapping error and the whole agent is silently skipped (R2 smoke: 3 of 12 roles).
            if val and val[0] not in "\"'":
                assert ": " not in val and not val.endswith(":"), f"{path.name}: quote the `{key}` value, it contains ': '"
            elif val:
                val = val[1:-1]
            out[key.strip()] = val or []
        elif line.strip().startswith("- ") and key:
            out[key].append(line.strip()[2:])
    return out


class AgentFiles(unittest.TestCase):
    def test_one_agent_and_one_skill_per_role(self):
        roles = set(CAPABILITIES)
        self.assertEqual({p.stem for p in AGENTS.glob("*.md")}, roles)
        self.assertTrue(roles <= {p.parent.name for p in SKILLS.glob("*/SKILL.md")})  # roles + shared skills (recipes)

    def test_frontmatter_is_valid_and_preloads_matching_skill(self):
        for path in AGENTS.glob("*.md"):
            fm = frontmatter(path)
            self.assertEqual(fm["name"], path.stem, path)
            self.assertTrue(fm.get("description"), path)
            self.assertEqual(fm.get("skills", [])[0], path.stem, path)
            for sk in fm.get("skills", []):
                self.assertTrue((SKILLS / sk / "SKILL.md").is_file(), f"{path.name} preloads missing skill {sk}")
            self.assertTrue(fm.get("tools"), path)

    def test_no_agent_lists_a_user_only_mcp_tool_or_unknown_mcp_tool(self):
        from mod_orchestra.mcp import TOOLS
        # Claude Code names an MCP tool mcp__<server>__<tool>; the server's tools are orchestra_*,
        # so the only valid spelling is mcp__minecraft-orchestra__orchestra_<x>.
        known = {"mcp__minecraft-orchestra__" + t["name"] for t in TOOLS}
        for path in AGENTS.glob("*.md"):
            for tool in [t.strip() for t in frontmatter(path)["tools"].split(",")]:
                if tool.startswith("mcp__blockbench__"):
                    continue  # vendored blockbench-mcp-safe server (resources/blockbench-mcp-safe); wildcard allowed
                if tool.startswith("mcp__"):
                    self.assertIn(tool, known, f"{path.name}: {tool} is not a real MCP tool")
                    for word in ("approve", "decide", "build_project", "evidence", "delete"):
                        self.assertNotIn(word, tool.removeprefix("mcp__minecraft-orchestra__orchestra_diagnose_"))

    def test_only_coder_class_roles_can_edit(self):
        editors = {p.stem for p in AGENTS.glob("*.md") if re.search(r"\b(Edit|Write)\b", frontmatter(p)["tools"])}
        self.assertEqual(editors, {"coder", "designer", "world-builder", "debugger", "researcher"})

    def test_settings_deny_every_user_only_command(self):
        settings = json.loads((ROOT / ".claude/settings.json").read_text())
        deny = " ".join(settings["permissions"]["deny"])
        for cmd in USER_ONLY:
            self.assertIn(f"Bash(craftctl {cmd}", deny)
            self.assertIn(f"PowerShell(craftctl {cmd}", deny, "A6: Windows desktop sessions use the PowerShell tool")
        self.assertIn("Bash(git push", deny); self.assertIn("PowerShell(git push", deny)
        hook_cmds = [h["command"] for grp in settings["hooks"]["PreToolUse"] for h in grp["hooks"] if "guard.py" in h["command"]]
        self.assertTrue(hook_cmds)
        for cmd in hook_cmds:
            # A cwd-relative script path breaks (and fails closed, blocking every shell/edit tool)
            # as soon as the session `cd`s into a subdirectory. Anchor it to the project dir.
            self.assertIn("$CLAUDE_PROJECT_DIR", cmd, cmd)
            self.assertNotIn(" .claude/", cmd, cmd)

    def test_mcp_json_launches_the_server_without_relying_on_path(self):
        cfg = json.loads((ROOT / ".mcp.json").read_text())
        server = cfg["mcpServers"]["minecraft-orchestra"]
        # `craftctl` is often not on PATH (venv not activated, Store Python Scripts dir); the
        # module form works wherever `python` can import the package (SETUP.md fallback).
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"], ["-m", "mod_orchestra.cli", "mcp"])


class Guard(unittest.TestCase):
    def run_guard(self, payload: dict) -> tuple[int, str]:
        p = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload), capture_output=True, text=True)
        return p.returncode, p.stderr

    def test_blocks_user_only_craftctl_in_both_spellings(self):
        for cmd in USER_ONLY:
            for prefix in ("craftctl", "python -m mod_orchestra.cli"):
                code, err = self.run_guard({"tool_name": "Bash", "tool_input": {"command": f"{prefix} {cmd} x"}})
                self.assertEqual(code, 2, f"{prefix} {cmd}"); self.assertIn("USER-ONLY", err)

    def test_allows_read_and_gradle(self):
        for cmd in ("craftctl status x", "craftctl doctor", "./gradlew build", "git status", "python -m unittest"):
            self.assertEqual(self.run_guard({"tool_name": "Bash", "tool_input": {"command": cmd}})[0], 0, cmd)

    def test_blocks_git_push_and_hard_reset(self):
        for cmd in ("git push origin dev", "git reset --hard HEAD~1"):
            self.assertEqual(self.run_guard({"tool_name": "Bash", "tool_input": {"command": cmd}})[0], 2, cmd)

    def test_researcher_writes_only_under_knowledge(self):
        self.assertEqual(self.run_guard({"tool_name": "Write", "agent_type": "researcher", "tool_input": {"file_path": "src/x.py"}})[0], 2)
        self.assertEqual(self.run_guard({"tool_name": "Write", "agent_type": "researcher", "tool_input": {"file_path": "knowledge/fabric/x.md"}})[0], 0)
        self.assertEqual(self.run_guard({"tool_name": "Write", "agent_type": "coder", "tool_input": {"file_path": "src/x.py"}})[0], 0)

    def test_malformed_input_never_blocks(self):
        p = subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
