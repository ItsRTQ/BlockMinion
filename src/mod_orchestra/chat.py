"""The project's main panel: a live chat on the left, the plan on the right, one button, Launch.

The user talks to a coordinator in their own words. Each turn is one coordinator task (an agent with read-only tools)
that receives the project (cards, 3D things, the moments the code emits, open tasks), the conversation so far and the
current plan, and answers with a reply for the chat and, when it understood enough, a `plan`: the ordered steps the tool
knows how to request (the same closed set Ask uses), each with its target and the user's words, plus `result` (what the
user will have at the end, briefly). Nothing runs until the user presses Launch: the plan is then applied through
`ask.apply_plan`, the same path the buttons take, one task after another, and the chat says what started.

The coordinator asks when something is unclear, says when a request does not fit the thing it names (a reload on a door is
probably a misclick), and shapes cross-cutting work as one configurable mechanic applied to many pieces rather than one
change per piece. Before Launch the controller checks what it can check without judgement: every target exists and its kind
fits the action. The goal of the whole panel is that the user and the tool agree on the end goal before anything is spent.
"""
from __future__ import annotations

import json
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

PLAN_KEY = "chat_plan"
MAX_TEXT = 4000
HISTORY_TURNS = 24

COORDINATOR_INSTRUCTIONS = """
## Your job on this task (coordinator — talk with the user, shape the plan)
You are the project's coordinator. The user talks to you in their own words; you make sure the two of you agree on the end
goal before anything is built, and you turn it into a plan the tool can run. You do no work yourself: no code, no art.
Answer in the user's language (the one they write in). Reply to the newest message in the conversation below.
- When something is unclear or has more than one reasonable reading, ask one short question instead of guessing.
- When a request does not fit the thing it names (an action that makes no sense for that kind of thing), say so and ask;
  it may be a misclick.
- When the user describes behaviour or looks, help them decide: say briefly how such a thing usually behaves or looks in
  the game, and what you would do, so they can confirm or correct it.
- When the same change touches several pieces, shape it as ONE configurable mechanic applied to all of them (a base with
  parameters: rates, damage, capacity; each piece only its values, name and icon), not one change per piece: say that in
  the plan's step text so the coder builds it that way.
- Code before art that depends on it (a mechanic before the animations of its moments; an entity before its model); art
  before code that only wires it. A moment the code lacks is handled by the tool when an `animate` step runs: you need
  not add a change step for that.
Actions you may plan (each step: {"step": n, "action": ..., "after": [step numbers], ...fields}):
- change: {"card": card id, "cards": [more card ids, optional], "text": what to change}
- feature: {"title": short, "text": what it does, "acceptance": [testable sentences]}
- make_3d: {"kind": "item|block|projectile", "target": id, "text": notes for the designer}
- animate: {"kind": "item|mob|block|projectile", "target": id, "anims": [{"name": snake, "what": ..., "when": ..., "loop": bool}]}
- art_pass: {"card": card id}
- modify_model: {"target": mob id, "text": what to change on the model, "may_change": [bones]}
Your handoff: status DONE with `"reply"`: your message to the user (plain text, short paragraphs, no markdown headings), and
`"plan"`: either null (not enough agreed yet) or {"result": one or two sentences on what the user will have at the end,
"steps": [...]}. Keep the previous plan's steps when the user did not change them; drop the plan (null) when the user
says they do not want it. Never claim something will run: only the user's Launch runs it.
"""


def current_plan(store: Store, pid: str) -> dict | None:
    return store.get_setting(pid, PLAN_KEY, None)


def _context(store: Store, pid: str) -> str:
    from .ask import project_context
    return project_context(store, pid)


def _transcript(store: Store, pid: str) -> str:
    msgs = store.chat_messages(pid, HISTORY_TURNS)
    lines = ["## The conversation so far (oldest first)"]
    for m in msgs:
        who = {"user": "USER", "coordinator": "YOU", "system": "TOOL"}.get(m["role"], m["role"].upper())
        lines.append(f"{who}: {m['text']}")
    return "\n".join(lines)


def send(store: Store, pid: str, text: str) -> dict:
    """USER-ONLY: a message to the coordinator. Records it and creates the coordinator's turn (a task to dispatch)."""
    text = (text or "").strip()
    if not text:
        raise InputError("Say something")
    if len(text) > MAX_TEXT:
        raise InputError(f"Keep it under {MAX_TEXT} characters")
    store.project(pid)
    msg_id = store.chat_add(pid, "user", text)
    n = sum(1 for t in store.tasks(pid) if ":CHAT:" in t["id"]) + 1
    task_id = f"{pid}:CHAT:{n}"
    plan = current_plan(store, pid)
    brief = [COORDINATOR_INSTRUCTIONS, _context(store, pid), "",
             "## The current plan (on the user's screen)", json.dumps(plan, indent=1) if plan else "(none yet)", "", _transcript(store, pid)]
    store.add_task(pid, task_id, "coordinator", f"Chat: {text[:50]}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(brief)))
    store.add_event(pid, "user", "CHAT_SENT", {"task": task_id, "message": msg_id, "text": text[:300]})
    return {"task": task_id, "message": msg_id, "next": {"action": "dispatch", "payload": {"task": task_id}}}


def coerce_plan(store: Store, pid: str, raw) -> dict | None:
    """The coordinator's plan, checked for what needs no judgement: shape, known actions, targets that exist with a fitting kind."""
    from .ask import ACTIONS, MAX_STEPS
    from .modmap import mod_map
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
        raise InputError("plan must be {result, steps}")
    cards = {c["id"]: c for c in mod_map(store, pid)["cards"]}
    ws = Path(store.project(pid)["root"])
    from .model3d import items3d, projectile_assets
    from .blocks3d import blocks3d
    spec = store.project(pid)["spec"]
    mobs = {m["identifier"] for m in spec.get("mobs", [])}
    steps, problems = [], []
    for i, s in enumerate(raw["steps"][:MAX_STEPS], start=1):
        if not isinstance(s, dict):
            problems.append(f"step {i}: not an object"); continue
        action = str(s.get("action", "")).lower()
        if action not in ACTIONS:
            problems.append(f"step {i}: unknown action {action!r}"); continue
        target, kind = str(s.get("target", "") or ""), str(s.get("kind", "") or "")
        if action in ("change", "art_pass"):
            for c in [s.get("card")] + list(s.get("cards") or []):
                if c and (str(c) not in cards or cards[str(c)].get("kind") == "vanilla"):
                    problems.append(f"step {i}: no card {c!r}")
        elif action == "make_3d":
            if kind == "block" and target not in {c for c, v in cards.items() if v.get("kind") == "block"}:
                problems.append(f"step {i}: {target!r} is not a block")
            elif kind == "projectile" and target not in projectile_assets(store, pid):
                problems.append(f"step {i}: {target!r} is not a projectile with its own art")
            elif kind in ("item", "") and target not in {c for c, v in cards.items() if v.get("kind") in ("item", "food", "material")} and not any(target.startswith(c + "_") for c, v in cards.items() if v.get("kind") == "material"):
                problems.append(f"step {i}: {target!r} is not an item")
        elif action == "animate":
            ok = {"mob": target in mobs, "item": target in items3d(ws, pid), "block": target in blocks3d(ws, pid), "projectile": target in projectile_assets(store, pid)}.get(kind)
            if not ok:
                problems.append(f"step {i}: {target!r} is not a 3D {kind or '?'} (Make it 3D first)" if kind != "mob" else f"step {i}: no mob {target!r}")
        elif action == "modify_model" and target not in mobs:
            problems.append(f"step {i}: no mob {target!r}")
        s = dict(s); s["step"] = int(s.get("step") or i); steps.append(s)
    return {"result": " ".join(str(raw.get("result", "")).split())[:600], "steps": steps, "problems": problems}


def receive(store: Store, pid: str, task_id: str, handoff: dict) -> dict:
    """The coordinator's turn is DONE: record the reply and the plan it proposed."""
    reply = " ".join(str(handoff.get("reply", "")).split())[:MAX_TEXT] or "(the coordinator sent no reply)"
    try:
        plan = coerce_plan(store, pid, handoff.get("plan"))
    except InputError as exc:
        plan = None; reply += f"\n\n(The plan it sent could not be read: {exc})"
    if "plan" in handoff:   # the coordinator may keep, change or drop the plan; absent means unchanged
        if plan is None:
            store.set_setting(pid, PLAN_KEY, None, actor="controller")
        else:
            store.set_setting(pid, PLAN_KEY, plan | {"turn": task_id, "launched": None}, actor="controller")
    store.chat_add(pid, "coordinator", reply, meta={"plan": bool(plan)}, task_id=task_id)
    store.add_event(pid, "controller", "CHAT_REPLY", {"task": task_id, "plan": bool(plan), "problems": (plan or {}).get("problems", [])})
    return {"reply": reply, "plan": plan}


def launch(store: Store, pid: str) -> dict:
    """USER-ONLY: run the plan on the screen, one task after another, through the same requests the buttons make."""
    from .ask import apply_plan
    plan = current_plan(store, pid)
    if not plan or not plan.get("steps"):
        raise StateError("There is no plan to launch; talk with the coordinator first")
    if plan.get("problems"):
        raise InputError("The plan has steps the tool cannot run as written: " + "; ".join(plan["problems"][:5]) + ". Tell the coordinator.")
    if plan.get("launched"):
        raise StateError("This plan was already launched; ask the coordinator for the next one")
    out = apply_plan(store, pid, plan.get("turn") or f"{pid}:CHAT", {"plan": plan["steps"]})
    store.set_setting(pid, PLAN_KEY, plan | {"launched": out}, actor="user")
    lines = ["Launched. " + (plan.get("result") or "")]
    lines += [f"- step {a['step']} ({a['action']}): {', '.join(a['tasks'])}" for a in out["applied"]]
    if out["skipped"]:
        lines += [f"- step {s['step']} could not start: {s['why']}" for s in out["skipped"]]
    store.chat_add(pid, "system", "\n".join(lines), meta={"launched": out})
    store.add_event(pid, "user", "PLAN_LAUNCHED", {"applied": out["applied"], "skipped": out["skipped"], "first": out["first"]})
    return out | {"next": ({"action": "dispatch", "payload": {"task": out["first"]}} if out["first"] else None)}


def discard(store: Store, pid: str) -> dict:
    store.set_setting(pid, PLAN_KEY, None, actor="user")
    store.chat_add(pid, "system", "Plan discarded.")
    return {"plan": None}


def view(store: Store, pid: str) -> dict:
    """What the panel shows: messages, the plan, whether a coordinator turn is still running, and a cost hint."""
    from .model3d import designer_cost
    running = [t for t in store.tasks(pid) if ":CHAT:" in t["id"] and t["state"] in ("READY", "RUNNING", "LEASED", "BACKLOG")]
    plan = current_plan(store, pid)
    return {"messages": store.chat_messages(pid), "plan": plan, "thinking": bool(running), "pending_turn": running[0]["id"] if running else None,
            "designer_cost": designer_cost(store)}
