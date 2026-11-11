"""When a request needs something that does not exist yet, the thing is made first: a limitation becomes work, not a question.

Piece 1 (before a designer runs): an animation plays at a MOMENT of the game ("when the player reloads it", "while it is in
water", "when a player opens it"). The controller knows which moments the code emits: for items the declared animation
events (the contract), for mobs the built-in idle/walk/attack plus declared ones, for blocks the declared ones, for projectiles
only their flight. A requested animation whose moment the code does not have goes to the coder FIRST, as a change request on
the thing's own card: make the moment exist with the minimum behaviour the user's words need, emit it, declare it. The
designer's task is chained after it, so it animates a moment that is real. The same rule for every kind of thing.
"""
from __future__ import annotations

from pathlib import Path

from .state import Store
from .validation import InputError

MOB_BUILTIN = {"idle", "walk", "attack"}


def code_moments(store: Store, pid: str, kind: str, ident: str) -> set[str]:
    """The animation moments the code already emits for this thing."""
    from .artreq import declared_events
    ws = Path(store.project(pid)["root"])
    declared = set(declared_events(ws, ident))
    if kind == "mob":
        return MOB_BUILTIN | declared
    if kind == "projectile":
        return {"idle"}
    return declared


def card_for(store: Store, pid: str, kind: str, ident: str) -> str | None:
    """The Mod Map card that owns this thing: the custom card that produces it, else its own spec card, else (projectiles) the card
    whose art it is."""
    from .modmap import mod_map
    cards = mod_map(store, pid)["cards"]
    if kind == "projectile":
        from .model3d import projectile_assets
        card = (projectile_assets(store, pid).get(ident) or {}).get("card")
        return card if any(c["id"] == card for c in cards) else None
    for c in cards:
        if c.get("kind") == "custom" and ident in (c.get("produces") or []):
            return c["id"]
    if any(c["id"] == ident and c.get("kind") != "vanilla" for c in cards):
        return ident
    # a material's tool or armour piece (<material>_<piece>) belongs to the material's card
    for c in cards:
        if c.get("kind") == "material" and ident.startswith(c["id"] + "_"):
            return c["id"]
    return None


def missing_moments(store: Store, pid: str, kind: str, ident: str, anims: list[dict]) -> list[dict]:
    """The requested animations whose moment the code does not emit (idle and a mob's built-ins never count)."""
    have = code_moments(store, pid, kind, ident)
    return [a for a in anims if a["name"] not in have and a["name"] != "idle" and not (kind == "mob" and a["name"] in MOB_BUILTIN)]


def _emit_text(kind: str, ident: str) -> str:
    if kind == "item":
        return (f"The item `{ident}` must be a `<the mod's package>.model3d.Item3DBase` (or implement GeoItem the same way; migrate it if it is a plain Item): "
                "emit each moment with `Item3DActions.event(stack, holder, \"<name>\")` and, for one that lasts, `Item3DActions.eventEnd` when it ends.")
    if kind == "mob":
        return (f"In `{ident}`'s entity: a one-shot moment is `triggerAnim(\"actions\", \"<name>\")` on the server (add an \"actions\" controller with "
                "`triggerableAnim(\"<name>\", RawAnimation.begin().thenPlay(\"animation." + ident + ".<name>\"))` if there is none); a moment that lasts is a state "
                "in the \"main\" controller's predicate, before walk and idle, playing `animation." + ident + ".<name>` as a loop while it holds.")
    if kind == "block":
        return (f"For the block `{ident}`: `<the mod's package>.model3d.Block3DEntity.trigger(level, pos, \"<name>\")` on the server at the moment "
                "(and `.stop` when a lasting one ends); interactions go in a class that extends Block3DBlock, registered for the block.")
    return "Projectiles have one animation, their flight; nothing to emit."


def request_moments(store: Store, pid: str, kind: str, ident: str, missing: list[dict], card: str) -> str:
    """One coder change request, on the thing's own card, that makes every missing moment real. Returns the task id."""
    from .modmap import request_change
    lines = [f"Animation moments the code does not have yet, for the {kind} `{ident}`. The user asked for animations that play at these moments,",
             "in their words (what happens in the game, and whether it lasts):"]
    for a in missing:
        lines.append(f"- `{a['name']}`{' (lasts while it holds)' if a['loop'] else ' (happens once)'}: {a['when']}")
    lines += ["Make each moment exist in the game with the MINIMUM behaviour the user's words need, on top of what the thing already does:",
              "if the mechanic behind the moment does not exist, add it, as small as it can be while being real; keep everything else as it is.",
              _emit_text(kind, ident),
              "Declare every moment in your handoff as `animation_events` (item, name, when, loop) and the thing in `geo_items` where it applies.",
              "The designer animates these exact names right after you; do not touch models, textures or assets/<mod>/model3d/."]
    return request_change(store, pid, card, "\n".join(lines))["task"]


# ------------------------------------------------------------------------------------------------ piece 2: from inside a run

NEED_ROLES = ("coder",)


def _own_card(store: Store, pid: str, task_id: str) -> str | None:
    from .modmap import mod_map
    parts = task_id.split(":")
    cid = parts[2] if len(parts) >= 3 and parts[1] in ("FEATURE", "CHANGE", "MODEL", "ITEM3D", "BLOCK3D", "ANIMATE") else None
    if parts[1:2] == ["ANIMATE"] and len(parts) >= 4:
        cid = parts[3]
    cards = {c["id"]: c for c in mod_map(store, pid)["cards"]}
    if cid in cards and cards[cid].get("kind") != "vanilla":
        return cid
    for kind in ("item", "mob", "block"):
        c = card_for(store, pid, kind, cid) if cid else None
        if c:
            return c
    return None


def from_needs(store: Store, pid: str, task: dict, handoff: dict) -> dict | None:
    """An agent reported BLOCKED with `needs`: make each need a task for its role, park the agent's task behind them, and tell it
    what to expect when it runs again. Returns {created: [...], waiting: task id, unmet: [...]} or None when there is nothing to do."""
    from .modmap import request_change, request_feature
    raw = handoff.get("needs")
    if not isinstance(raw, list) or not raw:
        return None
    created, unmet = [], []
    for i, n in enumerate(raw[:6]):
        if not isinstance(n, dict):
            continue
        role = str(n.get("role", "coder")).lower()
        what = " ".join(str(n.get("what", "")).split())[:600]; why = " ".join(str(n.get("why", "")).split())[:400]
        target = str(n.get("target", "") or "").strip()
        if not what:
            continue
        if role not in NEED_ROLES:
            unmet.append({"role": role, "what": what, "why": why}); continue
        card = None
        if target:
            for kind in ("item", "mob", "block", "projectile"):
                card = card_for(store, pid, kind, target)
                if card:
                    break
            if card is None:
                try:
                    from .modmap import mod_map
                    if any(c["id"] == target and c.get("kind") != "vanilla" for c in mod_map(store, pid)["cards"]):
                        card = target
                except Exception:
                    card = None
        card = card or _own_card(store, pid, task["id"])
        text = [f"A {task['role']} working on `{task['id']}` could not continue because this does not exist yet:",
                f"- what must exist: {what}", f"- why that task needs it: {why}" if why else "",
                "Make it exist with the MINIMUM behaviour those words need, on top of what is already there; keep everything else as it is.",
                "Declare what you add as usual: animation_events (moments the code emits), geo_items, art_needed (anything visible that needs its own art).",
                f"The {task['role']} runs again right after you, building on what you made."]
        text = "\n".join(t for t in text if t)
        if card:
            tid = request_change(store, pid, card, text)["task"]
        else:
            tid = request_feature(store, pid, title=what[:60], description=text, acceptance=[what[:120]])["task"]
        created.append({"task": tid, "role": role, "what": what, "card": card})
    if created:
        store.wait_for(task["id"], [c["task"] for c in created])
        note = ["", "## Since your last run",
                "You stopped because something did not exist yet. These tasks were created to make it, and they are done before you run again:"]
        note += [f"- {c['task']} ({c['role']}): {c['what']}" for c in created]
        note += ["Look at what they changed (the project's files and `orchestra_project_status`) and continue from there; do not redo their work."]
        prev = store.task_instructions(task["id"])
        with store.tx() as con:
            con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task["id"], prev + "\n" + "\n".join(note)))
    store.add_event(pid, "controller", "NEEDS_ESCALATED", {"task": task["id"], "created": created, "unmet": unmet})
    return {"created": created, "waiting": task["id"] if created else None, "unmet": unmet}
