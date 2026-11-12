"""Ask: the user says what they want in their own words; a planner turns it into an ordered plan of the requests that already exist.

The planner (an agent with no tools: it only reads the context the controller gives it) returns `plan` in its handoff: an
ordered list of steps, each one an ACTION the controller knows how to request, with a target and the user's words. The
controller applies the plan by calling the same functions the buttons call (change request, feature, Make it 3D, Animate
with its escalation, art pass, modify), chaining each step after the ones it depends on. Nothing the planner says bypasses
a check: it chooses and orders; the controller requests, validates and installs as always. Steps the controller cannot apply
are reported, never guessed.
"""
from __future__ import annotations

import json
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

ACTIONS = ("change", "feature", "make_3d", "animate", "art_pass", "modify_model")
MAX_STEPS = 8
MAX_ASK = 2000

PLANNER_INSTRUCTIONS = """
## Your job on this task (planner — turn the user's request into a plan)
Read the request and the project below, then answer with a plan: the smallest ordered list of steps, each one of these actions,
that gives the user what they asked for on top of what already exists. Do not do any of the work yourself; do not invent content
the user did not ask for; when the request is unclear, ask with status WAITING_USER and a question in needs_user instead of
guessing. Order: code before art that depends on it (a mechanic before the animation of its moments; an entity before its model),
art before code that only wires it. Keep each step's `text` in the user's own words plus only what the step needs to be concrete.
Actions and their fields:
- change: {"card": an existing card id, "cards": [more card ids, optional], "text": what to change}   (any behaviour, mechanic, or fix on
  something that exists; list every card the same change applies to, so the coder does it once and consistently)
- feature: {"title": short, "text": what it does, "acceptance": [testable sentences]}   (new behaviour that belongs to no card)
- make_3d: {"kind": "item|block|projectile", "target": id, "text": notes for the designer}
- animate: {"kind": "item|mob|block|projectile", "target": id, "anims": [{"name": snake, "what": ..., "when": ..., "loop": bool}]}
  (moments the code lacks are sent to a coder first by the controller; you need not add a change step for that)
- art_pass: {"card": card id}   (a feature that borrows vanilla visuals gets its own)
- modify_model: {"target": mob id, "text": what to change on the model, "may_change": [bones]}
Report the plan in your handoff as `"plan": [{"step": 1, "action": ..., "after": [step numbers], ...fields}]`, status DONE.
"""


def project_context(store: Store, pid: str) -> str:
    """What the planner can see: cards, 3D things, declared moments, pending tasks."""
    from .artreq import events_store
    from .model3d import _index
    from .modmap import mod_map
    proj = store.project(pid); ws = Path(proj["root"])
    m = mod_map(store, pid)
    lines = ["## The project", f"id: {pid}; status: {proj['status']}", "cards (id · kind · title):"]
    lines += [f"- {c['id']} · {c['kind']} · {c.get('title', '')}" + (f" · produces {c['produces']}" if c.get("produces") else "") for c in m["cards"] if c.get("kind") != "vanilla"]
    _, idx = _index(ws, pid)
    if idx.get("items") or idx.get("blocks") or idx.get("projectiles"):
        lines.append("3D already: items " + ", ".join(i["id"] for i in idx.get("items", [])) + "; blocks " + ", ".join(b["id"] for b in idx.get("blocks", [])) + "; projectiles " + ", ".join(idx.get("projectiles", [])))
    ev = events_store(ws)["events"]
    if ev:
        lines.append("moments the code emits: " + "; ".join(f"{item}: {', '.join(names)}" for item, names in ev.items()))
    open_tasks = [t for t in store.tasks(pid) if t["state"] in ("READY", "BACKLOG", "RUNNING", "LEASED", "WAITING_USER")]
    if open_tasks:
        lines.append("open tasks: " + ", ".join(f"{t['id']} ({t['state']})" for t in open_tasks[:12]))
    return "\n".join(lines)


def request_ask(store: Store, pid: str, text: str) -> dict:
    """USER-ONLY: a free-text request becomes a planner task."""
    text = (text or "").strip()
    if not text:
        raise InputError("Say what you want, in your own words")
    if len(text) > MAX_ASK:
        raise InputError(f"Keep it under {MAX_ASK} characters")
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first; before that, the spec is the place to ask")
    n = sum(1 for t in store.tasks(pid) if ":ASK:" in t["id"]) + 1
    task_id = f"{pid}:ASK:{n}"
    brief = PLANNER_INSTRUCTIONS + "\n" + project_context(store, pid) + "\n\n## The user's request (their words, verbatim)\n" + text
    store.add_task(pid, task_id, "planner", f"Plan: {text[:60]}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, brief))
    store.add_event(pid, "user", "ASK_REQUESTED", {"task": task_id, "text": text[:600]})
    return {"task": task_id, "next": {"action": "dispatch", "payload": {"task": task_id}}}


def apply_plan(store: Store, pid: str, task_id: str, handoff: dict) -> dict:
    """Turn the planner's steps into real requests, chained; report what could not be applied."""
    from .animate import request_animate
    from .artreq import request_art_pass
    from .blocks3d import request_block3d
    from .model3d import request_item3d, request_proj3d
    from .modeledit import request_model_edit
    from .modmap import request_change, request_feature
    raw = handoff.get("plan")
    if not isinstance(raw, list) or not raw:
        raise InputError("the planner returned no plan")
    created: dict[int, list[str]] = {}
    applied, skipped = [], []
    for i, step in enumerate(raw[:MAX_STEPS], start=1):
        if not isinstance(step, dict):
            skipped.append({"step": i, "why": "not an object"}); continue
        n = int(step.get("step") or i); action = str(step.get("action", "")).lower()
        after = [t for k in (step.get("after") or []) if isinstance(k, int) for t in created.get(k, [])]
        try:
            if action == "change":
                tid = request_change(store, pid, str(step.get("card", "")), str(step.get("text", "")), [str(c) for c in (step.get("cards") or [])])["task"]; tids = [tid]
            elif action == "feature":
                tid = request_feature(store, pid, title=str(step.get("title") or step.get("text", ""))[:80], description=str(step.get("text", "")),
                                      acceptance=[str(a) for a in (step.get("acceptance") or [])], after=after or None)["task"]; tids = [tid]
            elif action == "make_3d":
                kind, target, notes = str(step.get("kind", "item")), str(step.get("target", "")), str(step.get("text", ""))
                out = request_block3d(store, pid, target, notes) if kind == "block" else request_proj3d(store, pid, target, notes) if kind == "projectile" else request_item3d(store, pid, target, notes)
                tids = [out["task"]]
            elif action == "animate":
                out = request_animate(store, pid, str(step.get("kind", "item")), str(step.get("target", "")), list(step.get("anims") or []))
                tids = [s["task"] for s in out["plan"]]
            elif action == "art_pass":
                tids = [request_art_pass(store, pid, str(step.get("card", "")))["task"]]
            elif action == "modify_model":
                tids = [request_model_edit(store, pid, str(step.get("target", "")), str(step.get("text", "")), may_change=list(step.get("may_change") or []))["task"]]
            else:
                skipped.append({"step": n, "why": f"unknown action {action!r}"}); continue
        except (InputError, StateError) as exc:
            skipped.append({"step": n, "action": action, "why": str(exc)[:300]}); continue
        if after and action != "feature":   # the step's first task waits for the steps it depends on (feature took `after` itself)
            store.wait_for(tids[0], after)
        created[n] = tids
        applied.append({"step": n, "action": action, "tasks": tids})
    store.add_event(pid, "controller", "PLAN_APPLIED", {"task": task_id, "applied": applied, "skipped": skipped})
    first = next((a["tasks"][0] for a in applied), None)
    return {"applied": applied, "skipped": skipped, "first": first}
