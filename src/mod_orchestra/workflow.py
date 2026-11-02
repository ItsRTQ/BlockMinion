"""Coordinator: typed actions, bounded planning, approval and deterministic execution."""
from __future__ import annotations
import json
import os
import shutil
import hashlib
from pathlib import Path
from .config import PROJECTS, PROFILE, save_json
from .fabric import generate, validate_generated
from .spec import interpret, read_spec
from .state import Store, StateError
from .validation import InputError, project_id


def new_project(store: Store, *, name: str, mod_id: str, package: str, idea: str, profile: str | None = None) -> dict:
    pid = project_id(mod_id)
    spec = interpret(name=name, mod_id=pid, package=package, idea=idea, profile=profile or PROFILE["id"])
    if not spec.features:   # free-text idea: nothing the regex grammar could extract; the interpreter agent fills the spec
        spec = spec.__class__(**{**spec.__dict__, "questions": [
            "Idea recorded as free text. Run `craftctl dispatch <id> --task <id>:SPEC` (or `craftctl orchestrate <id>`) so the interpreter proposes a spec, "
            "or rewrite the idea as 'items: a, b; blocks: c; tab: Label'."]})
    root = (PROJECTS / pid).resolve()
    if root.exists() and any(root.iterdir()):
        raise InputError("Workspace already exists; never overwrite an existing project")
    result = store.create_project(pid, str(root), name, spec.to_dict())
    return {"id": result["id"], "root": result["root"], "spec": result["spec"], "questions": spec.questions}


def plan_project(store: Store, pid: str) -> dict:
    project = store.project(pid)
    spec = read_spec(project["spec"])
    tasks = [
        {"id": f"{pid}:SPEC", "role": "interpreter", "title": "Review, resolve questions, approve idea", "ready": True},
        {"id": f"{pid}:SCAFFOLD", "role": "controller", "title": "Generate the Fabric starter workspace (craftctl generate / Autopilot)"},
    ]
    edges = [(f"{pid}:SPEC", f"{pid}:SCAFFOLD")]
    for index, feat in enumerate(spec.features, 1):
        tid = f"{pid}:CONTENT:{index:02d}"
        tasks.append({"id": tid, "role": "controller", "title": f"Generate {feat.kind}: {feat.label} (generator)"})
        edges.append((f"{pid}:SCAFFOLD", tid))
    for mob in spec.mobs:
        tid = f"{pid}:MODEL:{mob.identifier}"
        tasks.append({"id": tid, "role": "designer", "title": f"Blockbench/GeckoLib model + idle/walk + texture for mob: {mob.label}"})
        edges.append((f"{pid}:SCAFFOLD", tid))
        edges.append((tid, f"{pid}:BUILD"))
    tasks.append({"id": f"{pid}:BUILD", "role": "controller", "title": "Trusted build through the controller (craftctl build / Autopilot); the debugger takes over on BUILD_FAILED"})
    tasks.append({"id": f"{pid}:GAME", "role": "user", "title": "Server smoke (controller) + client verification (you): record CLIENT_BOOT_PASS and CONTENT_VERIFIED"})
    if spec.features:
        edges.extend((f"{pid}:CONTENT:{i:02d}", f"{pid}:BUILD") for i in range(1, len(spec.features) + 1))
    elif not spec.mobs:
        edges.append((f"{pid}:SCAFFOLD", f"{pid}:BUILD"))
    edges.append((f"{pid}:BUILD", f"{pid}:GAME"))
    project_status = store.project(pid)["status"]
    store.set_tasks(pid, tasks, edges, replace=project_status in ("IDEA", "PLAN_READY"))
    store.update_project(pid, status="PLAN_READY")
    return {"project": pid, "tasks": tasks, "dependencies": edges, "blocking_questions": spec.questions,
            "note": "This is a bounded deterministic implementation plan, not a full AI-generated engineering plan."}


def approve_spec(store: Store, pid: str) -> None:
    project = store.project(pid)
    spec = read_spec(project["spec"])
    if spec.questions:
        raise StateError("Open questions remain; answer them with: craftctl answer " + pid + ' "<answer>" — ' + " | ".join(spec.questions))
    if project["spec_state"] != "DRAFT":
        raise StateError("Spec is already approved")
    store.update_project(pid, spec_state="APPROVED")
    # Replan on approval while no source exists: the spec may have changed since the first plan
    # (interpreter proposal, add-recipe/add-mob), and the plan must match what will be generated.
    plan_project(store, pid)
    tid = pid + ":SPEC"
    state = next((t["state"] for t in store.tasks(pid) if t["id"] == tid), None)
    if state in ("WAITING_USER", "FAILED", "BLOCKED"):   # an interpreter pass left it parked; approval closes it
        store.requeue(tid, "approved by user")
    task = store.claim(tid, "interpreter")
    if task is None or not store.finish(tid, "interpreter", task["version"], [{"kind": "SPEC_REVIEW", "value": hashlib.sha256(json.dumps(spec.to_dict(), sort_keys=True).encode()).hexdigest()}]):
        raise StateError("Failed to complete SPEC task")
    store.refresh_ready(pid)


def generate_project(store: Store, pid: str) -> dict:
    project = store.project(pid)
    if project["spec_state"] != "APPROVED":
        raise StateError("Spec approval required before generation")
    if project["status"] != "PLAN_READY":
        raise StateError("Generation is only allowed once per approved new project")
    t_id = pid + ":SCAFFOLD"
    lease = store.claim(t_id, "coder", ttl=600)
    if not lease:
        raise StateError(unavailable_message(store, t_id))
    try:
        output = generate(read_spec(project["spec"]), Path(project["root"]))  # validated in staging, installed atomically
    except Exception as exc:
        # generate() leaves nothing at the final path; give the lease back so a retry can run.
        store.release(t_id, "coder", lease["version"], f"generation failed: {exc}")
        raise
    if not store.finish(t_id, "coder", lease["version"], [{"kind": "STATIC_MANIFEST", "value": output["manifest"]}]):
        raise StateError("Scaffold lease expired")
    store.refresh_ready(pid)
    # Contents generated in one atomic generator step: record each as static evidence, never BUILD evidence.
    for task in store.tasks(pid):
        if ":CONTENT:" in task["id"]:
            lease = store.claim(task["id"], "generator", ttl=600)
            if lease is None:
                raise StateError("Content task unavailable")
            if not store.finish(task["id"], "generator", lease["version"], [{"kind": "STATIC_MANIFEST", "value": output["manifest"]}]):
                raise StateError("Content task lease expired")
    store.refresh_ready(pid)
    store.update_project(pid, status="SOURCE_GENERATED_UNVERIFIED")
    store.add_event(pid, "generator", "SOURCE_GENERATED", output)
    return output


def unavailable_message(store: Store, task_id: str) -> str:
    info = store.lease_info(task_id)
    if info is None:
        return f"Task {task_id} does not exist"
    if info["holder"]:
        return (f"Task {task_id} is {info['state']} by '{info['holder']}' for {info['seconds_left']}s more. "
                f"Wait, or run: craftctl release {task_id}")
    return f"Task {task_id} is {info['state']}, not READY"


def rmtree_long(path: Path) -> None:
    r"""shutil.rmtree that survives Windows MAX_PATH (Loom caches nest very deep): use the \\?\ prefix there."""
    target = str(path)
    if os.name == "nt" and not target.startswith("\\\\?\\"):
        target = "\\\\?\\" + target
    shutil.rmtree(target)


def delete_project(store: Store, pid: str, *, remove_workspace: bool) -> dict:
    """USER-ONLY. Removes the workspace first (only on explicit request and only inside PROJECTS), then the
    Footprint rows, so a failed directory removal never leaves an orphan directory without its record."""
    project = store.project(pid)
    root = Path(project["root"]).resolve()
    existed = root.is_dir()
    removed = False
    if remove_workspace and existed:
        projects_root = PROJECTS.resolve()
        if projects_root not in root.parents:
            raise StateError(f"Refusing to delete a directory outside {projects_root}: {root}")
        rmtree_long(root)
        removed = True
    result = store.delete_project(pid)
    result.update({"workspace": str(root), "workspace_existed": existed, "workspace_removed": removed})
    return result


def summary(store: Store, pid: str) -> dict:
    project = store.project(pid)
    manifest_file = Path(project["root"]) / ".mod-orchestra" / "generation-manifest.json"
    current_manifest = hashlib.sha256(manifest_file.read_bytes()).hexdigest() if manifest_file.is_file() else None
    tasks = store.tasks(pid)
    return {"id": pid, "name": project["name"], "root": project["root"],
            "status": project["status"], "spec_state": project["spec_state"], "spec": project["spec"],
            "tasks": [{"id": t["id"], "title": t["title"], "role": t["role"], "state": t["state"]} for t in tasks],
            "approvals": [{"id": a["id"], "kind": a["kind"], "state": a["state"], "description": a["description"]} for a in store.approvals(pid)],
            "evidence": [{"level": e["level"], "actor": e["actor"], "note": e["note"], "artifact_sha256": e["artifact_sha256"],
                          "created_at": e["created_at"], "current": e["manifest_sha256"] == current_manifest} for e in store.evidence(pid)],
            "runs_all": store.runs(pid),
            "events": store.events(pid, 40)}


def export_state_markdown(store: Store, pid: str) -> str:
    data = summary(store, pid)
    lines = ["# Project State", "", f"Project: {data['name']} ({pid})", f"Status: {data['status']}",
             f"Spec: {data['spec_state']}", "", "## Evidence"]
    lines += [f"- {e['level']} by {e['actor']}" + (f" — {e['note']}" if e["note"] else "")
              + (f" (sha256 {e['artifact_sha256'][:12]}…)" if e["artifact_sha256"] else "")
              for e in data["evidence"]] or ["- none recorded"]
    lines += ["", "## Task board"]
    for task in data["tasks"][:50]:
        lines.append(f"- {task['state']}: {task['id']} — {task['title']} [{task['role']}]")
    lines.extend(["", "## Recent events"])
    for event in data["events"][:10]:
        lines.append(f"- {event['kind']} by {event['actor']} (event {event['id']})")
    result = "\n".join(lines)[:7000] + "\n"
    # Deliberately bounded output. SQLite retains full event history.
    return result
