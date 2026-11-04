"""Fabric GameTests through the controller: approval-gated `gradlew runGametest` in the broker, JUnit XML parsed,
GAMETEST_PASS / GAMETEST_FAILED recorded as evidence; failures open the repair loop with the failing test names."""
from __future__ import annotations
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .broker import run_watch
from .build import _gradle_launcher, _require_current_generator, BUILDABLE_STATUSES
from .evidence import record_evidence
from .fabric import validate_generated
from .state import Store, StateError
from .redact import redact

GAMETEST_TIMEOUT = int(os.environ.get("CRAFTCTL_GAMETEST_TIMEOUT", "900"))
FINISHED = re.compile(r"(All \d+ required tests passed|\d+ required tests failed|GameTest.*(?:passed|failed)|BUILD (?:SUCCESSFUL|FAILED))")


def gametest_log_path(root: Path) -> Path:
    d = root / ".mod-orchestra" / "build"; d.mkdir(parents=True, exist_ok=True)
    return d / "gametest.log"


def request_gametest(store: Store, pid: str) -> dict:
    proj = store.project(pid)
    if proj["status"] not in ("BUILD_PASSED_GAME_UNTESTED", "GAME_VERIFIED"):
        raise StateError("GameTests need a BUILD_PASS on the current source first (craftctl build)")
    root = Path(proj["root"])
    args = {"root": str(root), "task": "runGametest", "version": proj["spec"]["profile"]}
    return store.request_approval(pid, "run_gametests", args,
        "Run the mod's GameTests in a headless test server (Gradle runGametest) in " + redact(str(root)) + "/build/gametest. "
        "Executable project code; no EULA, no world of yours is touched.")


def parse_junit(path: Path) -> dict:
    if not path.is_file():
        return {"found": False, "tests": 0, "failures": 0, "errors": 0, "failed": []}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return {"found": True, "tests": 0, "failures": 0, "errors": 0, "failed": [], "parse_error": True}
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    cases = list(root.iter("testcase"))
    tests = max(len(cases), sum(int(s.get("tests", 0) or 0) for s in suites))   # Fabric's report may omit the counts
    failed = []
    for tc in cases:
        f = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
        if f is not None:
            failed.append({"name": tc.get("name", "?"), "message": (f.get("message") or (f.text or "").strip())[:300]})
    return {"found": True, "tests": tests, "failures": len(failed), "errors": 0, "failed": failed[:20], "names": [c.get("name", "?") for c in cases][:50]}


def run_gametest(store: Store, pid: str, approval_id: str) -> dict:
    proj = store.project(pid)
    if proj["status"] not in BUILDABLE_STATUSES:
        raise StateError("Generate and build first")
    root = Path(proj["root"])
    _require_current_generator(root)
    checked = validate_generated(root)
    if checked["status"] != "PASS":
        raise StateError("Generated files changed since generation; refusing to run: " + "; ".join(checked["problems"][:5]))
    gradle = _gradle_launcher(root)
    if gradle is None:
        raise StateError("No Gradle wrapper in workspace")
    args = {"root": str(root), "task": "runGametest", "version": proj["spec"]["profile"]}
    if not store.consume_approval(approval_id, pid, "run_gametests", args):
        raise StateError("An unexpired, one-use, specifically approved GameTest run is required")
    log = gametest_log_path(root)
    run_dir = root / "build" / "gametest"; run_dir.mkdir(parents=True, exist_ok=True)
    if not (run_dir / "server.properties").is_file():
        (run_dir / "server.properties").write_text("online-mode=false\nsync-chunk-writes=false\n", encoding="utf8")  # the test server refuses to start without one
    (run_dir / "eula.txt").write_text("eula=true\n", encoding="utf8")
    report = root / "build" / "gametest" / "junit.xml"
    if report.is_file():
        report.unlink()
    rec = run_watch([str(gradle), "--no-daemon", "--console=plain", "runGametest"], cwd=root, log=log, timeout=GAMETEST_TIMEOUT, ready=FINISHED, stop_input=None)
    text = log.read_text(encoding="utf8", errors="replace")
    junit = parse_junit(report)
    passed = junit["found"] and junit["tests"] > 0 and junit["failures"] == 0 and junit["errors"] == 0 and rec["exit_code"] == 0
    if not junit["found"]:
        m = re.search(r"All (\d+) required tests passed", text)
        if m and rec["exit_code"] == 0:
            junit = {"found": False, "tests": int(m.group(1)), "failures": 0, "errors": 0, "failed": []}; passed = True
    result = {"log": str(log), "exit_code": rec["exit_code"], "duration_s": rec["duration_s"], "junit": junit,
              "status": "GAMETEST_PASS" if passed else "GAMETEST_FAILED"}
    store.add_event(pid, "controller", "GAMETEST_RESULT", result)
    if passed:
        ev = record_evidence(store, pid, "GAMETEST_PASS", actor="controller", note=f"{junit['tests']} GameTest(s) passed in a headless server ({log.name})", payload={"junit": junit})
        result["evidence"] = {"id": ev["id"]}
    else:
        from .repair import open_repair_task
        why = ("failing tests: " + "; ".join(f"{f['name']}: {f['message']}" for f in junit["failed"][:4])) if junit["failed"] else \
              ("no JUnit report produced" if not junit["found"] else f"gradle exit {rec['exit_code']}")
        try:
            result["repair"] = open_repair_task(store, pid, reason=f"GameTests failed: {why}", source="gametest")
            tid = result["repair"].get("task")
            if tid:
                tail = "\n".join(text.splitlines()[-80:])
                brief = ["GameTests failed (craftctl gametest). Fix the mod so the tests pass; do not delete or weaken tests.",
                         "Failing tests:"] + [f"- {f['name']}: {f['message']}" for f in junit["failed"]] + ["", f"Log tail ({log.name}):", tail]
                with store.tx() as con:
                    con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (tid, "\n".join(brief)[:12000]))
        except StateError as exc:
            result["repair"] = {"exhausted": True, "error": str(exc)}
    return result
