"""What the tool is doing right now and what it finished lately, for the UI's sidebar dots and its floating activity banner.

Pure functions over the store and the UI server's in-memory job registry, so they are testable without HTTP. A task id becomes a sentence a person
reads ("Designer · model of Brute") and a *target* the UI can open: the tab, the sub-tab and the card or mob to focus.
"""
from __future__ import annotations

import time

from .state import Store

JOB_LABELS = {"dispatch": "Agent", "orchestrate": "Autopilot", "build": "Building with Gradle", "gametest": "Running the GameTests",
              "server-smoke": "Server smoke test", "run-client": "Game client running"}
CONTROLLER_TARGETS = {"build": {"tab": "verify"}, "gametest": {"tab": "verify"}, "server-smoke": {"tab": "verify"}, "run-client": {"tab": "verify"}}
RECENT_SECONDS = 15 * 60


def _words(slug: str) -> str:
    return slug.replace("_", " ").strip()


def describe_task(task_id: str, role: str | None = None) -> dict:
    """{label, target} for a task id such as `infectious:MODEL:brute`: a sentence, and the place of the UI where its result is seen."""
    tail = task_id.split(":", 1)[1] if ":" in task_id else task_id
    parts = tail.split(":")
    kind, arg = parts[0], (parts[1] if len(parts) > 1 else "")
    who = (role or "agent").capitalize()
    if kind == "SPEC":
        return {"label": "Interpreter · reading your idea and proposing the spec", "target": {"tab": "spec"}}
    if kind == "MODEL":
        return {"label": f"Designer · model of {_words(arg)}", "target": {"tab": "features", "sub": "mobs", "focus": f"mob:{arg}"}}
    if kind == "ADD_MOB":
        return {"label": f"{who} · adding the mob {_words(arg)}", "target": {"tab": "features", "sub": "mobs", "focus": f"mob:{arg}"}}
    if kind in ("SPRITES", "ARMOR", "ARMOR3D", "ADD_ORE"):
        what = {"SPRITES": "item icons", "ARMOR": f"worn armor of {_words(arg)}", "ARMOR3D": f"3D armor of {_words(arg)}", "ADD_ORE": f"ore {_words(arg)}"}[kind]
        return {"label": f"{who} · {what}", "target": {"tab": "features", "sub": "items"}}
    if kind == "FEATURE":
        return {"label": f"Coder · {_words(arg)}", "target": {"tab": "map", "focus": arg}}
    if kind == "CHANGE":
        return {"label": f"Coder · change on {_words(arg)}", "target": {"tab": "map", "focus": arg}}
    if kind == "REPAIR":
        return {"label": "Debugger · repairing the build", "target": {"tab": "activity"}}
    return {"label": f"{who} · {_words(' '.join(parts).lower())}", "target": {"tab": "activity"}}


def _running_run(store: Store, pid: str) -> dict | None:
    runs = [r for r in store.runs(pid) if r["state"] == "RUNNING"]
    return runs[-1] if runs else None


def _last_run(store: Store, pid: str, since: float) -> dict | None:
    runs = [r for r in store.runs(pid) if (r.get("created_at") or 0) >= since - 1]
    return runs[-1] if runs else None


def _step(store: Store, pid: str, job: str, run: dict | None) -> dict:
    if run is not None:
        d = describe_task(run["task_id"], run.get("role"))
        return {"task": run["task_id"], "role": run.get("role"), "runtime": run.get("provider"), "label": d["label"], "target": d["target"], "since": run.get("created_at")}
    return {"task": None, "role": "controller", "runtime": None, "label": JOB_LABELS.get(job, job), "target": CONTROLLER_TARGETS.get(job, {"tab": "activity"}), "since": None}


def running_now(store: Store, inflight: dict[str, dict], now: float | None = None) -> dict[str, dict]:
    """pid -> what is happening in that project right now (only projects with a job in flight)."""
    now = now or time.time()
    out = {}
    for pid, entry in list(inflight.items()):
        if not entry["thread"].is_alive():
            continue
        out[pid] = {"running": True, "job": entry["job"], "job_label": JOB_LABELS.get(entry["job"], entry["job"]), "elapsed_s": round(now - entry["started"], 1),
                    "step": _step(store, pid, entry["job"], _running_run(store, pid))}
    return out


def finished_entry(store: Store, pid: str, entry: dict) -> dict:
    """What a job that just ended should show in the banner: the last agent it ran, and whether it worked."""
    run = _last_run(store, pid, entry["started"])
    step = _step(store, pid, entry["job"], run)
    result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
    task_state = result.get("task_state")
    failed = bool(entry.get("error")) or task_state == "FAILED" or (run is not None and run.get("state") == "FAILED")
    waiting = task_state == "WAITING_USER"
    return {"project": pid, "job": entry["job"], "job_label": JOB_LABELS.get(entry["job"], entry["job"]), "state": "failed" if failed else "waiting" if waiting else "done",
            "finished_at": entry.get("finished") or time.time(), "elapsed_s": round((entry.get("finished") or time.time()) - entry["started"], 1), "step": step,
            "error": (entry.get("error") or result.get("error") or "")[:300] or None}


def snapshot(store: Store, inflight: dict[str, dict], finished: list[dict], now: float | None = None) -> dict:
    """The payload of GET /api/activity: what runs now, and what finished in the last quarter of an hour (newest first)."""
    now = now or time.time()
    names = {p["id"]: p.get("name") or p["id"] for p in store.projects()}
    projects = running_now(store, inflight, now)
    for pid, a in projects.items():
        a["name"] = names.get(pid, pid)
    recent = [dict(f, name=names.get(f["project"], f["project"])) for f in reversed(finished) if now - f["finished_at"] <= RECENT_SECONDS][:12]
    return {"now": now, "projects": projects, "recent": recent}
