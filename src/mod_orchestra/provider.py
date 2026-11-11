"""R2: AgentProvider — how the controller runs one bounded worker (DEVELOPMENT_PATH R2).

The controller never lets an agent run "independently of application state": it builds a
TaskEnvelope from the Footprint, starts exactly one worker with a role-scoped definition,
captures everything the worker printed, and accepts only a schema-valid handoff. Anything
else fails the run and returns the task to the user.

v1 uses the user's installed Claude Code and subscription (`claude -p`); no API key.
`GeminiCliProvider` runs the same envelope through the user's installed Gemini CLI (`gemini --prompt … --output-format
stream-json`), with the role definition and skills inlined in the prompt and the MCP servers declared in the
workspace's `.gemini/settings.json` for the duration of the run.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .broker import run_logged, controlled_env
from .config import HOME
from .state import StateError

RESOURCES = Path(__file__).resolve().parent / "resources" / "claude"
AGENT_TIMEOUT = int(os.environ.get("CRAFTCTL_AGENT_TIMEOUT", "1200"))
AGENT_MAX_TURNS = int(os.environ.get("CRAFTCTL_AGENT_MAX_TURNS", "40"))

# Evidence levels a worker may *claim*. Game levels are the user's (see evidence.py).
WORKER_EVIDENCE_LEVELS = ("STATIC", "BUILD_PASS", "BUILD_FAILED", "NONE")
HANDOFF_FIELDS = ("task", "status", "scope", "changed_files", "checks_run", "evidence", "risks", "unknowns", "needs_user", "next_agent")
HANDOFF_STATUSES = ("DONE", "WAITING_USER", "BLOCKED", "FAILED")


@dataclass
class TaskEnvelope:
    project_id: str
    task_id: str
    role: str
    title: str
    workspace: Path
    packet: str                 # bounded handoff packet from capabilities.handoff (already redacted)
    extra_instructions: str = ""


@dataclass
class RunResult:
    exit_code: int
    duration_s: float
    log_path: Path
    raw_output: str
    handoff: dict | None = None
    errors: list[str] = field(default_factory=list)
    session_id: str | None = None
    cost_usd: float | None = None
    turns: int | None = None
    killed: bool = False


def validate_handoff(obj: object) -> list[str]:
    """Return a list of problems; empty means the handoff is acceptable."""
    problems: list[str] = []
    if not isinstance(obj, dict):
        return ["handoff is not a JSON object"]
    for key in HANDOFF_FIELDS:
        if key not in obj:
            problems.append(f"missing field: {key}")
    if problems:
        return problems
    if "questions" in obj and not isinstance(obj["questions"], list):
        problems.append("questions must be a list")
    if "spec" in obj and not isinstance(obj["spec"], dict):
        problems.append("spec must be an object")
    if "card" in obj and not isinstance(obj["card"], dict):
        problems.append("card must be an object")
    if obj["status"] not in HANDOFF_STATUSES:
        problems.append(f"status must be one of {HANDOFF_STATUSES}, got {obj['status']!r}")
    for key in ("changed_files", "checks_run", "risks", "unknowns", "needs_user"):
        if not isinstance(obj[key], list):
            problems.append(f"{key} must be a list")
    ev = obj["evidence"]
    if not isinstance(ev, dict) or "level" not in ev:
        problems.append("evidence must be an object with a 'level'")
    elif ev["level"] not in WORKER_EVIDENCE_LEVELS:
        problems.append(f"evidence.level {ev['level']!r} is not something a worker can claim; allowed: {WORKER_EVIDENCE_LEVELS}")
    if isinstance(obj.get("checks_run"), list):
        for c in obj["checks_run"]:
            if not isinstance(c, dict) or "command" not in c or "exit_code" not in c:
                problems.append("each checks_run entry needs 'command' and 'exit_code'")
                break
    if isinstance(ev, dict) and ev.get("level") == "BUILD_PASS":
        ok = any(isinstance(c, dict) and c.get("exit_code") == 0 and "gradle" in str(c.get("command", "")).lower()
                 for c in obj.get("checks_run", []))
        if not ok:
            problems.append("evidence.level BUILD_PASS requires a gradle command with exit_code 0 in checks_run")
    # DONE + needs_user is legitimate: the worker's part is finished and the user's next steps
    # (request-build/decide/build/evidence) follow. WAITING_USER means the worker itself is blocked.
    return problems


HANDOFF_INSTRUCTIONS = """
## Output contract (mandatory)
Finish your reply with exactly one fenced block tagged `handoff` containing a JSON object with these fields:
```handoff
{"task": "<task id>", "status": "DONE|WAITING_USER|BLOCKED|FAILED",
 "scope": "<one sentence>", "changed_files": ["relative/path", ...],
 "checks_run": [{"command": "...", "exit_code": 0}],
 "evidence": {"level": "STATIC|BUILD_PASS|BUILD_FAILED|NONE", "pointer": "<log/jar/path or note>"},
 "risks": ["..."], "unknowns": ["..."],
 "needs_user": ["<exact craftctl command the user must run, if any>"],
 "needs": [{"role": "coder", "what": "<what must exist that does not>", "why": "<why your task needs it>", "target": "<the item/mob/block id or card it belongs to, if any>"}],
 "next_agent": "<role or none>"}
```
Status: DONE = your part is complete (list the user's next craftctl steps under needs_user);
WAITING_USER = you cannot continue until the user acts; BLOCKED = missing information; FAILED = you could not do it.
A limitation is work, not a stop: when what you were asked to build on does not exist yet (a mechanic, an entity, a moment the
code never emits, a thing to animate), do not fake it and do not stop silently: report status BLOCKED with `needs` saying what
must exist and why; the controller has it made by the right role and runs you again right after, with it in place.
Rules: you are running with the project workspace as your current directory. Only claim BUILD_PASS if you ran
`./gradlew build` (or `gradlew.bat build`) here and it exited 0. Never claim client/server/in-game results.
Never run `craftctl approve-spec|request-build|decide|build|evidence|delete|release|new`; list them under
needs_user instead. Do not modify files outside this workspace.
"""

_HANDOFF_RE = re.compile(r"```handoff[ \t]*\n(.*?)```", re.S)


def extract_handoff(text: str) -> tuple[dict | None, list[str]]:
    matches = _HANDOFF_RE.findall(text or "")
    if not matches:
        return None, ["no ```handoff block in worker output"]
    try:
        obj = json.loads(matches[-1].strip())
    except json.JSONDecodeError as exc:
        return None, [f"handoff block is not valid JSON: {exc}"]
    return obj, validate_handoff(obj)


def parse_claude_json(raw: str) -> dict | None:
    """Find the final envelope in a worker log. Works for `--output-format json` (one object) and for
    `--output-format stream-json` (one JSON object per line; the one with type "result" is the envelope).
    The log may also hold a command header, stderr noise, and anything after; nothing is assumed about order."""
    decoder = json.JSONDecoder()
    fallback = None
    for line_start in (m.start() for m in re.finditer(r"(?m)^\s*\{", raw)):
        try:
            obj, _ = decoder.raw_decode(raw, line_start + raw[line_start:].index("{"))
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "result":
            return obj
        if fallback is None and obj.get("type") is None and ("result" in obj or "session_id" in obj or "is_error" in obj):
            fallback = obj
    return fallback


_ERRORISH = re.compile(r"error|failed|not found|denied|unauthori[sz]ed|quota|exhausted|not signed in|timed out|traceback", re.I)


def _generic_event_line(obj: dict) -> str:
    """One compact line for an event the summary does not know (Antigravity nests its payload under the event name):
    the event name plus the first descriptive field, so progress is visible instead of hidden."""
    name = str(obj.get("event"))
    payload = obj.get(name) if isinstance(obj.get(name), dict) else obj
    detail = ""
    for key in ("tool_name", "tool", "name", "command", "message", "text", "content", "status", "error", "path", "file_path"):
        v = payload.get(key)
        if isinstance(v, (str, int, float)) and str(v).strip():
            detail = f"{key}={str(v).strip()}"; break
    if not detail:
        detail = "{" + ", ".join(list(payload)[:6]) + "}"
    return f"· {name} {detail}".replace("\n", " ")[:170]


def live_summary(raw: str, limit: int = 60) -> list[str]:
    """Human-readable lines from a stream-json worker log while it runs: tool calls and text snippets."""
    out: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            if line and _ERRORISH.search(line):   # plain stderr-style lines such as "Not signed in" or a stack trace headline
                out.append("! " + line[:200])
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = obj.get("type") or obj.get("event")
        if t == "result" and isinstance(obj.get("result"), dict):   # Antigravity (agy)
            r = obj["result"]; u = r.get("usage") or {}
            out.append(f"■ finished: {str(r.get('status', '?')).lower()} · {r.get('num_turns', '?')} turns · {u.get('input_tokens', '?')}/{u.get('output_tokens', '?')} tokens")
        elif t == "assistant":
            for block in (obj.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    arg = inp.get("command") or inp.get("file_path") or inp.get("path") or inp.get("pattern") or inp.get("query") or ""
                    out.append(f"→ {block.get('name')} {str(arg)[:140]}")
                elif block.get("type") == "text" and block.get("text", "").strip():
                    out.append("… " + block["text"].strip().replace("\n", " ")[:160])
        elif t == "user":
            for block in (obj.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_result":
                    content = block.get("content")
                    text = content if isinstance(content, str) else " ".join(c.get("text", "") for c in content or [] if isinstance(c, dict))
                    if block.get("is_error"):
                        out.append("   ✗ " + text.strip().replace("\n", " ")[:160])
        elif t == "result" and "stats" in obj and "num_turns" not in obj:   # Gemini CLI
            st = obj.get("stats") or {}
            out.append(f"■ finished: {obj.get('status', '?')} · {st.get('input_tokens', '?')}/{st.get('output_tokens', '?')} tokens")
        elif t == "result":
            out.append(f"■ finished: {obj.get('subtype')} · {obj.get('num_turns')} turns · ${float(obj.get('total_cost_usd') or 0):.2f}")
        elif t == "message" and obj.get("role") == "assistant" and str(obj.get("content") or "").strip():   # Gemini CLI
            out.append("… " + str(obj["content"]).strip().replace("\n", " ")[:160])
        elif t == "tool_use" and "tool_name" in obj:   # Gemini CLI
            inp = obj.get("parameters") or {}
            arg = inp.get("command") or inp.get("file_path") or inp.get("path") or inp.get("pattern") or inp.get("query") or ""
            out.append(f"→ {obj.get('tool_name')} {str(arg)[:140]}")
        elif t == "tool_result" and obj.get("status") == "error":   # Gemini CLI
            err = obj.get("error") or {}
            out.append("   ✗ " + str(err.get("message") or obj.get("output") or "").strip().replace("\n", " ")[:160])
        elif "event" in obj and "type" not in obj:   # any other Antigravity event
            out.append(_generic_event_line(obj))
    return out[-limit:]


def parse_gemini_stream(raw: str) -> dict:
    """Fold a Gemini CLI `--output-format stream-json` log (JSONL; other lines ignored) into one record:
    the assistant text in order (message events, deltas or whole), session id and model from `init`, the `result`
    event's status/stats, and any `error` events. Works on a partial log too (the run may have been killed)."""
    text_parts: list[str] = []
    result_text = None
    rec = {"text": "", "session_id": None, "model": None, "status": None, "stats": None, "errors": [], "result_seen": False}
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = obj.get("type") or obj.get("event")   # Gemini CLI says "type", Antigravity (agy) says "event"
        if t == "result" and isinstance(obj.get("result"), dict):   # agy: {"event":"result","result":{"response": "...", "conversation_id": ...}}
            r = obj["result"]
            rec["result_seen"] = True
            rec["session_id"] = r.get("conversation_id") or rec["session_id"]
            rec["status"] = str(r.get("status") or "").lower() or rec["status"]
            rec["stats"] = {**(r.get("usage") or {}), **({"turns": r["num_turns"]} if isinstance(r.get("num_turns"), int) else {})}
            if isinstance(r.get("response"), str) and r["response"].strip():
                result_text = r["response"]   # authoritative: the final answer, handoff block included
            if r.get("error"):
                rec["errors"].append(str(r["error"])[:300])
            continue
        if t == "init":
            rec["session_id"] = obj.get("session_id") or rec["session_id"]; rec["model"] = obj.get("model") or rec["model"]
        elif t == "message" and obj.get("role") == "assistant":
            content = obj.get("content")
            if isinstance(content, list):
                content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
            if isinstance(content, str):
                text_parts.append(content)
        elif t == "error":
            rec["errors"].append(str(obj.get("message") or obj.get("error") or obj)[:300])
        elif t == "result":
            rec["result_seen"] = True
            rec["status"] = obj.get("status"); rec["stats"] = obj.get("stats")
            rec["model"] = obj.get("model") or rec["model"]
            if obj.get("error"):
                rec["errors"].append(str(obj["error"])[:300])
            if isinstance(obj.get("response"), str) and obj["response"].strip() and not text_parts:
                text_parts.append(obj["response"])
    rec["text"] = result_text if result_text is not None else "".join(text_parts)
    if not rec["text"] and not rec["result_seen"] and "```handoff" in raw:
        rec["text"] = raw   # plain-text headless output (no JSON events): the handoff block is still in there
    return rec


class AgentProvider:
    name = "abstract"

    def run(self, envelope: TaskEnvelope, log_path: Path) -> RunResult:  # synchronous, one worker
        raise NotImplementedError


class FakeProvider(AgentProvider):
    """Deterministic provider for tests and dry runs: returns a scripted reply."""
    name = "fake"

    def __init__(self, reply: str, exit_code: int = 0, duration_s: float = 0.1):
        self.reply, self.exit_code, self.duration_s = reply, exit_code, duration_s
        self.envelopes: list[TaskEnvelope] = []

    def run(self, envelope: TaskEnvelope, log_path: Path) -> RunResult:
        self.envelopes.append(envelope)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(self.reply, encoding="utf8")
        handoff, errors = extract_handoff(self.reply)
        return RunResult(self.exit_code, self.duration_s, log_path, self.reply, handoff, errors)


def _load_agent_definitions() -> dict:
    """Agent JSON for `claude --agents`, with each role's skill inlined (no .claude/ dir in the workspace)."""
    agents = {}
    for path in sorted((RESOURCES / "agents").glob("*.md")):
        text = path.read_text(encoding="utf8")
        head, _, body = text.partition("\n---\n")
        fm: dict[str, str] = {}
        for line in head.splitlines():
            if ":" in line and not line.startswith("---") and not line.startswith("  "):
                k, _, v = line.partition(":"); fm[k.strip()] = v.strip().strip('"')
        name = fm.get("name") or path.stem
        prompt = body.strip()
        preload = [l.strip()[2:] for l in head.splitlines() if l.strip().startswith("- ")] or [name]
        for sk in preload:
            skill = RESOURCES / "skills" / sk / "SKILL.md"
            if skill.is_file():
                prompt += "\n\n# Preloaded skill: " + sk + "\n" + skill.read_text(encoding="utf8")
        entry = {"description": fm.get("description", name), "prompt": prompt}
        if fm.get("tools"):
            entry["tools"] = [t.strip() for t in fm["tools"].split(",") if t.strip()]
        agents[name] = entry
    return agents


def _settings_for_run(guard: Path) -> dict:
    base = json.loads((RESOURCES / "settings.json").read_text(encoding="utf8"))
    base.setdefault("permissions", {}).setdefault("allow", [])
    # Headless runs cannot answer prompts: allow the build/test commands a worker legitimately needs.
    for rule in ("Bash(./gradlew *)", "Bash(./gradlew.bat *)", "Bash(gradlew.bat *)", "Bash(.\\\\gradlew.bat *)", "Bash(sha256sum *)", "Bash(unzip *)", "Bash(ls*)", "Bash(cat *)",
                 "Bash(python *)", "Bash(python3 *)", "Bash(git status*)", "Bash(git diff*)", "Bash(mkdir *)",
                 "PowerShell(./gradlew *)", "PowerShell(.\\\\gradlew.bat *)", "PowerShell(gradlew.bat *)", "PowerShell(Get-FileHash *)",
                 "PowerShell(python *)", "PowerShell(python3 *)", "PowerShell(git status*)", "PowerShell(git diff*)",
                 "Read", "Edit", "Write", "Grep", "Glob", "mcp__minecraft-orchestra__*", "mcp__blockbench__*"):
        if rule not in base["permissions"]["allow"]:
            base["permissions"]["allow"].append(rule)
    base["hooks"] = {"PreToolUse": [{"matcher": "Bash|PowerShell|Write|Edit|MultiEdit",
                                    "hooks": [{"type": "command", "command": f'python "{guard}"'}]}]}
    return base


class ClaudeCodeProvider(AgentProvider):
    """Runs one bounded worker with the user's installed Claude Code (`claude -p`), their session and subscription."""
    name = "claude-code"

    def __init__(self, binary: str | None = None, timeout: int = AGENT_TIMEOUT, max_turns: int = AGENT_MAX_TURNS):
        self.binary = binary or os.environ.get("CRAFTCTL_CLAUDE_BIN") or shutil.which("claude")
        self.timeout, self.max_turns = timeout, max_turns

    def available(self) -> bool:
        return bool(self.binary) and Path(self.binary).exists() if self.binary and os.sep in self.binary else bool(self.binary)

    def _materialize(self, tmp: Path, envelope: TaskEnvelope | None = None) -> tuple[Path, Path, Path]:
        agents = tmp / "agents.json"; agents.write_text(json.dumps(_load_agent_definitions()), encoding="utf8")
        guard = RESOURCES / "hooks" / "guard.py"
        settings = tmp / "settings.json"; settings.write_text(json.dumps(_settings_for_run(guard), indent=1), encoding="utf8")
        servers = {"minecraft-orchestra": {"command": "python", "args": ["-m", "mod_orchestra.cli", "mcp"], "env": {"CRAFTCTL_HOME": str(HOME)}}}
        if envelope is not None and envelope.role == "designer":
            from .models import blockbench_server_config
            servers["blockbench"] = blockbench_server_config(envelope.workspace)  # vendored, zero-dependency, Node only
        mcp = tmp / "mcp.json"
        mcp.write_text(json.dumps({"mcpServers": servers}), encoding="utf8")
        return agents, settings, mcp

    def run(self, envelope: TaskEnvelope, log_path: Path) -> RunResult:
        if not self.binary:
            raise StateError("Claude Code CLI (`claude`) not found on PATH. Install Claude Code or set CRAFTCTL_CLAUDE_BIN.")
        prompt = envelope.packet + "\n" + envelope.extra_instructions + HANDOFF_INSTRUCTIONS
        with tempfile.TemporaryDirectory(prefix="craftctl-run-") as td:
            tmp = Path(td)
            agents, settings, mcp = self._materialize(tmp, envelope)
            (tmp / "prompt.md").write_text(prompt, encoding="utf8")
            cmd = [self.binary, "-p", "--agent", envelope.role, "--agents", str(agents),
                   "--settings", str(settings), "--mcp-config", str(mcp), "--strict-mcp-config",
                   "--permission-mode", "acceptEdits", "--max-turns", str(self.max_turns), "--output-format", "stream-json", "--verbose"]
            env = controlled_env({"CRAFTCTL_HOME": str(HOME), "CLAUDE_PROJECT_DIR": str(envelope.workspace)})
            for passthrough in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
                if passthrough in os.environ:
                    env[passthrough] = os.environ[passthrough]   # claude login/session lives under the user's home
            record = run_logged(cmd, cwd=envelope.workspace, log=log_path, timeout=self.timeout, env=env, stdin_text=prompt)
        raw = log_path.read_text(encoding="utf8", errors="replace")
        out = parse_claude_json(raw)
        session_id = cost = turns = None
        if out is None:
            text, errors_prefix = raw, ["claude did not print a JSON result envelope (see worker log)"]
        else:
            text, errors_prefix = str(out.get("result") or ""), []
            session_id, cost, turns = out.get("session_id"), out.get("total_cost_usd"), out.get("num_turns")
            denials = out.get("permission_denials") or []
            if denials:
                with log_path.open("a", encoding="utf8") as f:
                    f.write("\n[craftctl] permission denials during run:\n")
                    for d in denials:
                        f.write(f"  - {d.get('tool_name')}: {json.dumps(d.get('tool_input', {}))[:300]}\n")
            if out.get("is_error"):
                return RunResult(record["exit_code"] or 1, record["duration_s"], log_path, raw, None,
                                 [f"claude reported is_error: {text[:300]}"], session_id, cost, turns, record["killed"])
        handoff, errors = extract_handoff(text)
        errors = errors_prefix + errors if handoff is None else errors
        if record["killed"]:
            errors.append(f"worker killed after {self.timeout}s timeout")
        return RunResult(record["exit_code"], record["duration_s"], log_path, raw, handoff, errors, session_id, cost, turns, record["killed"])


def _role_prompt(role: str) -> str:
    """The role's agent definition with its skills inlined, as plain prompt text (for runtimes without `--agents`)."""
    agents = _load_agent_definitions()
    entry = agents.get(role)
    if entry is None:
        raise StateError(f"unknown role {role!r}; known: {', '.join(sorted(agents))}")
    return f"# You are the `{role}` worker\n{entry['description']}\n\n{entry['prompt']}"


GEMINI_EXIT_CODES = {42: "bad input", 53: "turn limit exceeded"}


class GeminiCliProvider(AgentProvider):
    """Runs one bounded worker with the user's installed Gemini CLI and their Google login (no API key).

    Differences from Claude Code that this adapter absorbs: no `--agents` (the role prompt and skills go in front of the
    packet), no `--mcp-config` (the servers are written to the workspace's `.gemini/settings.json` for the run and the
    previous file is restored afterwards), no guard hook (the MCP server refuses USER-ONLY operations by itself), and the
    final text arrives as `message` events rather than inside `result`. The prompt goes through stdin so Windows' argv
    limit never truncates an inlined skill."""
    name = "gemini-cli"
    SETTINGS_REL = Path(".gemini") / "settings.json"

    def __init__(self, binary: str | None = None, timeout: int = AGENT_TIMEOUT, model: str | None = None, approval_mode: str | None = None):
        self.binary = binary or os.environ.get("CRAFTCTL_GEMINI_BIN") or shutil.which("gemini")
        self.timeout = timeout
        self.model = model or os.environ.get("CRAFTCTL_GEMINI_MODEL") or None
        self.approval_mode = approval_mode or os.environ.get("CRAFTCTL_GEMINI_APPROVAL") or "yolo"   # headless: no prompt to answer

    def available(self) -> bool:
        return bool(self.binary) and (Path(self.binary).exists() if os.sep in str(self.binary) else bool(shutil.which(str(self.binary))))

    def _servers(self, envelope: TaskEnvelope) -> dict:
        servers = {"minecraft-orchestra": {"command": "python", "args": ["-m", "mod_orchestra.cli", "mcp"],
                                           "env": {"CRAFTCTL_HOME": str(HOME)}, "trust": True, "timeout": 120000}}
        if envelope.role == "designer":
            from .models import blockbench_server_config
            servers["blockbench"] = {**blockbench_server_config(envelope.workspace), "trust": True}
        return servers

    def _settings(self, envelope: TaskEnvelope, existing: dict | None) -> dict:
        base = dict(existing or {})
        base["mcpServers"] = {**(base.get("mcpServers") or {}), **self._servers(envelope)}
        base["mcp"] = {**(base.get("mcp") or {}), "allowed": sorted(self._servers(envelope))}   # only ours this run
        return base

    def run(self, envelope: TaskEnvelope, log_path: Path) -> RunResult:
        if not self.binary:
            raise StateError("Gemini CLI (`gemini`) not found on PATH. Install Gemini CLI or set CRAFTCTL_GEMINI_BIN.")
        prompt = _role_prompt(envelope.role) + "\n\n" + envelope.packet + "\n" + envelope.extra_instructions + HANDOFF_INSTRUCTIONS
        settings_path = envelope.workspace / self.SETTINGS_REL
        previous = settings_path.read_text(encoding="utf8") if settings_path.is_file() else None
        try:
            existing = json.loads(previous) if previous else None
        except json.JSONDecodeError:
            existing = None
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(self._settings(envelope, existing), indent=1), encoding="utf8")
        try:
            cmd = [self.binary, "--prompt", "Carry out the task described in the input below, in this workspace. Finish with the handoff block.",
                   "--output-format", "stream-json", "--approval-mode", self.approval_mode, "--skip-trust"]
            if self.model:
                cmd += ["--model", self.model]
            env = controlled_env({"CRAFTCTL_HOME": str(HOME)})
            for passthrough in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                                "GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "NO_BROWSER"):
                if passthrough in os.environ:
                    env[passthrough] = os.environ[passthrough]   # the Google login lives under ~/.gemini
            record = run_logged(cmd, cwd=envelope.workspace, log=log_path, timeout=self.timeout, env=env, stdin_text=prompt)
        finally:
            if previous is None:
                settings_path.unlink(missing_ok=True)
                try:
                    settings_path.parent.rmdir()   # only if we created it and it is empty
                except OSError:
                    pass
            else:
                settings_path.write_text(previous, encoding="utf8")
        raw = log_path.read_text(encoding="utf8", errors="replace")
        rec = parse_gemini_stream(raw)
        errors_prefix: list[str] = []
        if not rec["result_seen"] and not rec["text"]:
            errors_prefix.append("gemini did not print a stream-json result (see worker log)")
        if record["exit_code"] in GEMINI_EXIT_CODES:
            errors_prefix.append(f"gemini exit {record['exit_code']}: {GEMINI_EXIT_CODES[record['exit_code']]}")
        errors_prefix += [f"gemini error: {e}" for e in rec["errors"]]
        handoff, errors = extract_handoff(rec["text"])
        errors = errors_prefix + errors if handoff is None else errors_prefix + errors
        if record["killed"]:
            errors.append(f"worker killed after {self.timeout}s timeout")
        turns = None
        if isinstance(rec["stats"], dict) and isinstance(rec["stats"].get("tool_calls"), int):
            turns = rec["stats"]["tool_calls"]
        return RunResult(record["exit_code"], record["duration_s"], log_path, raw, handoff, errors, rec["session_id"], None, turns, record["killed"])


class AntigravityCliProvider(GeminiCliProvider):
    """Runs one bounded worker with Google's Antigravity CLI (`agy`), the successor of Gemini CLI for personal
    accounts (June 2026). Same shape as the Gemini adapter with the differences Antigravity introduced:
    `--dangerously-skip-permissions` instead of `--approval-mode`, `--print-timeout` (default 5 min, raised to
    ours), no `--skip-trust`, `--model` only when one is chosen (UI or CRAFTCTL_AGY_MODEL), MCP servers in the workspace's `.agents/mcp_config.json`,
    and `--output-format stream-json` only from agy 1.1.8. The full prompt is also written to
    `.agents/craftctl_task.md` and the short `--prompt` points at it, so the task survives a CLI that does not
    append stdin to the prompt."""
    name = "antigravity-cli"
    SETTINGS_REL = Path(".agents") / "mcp_config.json"
    TASK_REL = Path(".agents") / "craftctl_task.md"

    def __init__(self, binary: str | None = None, timeout: int = AGENT_TIMEOUT, model: str | None = None, approval_mode: str | None = None):
        super().__init__(binary or os.environ.get("CRAFTCTL_AGY_BIN") or shutil.which("agy"), timeout, model, approval_mode)
        self.model = model or os.environ.get("CRAFTCTL_AGY_MODEL") or None   # agy model ids differ from Gemini CLI's; `agy models` lists them

    def _servers(self, envelope: TaskEnvelope) -> dict:
        out = {}
        for name, cfg in super()._servers(envelope).items():
            out[name] = {k: v for k, v in cfg.items() if k in ("command", "args", "env", "cwd")}   # agy's mcp_config keys
        return out

    def _settings(self, envelope: TaskEnvelope, existing: dict | None) -> dict:
        base = dict(existing or {})
        base["mcpServers"] = {**(base.get("mcpServers") or {}), **self._servers(envelope)}
        return base

    def run(self, envelope: TaskEnvelope, log_path: Path) -> RunResult:
        if not self.binary:
            raise StateError("Antigravity CLI (`agy`) not found on PATH. Install it from antigravity.google or set CRAFTCTL_AGY_BIN.")
        prompt = _role_prompt(envelope.role) + "\n\n" + envelope.packet + "\n" + envelope.extra_instructions + HANDOFF_INSTRUCTIONS
        settings_path = envelope.workspace / self.SETTINGS_REL
        task_path = envelope.workspace / self.TASK_REL
        previous = settings_path.read_text(encoding="utf8") if settings_path.is_file() else None
        try:
            existing = json.loads(previous) if previous else None
        except json.JSONDecodeError:
            existing = None
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(self._settings(envelope, existing), indent=1), encoding="utf8")
        task_path.write_text(prompt, encoding="utf8")
        try:
            cmd = [self.binary, "--prompt",
                   f"Read {self.TASK_REL.as_posix()} in this workspace (the same text may also arrive on stdin) and carry out the task it describes. Finish with the handoff block.",
                   "--output-format", "stream-json", "--dangerously-skip-permissions", "--print-timeout", f"{self.timeout}s"]
            if self.model:   # opt-in: without it agy picks its own default, which some accounts cannot use for every call
                cmd += ["--model", self.model]
            env = controlled_env({"CRAFTCTL_HOME": str(HOME)})
            for passthrough in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                                "GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "NO_BROWSER"):
                if passthrough in os.environ:
                    env[passthrough] = os.environ[passthrough]   # the Google login lives under ~/.gemini/antigravity-cli
            record = run_logged(cmd, cwd=envelope.workspace, log=log_path, timeout=self.timeout, env=env, stdin_text=prompt)
        finally:
            task_path.unlink(missing_ok=True)
            if previous is None:
                settings_path.unlink(missing_ok=True)
                try:
                    settings_path.parent.rmdir()
                except OSError:
                    pass
            else:
                settings_path.write_text(previous, encoding="utf8")
        raw = log_path.read_text(encoding="utf8", errors="replace")
        rec = parse_gemini_stream(raw)
        errors_prefix: list[str] = []
        if not rec["result_seen"] and not rec["text"]:
            errors_prefix.append("agy printed no result (headless stream-json needs Antigravity CLI 1.1.8+; run `agy --version` and `agy update`)")
        errors_prefix += [f"agy error: {e}" for e in rec["errors"]]
        if any("NOT_FOUND" in e or "404" in e for e in rec["errors"]):
            errors_prefix.append("Google says this account cannot use the model agy asked for: run `agy models`, then pick one you have under "
                                 "Environment → Agent runtime → Model (or set CRAFTCTL_AGY_MODEL)")
        handoff, errors = extract_handoff(rec["text"])
        errors = errors_prefix + errors
        if record["killed"]:
            errors.append(f"worker killed after {self.timeout}s timeout")
        st = rec["stats"] if isinstance(rec["stats"], dict) else {}
        turns = st.get("turns") if isinstance(st.get("turns"), int) else st.get("tool_calls") if isinstance(st.get("tool_calls"), int) else None
        return RunResult(record["exit_code"], record["duration_s"], log_path, raw, handoff, errors, rec["session_id"], None, turns, record["killed"])
