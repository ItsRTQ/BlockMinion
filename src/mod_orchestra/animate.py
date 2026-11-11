"""Animate: tell the designer what an animation does and the coder when it plays, without touching the model's shape.

The user describes each animation in two parts: WHAT it does (for the designer) and WHEN it plays (for the coder, verbatim).
The designer gets an animation-only brief; geometry, UV and texture are locked. On DONE `shape_changes` compares the new
exports with a snapshot taken before the run: the model must show exactly the same cubes at rest (Bedrock cube origins are
absolute, so the designer may move cubes into new bones to animate them separately, as long as every cube keeps its
data and the chain of rest rotations above it) and exactly the same texture pixels. Then the model is installed like any
delivery and the animations that need code go to a coder with the user's WHEN for each one.

Targets: a 3D item (actions become GeoItem triggers), a 3D projectile (one animation: how it moves in flight), a mob
(new one-shots and movement states go into its entity class; idle/walk/attack it already plays), and, after
`blocks3d`, a 3D block.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from collections import Counter
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

NAME = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
KINDS = ("item", "projectile", "mob", "block")
MOB_BUILTIN = ("idle", "walk", "attack")
MAX_ANIMS = 10


def _files(store: Store, pid: str, kind: str, ident: str) -> tuple[Path, str]:
    """(folder, stem) of the target's exports."""
    from . import model3d
    from .models import MODEL_DIR
    ws = Path(store.project(pid)["root"])
    if kind == "item":
        return ws / model3d.DIR, ident
    if kind == "projectile":
        return ws / model3d.PDIR, ident
    if kind == "mob":
        return ws / MODEL_DIR, ident
    if kind == "block":
        from .blocks3d import BDIR
        return ws / BDIR, ident
    raise InputError(f"kind must be one of {KINDS}")


def _check_target(store: Store, pid: str, kind: str, ident: str) -> None:
    from . import model3d
    proj = store.project(pid)
    ws = Path(proj["root"])
    if proj["status"] not in model3d.GENERATED:
        raise StateError("Generate the project first")
    if kind == "item" and ident not in model3d.items3d(ws, pid):
        raise InputError(f"{ident!r} is not a 3D item yet: Make it 3D first")
    if kind == "projectile" and not model3d.projectile_assets(store, pid).get(ident, {}).get("model3d"):
        raise InputError(f"{ident!r} is not a 3D projectile yet: Make it 3D first")
    if kind == "mob" and ident not in {m["identifier"] for m in proj["spec"].get("mobs", [])}:
        raise InputError(f"Unknown mob {ident!r}")
    if kind == "block":
        from .blocks3d import blocks3d
        if ident not in blocks3d(ws, pid):
            raise InputError(f"{ident!r} is not a 3D block yet: Make it 3D first")
    folder, stem = _files(store, pid, kind, ident)
    missing = [f"{stem}.{e}" for e in ("bbmodel", "geo.json", "animation.json", "png") if not (folder / f"{stem}.{e}").is_file()]
    if missing:
        raise StateError(f"{ident} has no finished model to animate (missing: {', '.join(missing)})")


def coerce_anims(kind: str, anims: list, remove: list | None = None) -> tuple[list[dict], list[str]]:
    out, seen = [], set()
    if not isinstance(anims, list) or not (anims or remove):
        raise InputError("Describe at least one animation (what it does and when it plays), or one to remove")
    if len(anims) > MAX_ANIMS:
        raise InputError(f"At most {MAX_ANIMS} animations per request")
    if kind == "projectile" and len(anims) > 1:
        raise InputError("a projectile has one animation: how it moves while it flies")
    for a in anims:
        if not isinstance(a, dict):
            raise InputError("Each animation is {name, what, when, loop}")
        name = str(a.get("name", "")).strip().lower().replace(" ", "_")
        what = " ".join(str(a.get("what", "")).split())[:800]
        when = " ".join(str(a.get("when", "")).split())[:300]
        if kind == "projectile":
            name, when = "idle", "the whole time it flies"
        if not NAME.match(name):
            raise InputError(f"animation name {name!r}: short snake_case (letters, digits, _)")
        if name in seen:
            raise InputError(f"two animations are called {name!r}")
        if not what:
            raise InputError(f"say what {name!r} does")
        builtin = kind == "mob" and name in MOB_BUILTIN
        if not when and not builtin and name != "idle":
            raise InputError(f"say when {name!r} plays (the coder plays it at that moment)")
        loop = bool(a.get("loop")) or name in ("idle", "walk") or kind == "projectile"
        seen.add(name)
        player = " ".join(str(a.get("player", "")).split())[:800] if kind == "item" else ""
        out.append({"name": name, "what": what, "when": when or ("always, at rest" if name == "idle" else "as it does today"), "loop": loop,
                    **({"player": player} if player else {})})
    rm = [str(r).strip() for r in (remove or []) if str(r).strip()]
    bad = [r for r in rm if not NAME.match(r) or (kind == "mob" and r in MOB_BUILTIN)]
    if bad:
        raise InputError(f"cannot remove {bad}" + (" (a mob always needs idle, walk and attack)" if kind == "mob" else ""))
    return out, rm


ANIMATE_INSTRUCTIONS = """
## Your job on this task (designer — animate an existing model)
Only animate. The model `<folder>/<stem>.bbmodel` is finished: its shape, UV and texture are locked. The controller compares
your exports with a snapshot taken before this run and refuses the install if any cube (position, size, UV, rotation) or any
texture pixel changed. You MAY regroup cubes into new bones so a part can move on its own (create the bone with its pivot where
the part should hinge, then move the existing cubes into it unchanged; a new bone has no rest rotation).
Make each animation listed below with `bbmodel_geckolib_upsert_animation`, named exactly `animation.<stem>.<name>`; loop it
only where the list says so. Animate what the user describes, not more; keep every other clip as it is unless it is listed
for removal (`bbmodel_geckolib_remove_animation`). Look at each one with `bbmodel_render` / `bbmodel_sample_pose` before you
finish, then re-export the animations (and the geometry, if you regrouped) with `overwrite: true`, and render
`<folder>/<stem>_render.png`. Report the files in `changed_files`. Never touch `src/`.
"""


def request_animate(store: Store, pid: str, kind: str, ident: str, anims: list, remove: list | None = None, notes: str = "", *, escalate: bool = True) -> dict:
    """USER-ONLY: ask the designer for animations on an existing model; geometry and texture stay locked. A moment the code does not
    have yet goes to the coder first (a change request on the thing's card) and the designer's task waits behind it."""
    from .models import user_words
    from . import escalate as _esc
    if kind not in KINDS:
        raise InputError(f"kind must be one of {KINDS}")
    _check_target(store, pid, kind, ident)
    anims, rm = coerce_anims(kind, anims, remove)
    plan, first_task = [], None
    missing = _esc.missing_moments(store, pid, kind, ident, anims) if escalate else []
    if missing:
        card = _esc.card_for(store, pid, kind, ident)
        if card is None:
            raise InputError(f"the code has no moment for {[a['name'] for a in missing]} and {ident!r} has no card to change; ask for it as a feature first")
        first_task = _esc.request_moments(store, pid, kind, ident, missing, card)
        plan.append({"task": first_task, "role": "coder", "why": "the code has no moment for " + ", ".join(a["name"] for a in missing) + ": it is made first and emitted"})
    folder, stem = _files(store, pid, kind, ident)
    ws = Path(store.project(pid)["root"])
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    snap = ws / ".mod-orchestra/animate" / kind / ident / stamp
    snap.mkdir(parents=True, exist_ok=True)
    for e in ("geo.json", "animation.json", "png"):
        shutil.copyfile(folder / f"{stem}.{e}", snap / f"before.{e}")
    base = f"{pid}:ANIMATE:{kind}:{ident}"
    n = sum(1 for t in store.tasks(pid) if t["id"] == base or t["id"].startswith(base + ":")) + 1
    task_id = base if n == 1 else f"{base}:{n}"
    rel = str(folder.relative_to(ws)).replace("\\", "/")
    lines = [ANIMATE_INSTRUCTIONS.replace("<folder>", rel).replace("<stem>", stem), user_words(store, pid, ident),
             f"\n## The animations the user asked for ({kind} `{ident}`), in their words"]
    for a in anims:
        lines.append(f"- animation.{stem}.{a['name']} ({'loops' if a['loop'] else 'plays once'}); what it does: {a['what']}; it plays: {a['when']}")
    if rm:
        lines.append("Remove these clips: " + ", ".join(f"animation.{stem}.{r}" for r in rm))
    bodies = [a for a in anims if a.get("player")]
    if bodies:
        from . import playeranim
        playeranim.stage_rig(ws)
        lines += ["", "## The player's body (Player Animation Library)",
                  f"Some of these actions also move the player holding it. Open `{playeranim.PDIR}/{playeranim.STEM}.bbmodel` (the player rig: bones "
                  + ", ".join(playeranim.PAL_BONES) + "; +X is the player's right, -Z forward; never rename, move or re-pivot them), add one clip per action",
                  "named exactly as below (no `animation.` prefix: the name becomes the animation's id), keyed in time with the item's clip of the same action,",
                  f"and export the rig's animations to `{playeranim.PDIR}/{playeranim.STEM}.animation.json` with `overwrite: true`. Keep its other clips."]
        lines += [f"- {playeranim.anim_key(ident, a['name'])}: {a['player']}" for a in bodies]
    if kind == "mob":
        lines.append("The mob must keep animation.<stem>.idle, .walk and .attack (its entity plays them).".replace("<stem>", stem))
    if notes.strip():
        lines += ["", "## More from the user", notes.strip()[:1500]]
    if missing:
        lines.append("The moments listed above that the code did not have are being added by a coder before you; name your clips exactly as listed.")
    store.add_task(pid, task_id, "designer", f"Animate {ident}", after=[first_task] if first_task else None)
    plan.append({"task": task_id, "role": "designer", "why": "the animations, once the moments exist" if missing else "the animations"})
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(lines)))
    # relative to the project: events hide the user's home directory, so an absolute path under it (Windows) would not read back
    store.add_event(pid, "user", "ANIMATE_REQUESTED", {"task": task_id, "kind": kind, "ident": ident, "anims": anims, "remove": rm,
                                                       "snapshot": str(snap.relative_to(ws)).replace("\\", "/"), "after": first_task})
    return {"task": task_id, "kind": kind, "ident": ident, "anims": [a["name"] for a in anims], "plan": plan, "first": first_task or task_id,
            "next": {"action": "dispatch", "payload": {"task": first_task or task_id}}}


# ------------------------------------------------------------------------------------------------ the shape lock

def _first_person(bones: dict, b: dict) -> bool:
    cur, guard = b, 0
    while cur is not None and guard < 64:
        if str(cur.get("name", "")).startswith("fp_"):
            return True
        cur = bones.get(cur.get("parent")) if cur.get("parent") else None
        guard += 1
    return False


def _shape(geo: dict) -> Counter:
    """What the model looks like at rest outside first person: fp_* parts (first-person arms) are free to add or change."""
    g = geo["minecraft:geometry"][0]
    bones = {b["name"]: b for b in g["bones"]}
    sig = Counter()
    for b in g["bones"]:
        if _first_person(bones, b):
            continue
        chain, cur, guard = [], b, 0
        while cur is not None and guard < 64:
            rot = cur.get("rotation") or [0, 0, 0]
            if any(abs(float(v)) > 1e-6 for v in rot):
                chain.append((tuple(cur.get("pivot") or [0, 0, 0]), tuple(rot)))
            cur = bones.get(cur.get("parent")) if cur.get("parent") else None
            guard += 1
        for c in b.get("cubes") or []:
            sig[(json.dumps(c, sort_keys=True), json.dumps(chain))] += 1
    return sig


def shape_changes(before_geo: dict, after_geo: dict, before_png: bytes, after_png: bytes) -> list[str]:
    from .skin import decode_png
    out = []
    try:
        a, b = _shape(before_geo), _shape(after_geo)
    except (KeyError, IndexError, TypeError):
        return ["the geometry is not GeckoLib geometry"]
    if a != b:
        lost, extra = sum((a - b).values()), sum((b - a).values())
        out.append(f"the model's shape changed ({lost} cube(s) gone or moved, {extra} new or moved): animating may regroup cubes into new bones but never change them")
    bd, ad = before_geo["minecraft:geometry"][0]["description"], after_geo["minecraft:geometry"][0]["description"]
    if (bd.get("texture_width"), bd.get("texture_height")) != (ad.get("texture_width"), ad.get("texture_height")):
        out.append("the texture layout changed")
    try:
        (bw, bh, bpx), (aw, ah, apx) = decode_png(before_png), decode_png(after_png)
    except ValueError:
        return out + ["the texture is not a readable PNG"]
    if (bw, bh) != (aw, ah):
        return out + ["the texture size changed"]
    from .modeledit import _strips
    scale = max(1, bw // max(1, int(ad.get("texture_width") or bw)))
    free = []   # the texture of first-person parts may be painted
    for geo in (before_geo, after_geo):
        g = geo["minecraft:geometry"][0]; bones = {b["name"]: b for b in g["bones"]}
        free += [r for b in g["bones"] if _first_person(bones, b) for c in b.get("cubes") or [] for r in _strips(c)]
    changed = 0
    for y in range(bh):
        for x in range(bw):
            i = (y * bw + x) * 4
            if bpx[i:i + 4] != apx[i:i + 4] and not any(x0 * scale <= x < x1 * scale and y0 * scale <= y < y1 * scale for x0, y0, x1, y1 in free):
                changed += 1
    if changed:
        out.append(f"texture pixels changed ({changed})")
    return out


def latest_request(store: Store, pid: str, task_id: str) -> dict | None:
    return next((e["payload"] for e in store.events(pid, 500) if e["kind"] == "ANIMATE_REQUESTED" and e["payload"].get("task") == task_id), None)


def whens(store: Store, pid: str, kind: str, ident: str) -> dict[str, str]:
    """The user's WHEN for each animation of a target, newest request wins."""
    out: dict[str, str] = {}
    for e in reversed(store.events(pid, 500)):
        p = e["payload"]
        if e["kind"] == "ANIMATE_REQUESTED" and p.get("kind") == kind and p.get("ident") == ident:
            for a in p.get("anims", []):
                out[a["name"]] = a["when"]
            for r in p.get("remove", []):
                out.pop(r, None)
    return out


def player_actions(store: Store, pid: str, ident: str) -> dict[str, str]:
    """Actions of a 3D item that also move the player's body (newest request wins)."""
    out: dict[str, str] = {}
    for e in reversed(store.events(pid, 500)):
        p = e["payload"]
        if e["kind"] == "ANIMATE_REQUESTED" and p.get("kind") == "item" and p.get("ident") == ident:
            for a in p.get("anims", []):
                if a.get("player"):
                    out[a["name"]] = a["player"]
                else:
                    out.pop(a["name"], None)
            for r in p.get("remove", []):
                out.pop(r, None)
    return out


def check_delivery(store: Store, pid: str, task_id: str) -> dict:
    """Shape locked, every requested clip present (loop as asked), every removed clip gone."""
    req = latest_request(store, pid, task_id)
    if req is None:
        raise StateError(f"No animation request recorded for {task_id}")
    folder, stem = _files(store, pid, req["kind"], req["ident"])
    snap = Path(store.project(pid)["root"]) / req["snapshot"]
    try:
        after_geo = json.loads((folder / f"{stem}.geo.json").read_text(encoding="utf8"))
        anims = json.loads((folder / f"{stem}.animation.json").read_text(encoding="utf8")).get("animations") or {}
        problems = shape_changes(json.loads((snap / "before.geo.json").read_text(encoding="utf8")), after_geo,
                                 (snap / "before.png").read_bytes(), (folder / f"{stem}.png").read_bytes())
    except (OSError, ValueError) as exc:
        raise InputError(f"cannot read the exports: {exc}") from None
    for a in req["anims"]:
        clip = anims.get(f"animation.{stem}.{a['name']}")
        if not clip or not clip.get("bones"):
            problems.append(f"animation.{stem}.{a['name']} is missing or has no keyframes")
        elif bool(clip.get("loop") is True) != a["loop"]:
            problems.append(f"animation.{stem}.{a['name']} must {'loop' if a['loop'] else 'play once (loop off)'}")
    for r in req["remove"]:
        if f"animation.{stem}.{r}" in anims:
            problems.append(f"animation.{stem}.{r} should have been removed")
    if problems:
        raise InputError("animation delivery refused: " + "; ".join(problems[:8]))
    return req


def install_animate(store: Store, pid: str, task_id: str, *, run_id: str, actor: str) -> dict:
    """Check, then install through the target's own installer; animations that need code go to a coder with the user's WHEN."""
    from . import model3d
    req = check_delivery(store, pid, task_id)
    kind, ident = req["kind"], req["ident"]
    if kind == "item":
        bodies = [a for a in req["anims"] if a.get("player")]
        if bodies:   # check the player's clips before anything is installed
            from . import playeranim
            playeranim.validate(Path(store.project(pid)["root"]), [playeranim.anim_key(ident, a["name"]) for a in bodies])
        out = model3d.install_item3d(store, pid, task_id, ident, run_id=run_id, actor=actor)
        coder = out.get("anim_task")
        if bodies:
            pa = playeranim.install(store, pid, [playeranim.anim_key(ident, a["name"]) for a in bodies], run_id=run_id, actor=actor)
            out["installed"] = list(out.get("installed", [])) + pa["installed"]
            if out.get("actions"):
                coder = model3d.request_actions_wiring(store, pid, ident, out["actions"], out["animated"], out.get("loops"), extra=pa["coder"])
    elif kind == "projectile":
        out = model3d.install_proj3d(store, pid, task_id, ident, run_id=run_id, actor=actor, wire=False)
        coder = None
    elif kind == "mob":
        from .models import install_model
        out = install_model(store, pid, ident, run_id=run_id, actor=actor)
        coder = request_mob_wiring(store, pid, ident)
    else:
        from .blocks3d import install_block3d
        out = install_block3d(store, pid, task_id, ident, run_id=run_id, actor=actor)
        coder = out.get("anim_task")
    store.add_event(pid, "controller", "ANIMATE_APPLIED", {"task": task_id, "kind": kind, "ident": ident, "anims": [a["name"] for a in req["anims"]],
                                                           "coder_task": coder})
    return {"installed": out.get("installed", []), "coder_task": coder, "kind": kind, "ident": ident}


# ------------------------------------------------------------------------------------------------ mobs: the coder plays them

def mob_brief(package: str, mob_class: str, mob: str, todo: dict[str, dict]) -> list[str]:
    once = {n: a for n, a in todo.items() if not a["loop"]}
    states = {n: a for n, a in todo.items() if a["loop"]}
    lines = [f"The mob `{mob}` has new animations in assets/<mod>/animations/entity/{mob}.animation.json. Make its entity play each one at the moment",
             f"the user described. The class is {package}.entity.{mob_class}Entity (a GeoEntity; its \"main\" controller plays idle, walk and attack)."]
    if states:
        lines += ["Movement states and other loops (they play while the condition holds): in the \"main\" controller's predicate, before walk and idle,",
                  "check each condition and `return state.setAndContinue(RawAnimation.begin().thenLoop(\"animation." + mob + ".<name>\"));` for the one that holds:"]
        lines += [f"   - {n}: while {a['when']}" for n, a in states.items()]
        lines += ["   Use the entity's own state for the conditions (isInWater(), isSprinting(), onGround(), getDeltaMovement(), its target...);",
                  "   if a condition needs state the entity does not track yet, track it (a synced data field when the client must know it)."]
    if once:
        lines += ["One-shots (they play once when something happens): add a second controller",
                  '   `controllers.add(new AnimationController<>(this, "actions", 0, state -> PlayState.STOP)' +
                  "".join(f'.triggerableAnim("{n}", RawAnimation.begin().thenPlay("animation.{mob}.{n}"))' for n in once) + ");`",
                  '   and call `triggerAnim("actions", "<name>")` on the server at each moment:']
        lines += [f"   - {n}: {a['when']}" for n, a in once.items()]
    lines += ["Do not change the model files, idle, walk or attack, or anything else. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    return lines


def request_mob_wiring(store: Store, pid: str, mob: str) -> str | None:
    """A coder task for the mob's animations that need code (everything except idle/walk/attack), with the user's WHEN; rewrites a waiting one."""
    from .geckolib import class_name
    from .spec import read_spec
    spec = read_spec(store.project(pid)["spec"])
    m = next(x for x in spec.mobs if x.identifier == mob)
    loops: dict[str, bool] = {}
    for e in reversed(store.events(pid, 500)):
        p = e["payload"]
        if e["kind"] == "ANIMATE_REQUESTED" and p.get("kind") == "mob" and p.get("ident") == mob:
            for a in p.get("anims", []):
                loops[a["name"]] = a["loop"]
            for r in p.get("remove", []):
                loops.pop(r, None)
    when = whens(store, pid, "mob", mob)
    todo = {n: {"loop": loops[n], "when": when[n]} for n in loops if n not in MOB_BUILTIN}
    if not todo:
        return None
    base = f"{pid}:MOBANIM:{mob}"
    tasks = [t for t in store.tasks(pid) if t["id"] == base or t["id"].startswith(base + ":")]
    waiting = next((t for t in tasks if t["state"] in ("BACKLOG", "READY")), None)
    task_id = waiting["id"] if waiting else (base if not tasks else f"{base}:{len(tasks) + 1}")
    if waiting is None:
        store.add_task(pid, task_id, "coder", f"Play the new animations of {m.label}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(mob_brief(spec.package, class_name(m), mob, todo))))
    return task_id
