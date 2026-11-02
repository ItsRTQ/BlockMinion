#!/usr/bin/env python3
"""PreToolUse guard for Minecraft Mod Orchestra (Claude Code hook; runs on Windows and POSIX).

Reads the hook JSON on stdin. Exit 2 blocks the tool call and sends the message to Claude.
Blocks:
  - USER-ONLY craftctl operations (approval gates must be the human's action)
  - git push / force / reset --hard (the user merges and releases)
  - Write/Edit outside knowledge/ for the researcher role
"""
import json
import re
import sys

USER_ONLY = r"(?:craftctl|mod_orchestra\.cli)\s+(approve-spec|request-build|decide|build|evidence|delete|release|new|requeue|add-task|dispatch|orchestrate|autopilot|accept-changes|break|server-smoke|request-smoke|add-recipe|remove-recipe|add-drop|add-mob|remove-mob|add-material|remove-material|add-food|remove-food|set-tab|run-client|answer|interpret-suite)\b"
GIT_BLOCK = r"\bgit\s+(push|reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s+\.)"

def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}
    agent = data.get("agent_type") or data.get("agent_name") or ""
    if tool in ("Bash", "PowerShell"):
        cmd = inp.get("command", "") or ""
        m = re.search(USER_ONLY, cmd)
        if m:
            print(f"Blocked: `craftctl {m.group(1)}` is USER-ONLY. Tell the user the exact command instead.", file=sys.stderr)
            return 2
        if re.search(GIT_BLOCK, cmd):
            print("Blocked: git push/reset/clean are the user's actions. Commit locally and report.", file=sys.stderr)
            return 2
    if tool in ("Write", "Edit", "MultiEdit") and agent == "researcher":
        path = (inp.get("file_path") or inp.get("path") or "").replace("\\", "/")
        if "/knowledge/" not in path and not path.startswith("knowledge/"):
            print("Blocked: the researcher writes only under knowledge/.", file=sys.stderr)
            return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
