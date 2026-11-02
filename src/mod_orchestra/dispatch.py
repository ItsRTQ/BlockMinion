"""R2: controller-driven dispatch of one bounded worker per READY task.

dispatch() is the only path by which an agent is started from application state:
  pick task -> lease -> envelope -> provider.run -> validate handoff -> task state + Footprint.
The worker never decides its own task state; the handoff's `status` is a claim the
controller maps onto the task after validation.
"""
from __future__ import annotations
import os
import re
import time
from pathlib import Path

from .capabilities import CAPABILITIES, handoff
from .fabric import accept_changes
from .provider import AgentProvider, ClaudeCodeProvider, FakeProvider, TaskEnvelope, RunResult
from .redact import redact_obj
from .state import Store, StateError

DISPATCHABLE_ROLES = tuple(r for r in CAPABILITIES if r not in ("controller", "user"))  # BUILD/GAME are never agent tasks
LEASE_TTL = 3600


def pick_task(store: Store, pid: str, task_id: str | None) -> dict:
    store.refresh_ready(pid)
    tasks = store.tasks(pid)
    if task_id:
        t = next((t for t in tasks if t["id"] == task_id), None)
        if t is None:
            raise StateError(f"Task not found: {task_id}")
        if not _dispatchable_now(store, pid, t):
            raise StateError(f"{task_id} is controller/user work (generate, build, game), not an agent task; use craftctl generate/build or Autopilot")
        if t["state"] != "READY":
            raise StateError(f"Task {task_id} is {t['state']}, not READY" + (f" (last error: {t['last_error']})" if t.get("last_error") else ""))
        return t
    ready = [t for t in tasks if t["state"] == "READY" and t["role"] in DISPATCHABLE_ROLES and _dispatchable_now(store, pid, t)]
    if not ready:
        raise StateError("No READY task to dispatch (or the ready ones wait on a trusted BUILD_PASS of the current source); run `craftctl next <project>`")
    # A pending repair blocks everything else: nothing downstream is worth running on a broken build.
    ready.sort(key=lambda t: (0 if ":REPAIR:" in t["id"] else 1, t["id"]))
    return ready[0]


PLANNER_OWNED = re.compile(r":(SPEC|SCAFFOLD|BUILD|GAME)$|:CONTENT:\d+$")


def _dispatchable_now(store: Store, pid: str, task: dict) -> bool:
    """Controller/user work is never dispatched to an agent whatever role the row carries (old plans had
    SCAFFOLD/CONTENT/BUILD/GAME as coder/qa). SPEC is the exception: the interpreter is an agent."""
    if PLANNER_OWNED.search(task["id"]) and not task["id"].endswith(":SPEC"):
        return False
    if task["role"] in ("controller", "user"):
        return False
    if task["role"] != "qa" and not task["id"].endswith(":GAME"):
        return True
    from .evidence import levels_for_current_source
    try:
        return "BUILD_PASS" in levels_for_current_source(store, pid, Path(store.project(pid)["root"]))
    except StateError:
        return False


def build_envelope(store: Store, pid: str, task: dict) -> TaskEnvelope:
    proj = store.project(pid)
    packet = handoff(store, pid, task["id"])
    extra = ""
    if ":REPAIR:" in task["id"]:
        from .repair import repair_context
        extra = repair_context(store, pid)
    elif task["id"].endswith(":SPEC"):
        from .interpreter import SPEC_INSTRUCTIONS
        extra = SPEC_INSTRUCTIONS
    elif ":SPRITES:" in task["id"]:
        from .models import SPRITES_INSTRUCTIONS, theme_block
        extra = SPRITES_INSTRUCTIONS + theme_block(store, pid)
    elif ":ARMOR:" in task["id"]:
        from .models import ARMOR_INSTRUCTIONS, theme_block
        extra = ARMOR_INSTRUCTIONS.replace("<material>", task["id"].split(":ARMOR:")[1]) + theme_block(store, pid)
    elif ":MODEL:" in task["id"]:
        from .models import MODEL_INSTRUCTIONS, theme_block
        from .feedback import feedback_context
        mob = task["id"].split(":MODEL:")[1]
        extra = MODEL_INSTRUCTIONS.replace("<mob>", mob) + theme_block(store, pid) + feedback_context(store, pid, mob)
    specific = store.task_instructions(task["id"])
    if specific:
        extra = extra + "\n\n## Task-specific instructions\n" + specific
    return TaskEnvelope(project_id=pid, task_id=task["id"], role=task["role"], title=task["title"],
                        workspace=Path(proj["root"]), packet=packet, extra_instructions=extra)


def apply_outcome(store: Store, pid: str, task: dict, lease: dict, run: dict, result: RunResult) -> dict:
    worker, version = lease["lease_owner"], lease["version"]
    log = str(result.log_path)
    if result.errors or result.handoff is None:
        error = "; ".join(result.errors)[:500] or "no handoff"
        store.set_task_state(task["id"], worker, version, "FAILED", error=error)
        store.finish_run(run["id"], state="FAILED", exit_code=result.exit_code, duration_s=result.duration_s, log_path=log,
                         session_id=result.session_id, cost_usd=result.cost_usd, turns=result.turns, handoff=result.handoff, error=error)
        return {"task_state": "FAILED", "error": error}
    h = redact_obj(result.handoff)
    status = h["status"]
    if task["id"].endswith(":SPEC") and status in ("DONE", "WAITING_USER"):
        from .interpreter import apply_interpretation
        from .validation import InputError
        try:
            interp = apply_interpretation(store, pid, h, run["id"])
        except (InputError, StateError) as exc:
            error = f"interpreter proposal rejected: {exc}"
            store.set_task_state(task["id"], worker, version, "FAILED", error=error[:500])
            store.finish_run(run["id"], state="FAILED", exit_code=result.exit_code, duration_s=result.duration_s, log_path=log,
                             session_id=result.session_id, cost_usd=result.cost_usd, turns=result.turns, handoff=h, error=error)
            # Format failures are the worker's, not the user's: retry once automatically with the reason in the packet.
            failures = sum(1 for r in store.runs(pid) if r["task_id"] == task["id"] and r["state"] == "FAILED")  # includes this run
            if failures <= MAX_AUTO_RETRIES:
                with store.tx() as con:
                    con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)",
                                (task["id"], f"PREVIOUS ATTEMPT REJECTED BY THE CONTROLLER: {exc}\nFix exactly that. The `spec` object goes INSIDE the ```handoff JSON block."))
                store.requeue(task["id"], "auto-retry after rejected proposal")
                store.add_event(pid, "controller", "AUTO_RETRY", {"task": task["id"], "attempt": failures, "reason": str(exc)[:200]})
                return {"task_state": "FAILED", "error": error, "handoff": h, "auto_retry": {"task": task["id"], "attempt": failures}}
            return {"task_state": "FAILED", "error": error, "handoff": h}
        h = h | {"needs_user": interp["needs_user"], "interpretation": interp}
        status = "WAITING_USER"  # the user answers or approves; the controller, not the worker, closes SPEC via approve-spec
    if ":ADD_MOB:" in task["id"] and status == "DONE":
        _reopen_build(store, pid)
    if ":ARMOR:" in task["id"] and status == "DONE":
        from .models import install_armor_design
        from .validation import InputError
        material = task["id"].split(":ARMOR:")[1].split(":")[0]
        try:
            ad = install_armor_design(store, pid, task["id"], material, run_id=run["id"], actor=f"agent:{task['role']}")
        except (InputError, StateError, OSError) as exc:
            error = f"armor deliverables rejected: {exc}"
            store.set_task_state(task["id"], worker, version, "FAILED", error=error[:500])
            store.finish_run(run["id"], state="FAILED", exit_code=result.exit_code, duration_s=result.duration_s, log_path=log,
                             session_id=result.session_id, cost_usd=result.cost_usd, turns=result.turns, handoff=h, error=error)
            return {"task_state": "FAILED", "error": error, "handoff": h}
        h = h | {"armor": ad}
        h["changed_files"] = sorted(set(h.get("changed_files") or []) | set(ad["installed"]))
    if ":SPRITES:" in task["id"] and status == "DONE":
        from .models import install_sprites
        from .validation import InputError
        ev = next((e for e in store.events(pid, 500) if e["kind"] == "SPRITES_REQUESTED" and e["payload"].get("task") == task["id"]), None)
        ids = (ev or {}).get("payload", {}).get("items", [])
        armor = (ev or {}).get("payload", {}).get("armor", [])
        try:
            sp = install_sprites(store, pid, task["id"], ids, run_id=run["id"], actor=f"agent:{task['role']}", armor_materials=armor)
        except (InputError, StateError, OSError) as exc:
            error = f"sprite deliverables rejected: {exc}"
            store.set_task_state(task["id"], worker, version, "FAILED", error=error[:500])
            store.finish_run(run["id"], state="FAILED", exit_code=result.exit_code, duration_s=result.duration_s, log_path=log,
                             session_id=result.session_id, cost_usd=result.cost_usd, turns=result.turns, handoff=h, error=error)
            return {"task_state": "FAILED", "error": error, "handoff": h}
        h = h | {"sprites": sp}
        h["changed_files"] = sorted(set(h.get("changed_files") or []) | set(sp["installed"]))
    if ":MODEL:" in task["id"] and status == "DONE":
        from .models import install_model
        from .validation import InputError
        mob_id = task["id"].split(":MODEL:")[1]
        try:
            installed = install_model(store, pid, mob_id, run_id=run["id"], actor=f"agent:{task['role']}")
        except (InputError, StateError, OSError) as exc:
            error = f"model deliverables rejected: {exc}"
            store.set_task_state(task["id"], worker, version, "FAILED", error=error[:500])
            store.finish_run(run["id"], state="FAILED", exit_code=result.exit_code, duration_s=result.duration_s, log_path=log,
                             session_id=result.session_id, cost_usd=result.cost_usd, turns=result.turns, handoff=h, error=error)
            return {"task_state": "FAILED", "error": error, "handoff": h}
        h = h | {"model": installed}
        h["changed_files"] = sorted(set(h.get("changed_files") or []) | set(installed["installed"]))
        _reopen_build(store, pid)
    accepted = None
    if status in ("DONE", "WAITING_USER"):
        # A task's edits are the union of what all its runs reported (an earlier run may have written the
        # files and a later one only verified them). Hashes are taken from the files as they are now.
        reported = set(h.get("changed_files") or [])
        for prev in store.runs(pid):
            if prev["task_id"] == task["id"] and prev["handoff"]:
                reported.update(prev["handoff"].get("changed_files") or [])
        root = Path(store.project(pid)["root"])
        if reported and (root / ".mod-orchestra/generation-manifest.json").is_file():
            accepted = accept_changes(root, run_id=run["id"], actor=f"agent:{task['role']}", changed=sorted(reported))
            store.add_event(pid, "controller", "CHANGES_ACCEPTED", {"run": run["id"], **accepted})
            h = h | {"accepted_changes": accepted}
            if accepted["accepted"]:
                _source_changed(store, pid)
    if status == "DONE":
        evidence = [{"kind": "WORKER_HANDOFF", "value": f"run:{run['id']}"},
                    {"kind": h["evidence"]["level"], "value": str(h["evidence"].get("pointer") or log)}]
        store.finish(task["id"], worker, version, evidence)
        task_state = "DONE"
    elif status == "WAITING_USER":
        store.set_task_state(task["id"], worker, version, "WAITING_USER", error=None)
        task_state = "WAITING_USER"
    elif status == "BLOCKED":
        store.set_task_state(task["id"], worker, version, "BLOCKED", error="; ".join(h["unknowns"] + h["risks"])[:500])
        task_state = "BLOCKED"
    else:
        store.set_task_state(task["id"], worker, version, "FAILED", error="worker reported FAILED: " + "; ".join(h["risks"])[:400])
        task_state = "FAILED"
    store.finish_run(run["id"], state=task_state, exit_code=result.exit_code, duration_s=result.duration_s, log_path=log,
                     session_id=result.session_id, cost_usd=result.cost_usd, turns=result.turns, handoff=h, error=None)
    outcome = {"task_state": task_state, "handoff": h}
    # A worker that observed a failing gradle build (its own or the project's) hands the failure to the repair loop.
    if h.get("evidence", {}).get("level") == "BUILD_FAILED" or (status == "FAILED" and ":REPAIR:" in task["id"]):
        from .repair import open_repair_task
        try:
            outcome["repair"] = open_repair_task(store, pid, reason=f"worker {run['id']} ({task['role']}) reported build failure",
                                                 source=f"run:{run['id']}")
        except StateError as exc:
            outcome["repair"] = {"exhausted": True, "error": str(exc)}
    return outcome


def provider_from_env() -> AgentProvider:
    """CRAFTCTL_PROVIDER=fake (+ CRAFTCTL_FAKE_REPLY_FILE) lets the UI/CLI be exercised without Claude Code."""
    if os.environ.get("CRAFTCTL_PROVIDER") == "fake":
        path = os.environ.get("CRAFTCTL_FAKE_REPLY_FILE")
        return FakeProvider(Path(path).read_text(encoding="utf8") if path and Path(path).is_file() else "")
    return ClaudeCodeProvider()


def dispatch(store: Store, pid: str, *, task_id: str | None = None, provider: AgentProvider | None = None) -> dict:
    proj = store.project(pid)
    provider = provider or provider_from_env()
    if not store.tasks(pid):
        from .workflow import plan_project
        plan_project(store, pid)
    if proj["spec_state"] != "APPROVED" and task_id and not task_id.endswith(":SPEC"):
        raise StateError("Dispatch requires a user-approved spec (craftctl approve-spec); only the SPEC task may run before approval")
    task = pick_task(store, pid, task_id)
    if proj["spec_state"] != "APPROVED" and not task["id"].endswith(":SPEC"):
        raise StateError("Dispatch requires a user-approved spec (craftctl approve-spec); only the SPEC task may run before approval")
    worker = f"agent:{task['role']}"
    lease = store.claim(task["id"], worker, ttl=LEASE_TTL)
    if not lease:
        raise StateError(f"Could not lease {task['id']}")
    run = store.create_run(pid, task["id"], task["role"], provider.name)
    log_path_early = Path(proj["root"]) / ".mod-orchestra" / "runs" / f"{run['id']}.log"
    with store.tx() as con:
        con.execute("UPDATE runs SET log_path=? WHERE id=?", (str(log_path_early), run["id"]))
    log_path = Path(proj["root"]) / ".mod-orchestra" / "runs" / f"{run['id']}.log"
    try:
        envelope = build_envelope(store, pid, task)
        result = provider.run(envelope, log_path)
    except Exception as exc:  # provider crash: release the task, record the run, re-raise
        store.release(task["id"], worker, lease["version"], f"provider error: {exc}")
        store.finish_run(run["id"], state="FAILED", exit_code=None, duration_s=None, log_path=str(log_path), error=str(exc)[:500])
        raise
    outcome = apply_outcome(store, pid, task, lease, run, result)
    store.refresh_ready(pid)
    return {"run": run["id"], "task": task["id"], "role": task["role"], "provider": provider.name,
            "exit_code": result.exit_code, "duration_s": result.duration_s, "cost_usd": result.cost_usd, "turns": result.turns,
            "log": str(log_path), **outcome}


STALE_RUN_AFTER = LEASE_TTL + 300


def reconcile_stale_runs(store: Store, pid: str) -> list[str]:
    """Restart safety: a run still RUNNING long after its lease could have expired belonged to a
    controller that died mid-dispatch. Mark it FAILED so the board is honest; the task's lease has
    expired on its own and refresh_ready puts it back to READY."""
    stale = []
    now = time.time()
    for r in store.runs(pid):
        if r["state"] == "RUNNING" and now - r["created_at"] > STALE_RUN_AFTER:
            store.finish_run(r["id"], state="FAILED", exit_code=None, duration_s=None, log_path=r.get("log_path"),
                             error="controller restarted while this run was in progress")
            stale.append(r["id"])
    store.refresh_ready(pid)
    return stale


MAX_AUTO_RETRIES = 1
HUMAN_NEEDED = ("WAITING_USER", "BLOCKED", "FAILED")


AUTOPILOT_DEFAULT = {"approve_spec": False, "generate": False, "build": False, "server_smoke": False}


def autopilot_policy(store: Store, pid: str) -> dict:
    """What the user has pre-authorised Autopilot to do for this project (set only by the user)."""
    return AUTOPILOT_DEFAULT | (store.get_setting(pid, "autopilot", {}) or {})


def _autopilot_gate(store: Store, pid: str, policy: dict, gates: list[dict]) -> tuple[bool, str]:
    """Perform one controller-side gate the user pre-authorised. Returns (did_something, stop_reason)."""
    from .guidance import guidance
    g = guidance(store, pid)
    stage, questions = g["stage"], g.get("questions") or []
    proj = store.project(pid)
    if stage == "spec" and proj["spec_state"] != "APPROVED":
        if questions:
            return False, "the interpreter has questions for you: " + " | ".join(questions)
        if not policy["approve_spec"]:
            return False, f"spec drafted — approve it (craftctl approve-spec {pid}) or enable Autopilot's 'approve spec' for this project"
        from .workflow import approve_spec
        approve_spec(store, pid); gates.append({"gate": "approve_spec"}); store.add_event(pid, "controller", "AUTOPILOT_GATE", {"gate": "approve_spec"})
        return True, ""
    if stage == "source":
        if not policy["generate"]:
            return False, "spec approved — generate the source"
        from .workflow import generate_project
        generate_project(store, pid); gates.append({"gate": "generate"}); store.add_event(pid, "controller", "AUTOPILOT_GATE", {"gate": "generate"})
        return True, ""
    if stage == "build":
        if not policy["build"]:
            return False, "ready to build — request/grant/run the trusted build, or enable Autopilot's 'build'"
        from .build import request_build, build_project
        a = request_build(store, pid); store.decide_approval(a["id"], True)
        res = build_project(store, pid, a["id"]); gates.append({"gate": "build", "status": res["status"]})
        store.add_event(pid, "controller", "AUTOPILOT_GATE", {"gate": "build", "status": res["status"]})
        if res["status"] != "BUILD_PASS" and (res.get("repair") or {}).get("exhausted"):
            return False, "build failed and the repair loop is exhausted: " + str(res["repair"].get("error"))
        return True, ""
    if stage == "server":
        if not policy["server_smoke"]:
            return False, "built — run the dedicated-server smoke, or enable Autopilot's 'server smoke'"
        from .smoke import request_smoke, server_smoke
        a = request_smoke(store, pid); store.decide_approval(a["id"], True)
        res = server_smoke(store, pid, a["id"]); gates.append({"gate": "server_smoke", "status": res["status"]})
        store.add_event(pid, "controller", "AUTOPILOT_GATE", {"gate": "server_smoke", "status": res["status"]})
        if res["status"] != "SERVER_BOOT_PASS" and (res.get("repair") or {}).get("exhausted"):
            return False, "server smoke failed and the repair loop is exhausted"
        return True, ""
    if stage == "client":
        return False, f"ready for your eyes: launch the client (craftctl run-client {pid}), then record CLIENT_BOOT_PASS / CONTENT_VERIFIED"
    if stage == "verified":
        return False, "verified on this exact source — nothing left for Autopilot"
    return False, "no READY tasks and no gate Autopilot can cross here"


def orchestrate(store: Store, pid: str, *, max_runs: int = 5, max_cost_usd: float = 5.0, max_seconds: int = 3600,
                provider: AgentProvider | None = None) -> dict:
    """Coordinator loop: dispatch READY tasks one at a time; cross only the gates the user pre-authorised
    in the project's Autopilot policy (approve spec, generate, build, server smoke). Stops for questions,
    exhausted repairs, budgets, and always before the client (the user's eyes)."""
    started = time.time()
    if not store.tasks(pid):
        from .workflow import plan_project
        plan_project(store, pid)
    stale = reconcile_stale_runs(store, pid)
    policy = autopilot_policy(store, pid)
    runs, cost, gates = [], 0.0, []
    reason = "no READY tasks"
    while True:
        if len(runs) >= max_runs:
            reason = f"max_runs ({max_runs}) reached"; break
        if cost >= max_cost_usd:
            reason = f"max_cost_usd ({max_cost_usd}) reached"; break
        if time.time() - started > max_seconds:
            reason = f"max_seconds ({max_seconds}) reached"; break
        store.refresh_ready(pid)
        if not any(t["state"] == "READY" and t["role"] in DISPATCHABLE_ROLES and _dispatchable_now(store, pid, t) for t in store.tasks(pid)):
            did, why = _autopilot_gate(store, pid, policy, gates)
            if did:
                continue
            reason = why; break
        out = dispatch(store, pid, provider=provider)
        runs.append({k: out.get(k) for k in ("run", "task", "role", "task_state", "cost_usd", "duration_s", "error")})
        cost += float(out.get("cost_usd") or 0.0)
        if out["task_state"] == "DONE" and ":REPAIR:" in out["task"]:
            if policy["build"]:
                continue  # Autopilot will run the trusted build itself at the gate
            reason = (f"repair {out['task']} DONE by the debugger; confirm with the trusted build: "
                      f"craftctl request-build {pid}; craftctl decide <id> grant; craftctl build {pid} --approval-id <id>")
            break
        if out["task_state"] in HUMAN_NEEDED:
            rep = out.get("repair") or {}
            if rep.get("task") and not rep.get("exhausted"):
                continue  # the controller opened a repair task; keep going, the debugger is next
            if out.get("auto_retry"):
                continue  # a format failure was requeued with the reason; run it again
            if out["task_state"] == "WAITING_USER" and out["task"].endswith(":SPEC"):
                continue  # the spec proposal is in; the gate step decides (approve if authorised and no questions)
            needs = (out.get("handoff") or {}).get("needs_user") or []
            reason = f"{out['task_state']} on {out['task']}" + (": " + "; ".join(needs) if needs else "")
            if rep.get("exhausted"):
                reason = "repair loop exhausted: " + rep.get("error", "")
            break
    store.add_event(pid, "controller", "ORCHESTRATE_STOPPED", {"reason": reason, "runs": len(runs), "cost_usd": round(cost, 4), "gates": gates})
    return {"project": pid, "runs": runs, "gates": gates, "total_cost_usd": round(cost, 4), "elapsed_s": round(time.time() - started, 1),
            "stopped_because": reason, "stale_runs_reconciled": stale}


def _source_changed(store: Store, pid: str) -> None:
    """Accepted edits mean the source differs from what any evidence was observed on."""
    proj = store.project(pid)
    if proj["status"] in ("BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        store.update_project(pid, status="SOURCE_GENERATED_UNVERIFIED")
        store.add_event(pid, "controller", "VERIFICATION_RESET", {"reason": "source revised; previous evidence applies to an earlier manifest"})


def accept_run_changes(store: Store, run_id: str) -> dict:
    """USER-ONLY: accept the files a given run reported as changed, after reviewing its handoff."""
    for p in store.projects():
        for r in store.runs(p["id"]):
            if r["id"] == run_id:
                files = (r["handoff"] or {}).get("changed_files") or []
                if not files:
                    raise StateError(f"Run {run_id} reported no changed files")
                root = Path(p["root"])
                out = accept_changes(root, run_id=run_id, actor="user", changed=files)
                store.add_event(p["id"], "user", "CHANGES_ACCEPTED", {"run": run_id, **out})
                if out["accepted"]:
                    _source_changed(store, p["id"])
                return out | {"project": p["id"], "task": r["task_id"]}
    raise StateError(f"Run not found: {run_id}")


def _reopen_build(store: Store, pid: str) -> None:
    """New content after a build: the BUILD and GAME tasks must run again on the new source."""
    for tid in (f"{pid}:BUILD", f"{pid}:GAME"):
        t = next((x for x in store.tasks(pid) if x["id"] == tid), None)
        if t and t["state"] == "DONE":
            with store.tx() as con:
                con.execute("UPDATE tasks SET state='BACKLOG',version=version+1,lease_owner=NULL,lease_expiry=NULL WHERE id=?", (tid,))
                store.event(con, pid, "controller", "TASK_REOPENED", {"task": tid, "reason": "new content"})
    store.refresh_ready(pid)
