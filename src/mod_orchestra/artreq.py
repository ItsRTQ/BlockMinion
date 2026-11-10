"""Art for what the coder invents: coder -> designer -> coder.

The interpreter cannot foresee every visible thing a mechanic needs (the glob a mob spits, the icon of a new status effect, a
particle). The coder builds the mechanic with its OWN placeholder textures, never a vanilla one, and lists them in its handoff
as `art_needed`. When that task is DONE the controller checks the list and queues two tasks: ART (designer) paints each texture
at its exact size in models/art/, in the art direction of what it belongs to; ARTWIRE (coder, after ART) makes sure everything
uses the painted textures and builds. ART's DONE is checked here (size, real colour, not the placeholder) before anything is
copied into assets/.

An existing feature that already borrows vanilla visuals gets the same treatment through an ARTPASS: a coder task that only
gives those visuals their own placeholders and lists them.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

ART_DIR = "models/art"
KINDS = ("item", "projectile", "effect_icon", "particle", "entity", "block", "gui", "other")
MAX_ASSETS = 12
ID = re.compile(r"^[a-z][a-z0-9_]{1,47}$")

CODER_ART_RULE = [
    "Art: this mod never borrows vanilla visuals for what it adds. Everything visible you add (a projectile, an item, a status-effect icon, a particle,",
    "an entity texture, a GUI element) gets its OWN texture under src/main/resources/assets/<mod_id>/textures/. Create each one as a placeholder PNG of",
    "the size it needs (a flat colour is fine: the designer paints it after you), wire it in completely (models, renderers, registrations, lang), and",
    "list it in your handoff as `art_needed`: [{\"id\": snake_case, \"kind\": one of " + ", ".join(KINDS) + ", \"path\": the PNG path from the project root,",
    "\"size\": [width, height], \"for\": [identifiers of the mobs/items it belongs to], \"what\": how it is seen in the game and what it is}].",
    "Do not list mob models or the icons of items that are in the spec: the controller designs those already.",
    "Animation contract: every item you create that has gameplay moments (a weapon, a tool, a wand, anything used or swung) extends <the mod's package>.model3d.Item3DBase",
    "(or, when it must extend another base such as SwordItem, implements GeoItem by copying Item3DBase's four members). From day one its code emits each moment",
    "with <the mod's package>.model3d.Item3DActions.event(stack, holder, \"<name>\") (and eventEnd for one that lasts): it does nothing until a 3D model with that clip exists.",
    "List the moments in your handoff as `animation_events`: [{\"item\": id, \"name\": snake_case, \"when\": what happens in the game at that moment,",
    "\"loop\": true only if it lasts}], and the items that are Item3DBase/GeoItem as `geo_items`: [ids]. The designer animates exactly those names.",
]
EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
EVENTS_FILE = ".mod-orchestra/animation-events.json"


def events_store(ws: Path) -> dict:
    f = ws / EVENTS_FILE
    try:
        d = json.loads(f.read_text(encoding="utf8")) if f.is_file() else {}
    except ValueError:
        d = {}
    d.setdefault("events", {}); d.setdefault("geo_items", [])
    return d


def declared_events(ws: Path, item: str) -> dict[str, dict]:
    """{name: {when, loop}} the coder declared for an item."""
    return dict(events_store(ws)["events"].get(item) or {})


def is_geo_item(ws: Path, item: str) -> bool:
    return item in events_store(ws)["geo_items"]


def record_contract(store: Store, pid: str, task_id: str, handoff: dict) -> dict | None:
    """Keep the coder's animation_events and geo_items; drop malformed entries with the reason."""
    ws = Path(store.project(pid)["root"])
    raw_events, raw_geo = handoff.get("animation_events") or [], handoff.get("geo_items") or []
    if not raw_events and not raw_geo:
        return None
    d = events_store(ws)
    kept, dropped = [], {}
    for i, e in enumerate(raw_events if isinstance(raw_events, list) else []):
        if not isinstance(e, dict):
            dropped[f"#{i}"] = "not an object"; continue
        item, name = str(e.get("item", "")), str(e.get("name", "")).strip().lower()
        when = " ".join(str(e.get("when", "")).split())[:300]
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", item) or not EVENT_NAME.match(name):
            dropped[f"{item}.{name}" or f"#{i}"] = "item id and snake_case name needed"; continue
        if not when:
            dropped[f"{item}.{name}"] = "say what happens in the game at that moment"; continue
        d["events"].setdefault(item, {})[name] = {"when": when, "loop": bool(e.get("loop")), "task": task_id}
        kept.append(f"{item}.{name}")
    geo = [str(x) for x in raw_geo if isinstance(x, str) and re.fullmatch(r"[a-z][a-z0-9_]{1,49}", x)] if isinstance(raw_geo, list) else []
    d["geo_items"] = sorted(set(d["geo_items"]) | set(geo))
    (ws / EVENTS_FILE).parent.mkdir(parents=True, exist_ok=True)
    (ws / EVENTS_FILE).write_text(json.dumps(d, indent=2) + "\n", encoding="utf8")
    store.add_event(pid, "controller", "ANIM_EVENTS_DECLARED", {"task": task_id, "events": kept, "geo_items": geo, "dropped": dropped})
    return {"events": kept, "geo_items": geo, "dropped": dropped}


def _tid(store: Store, pid: str, kind: str, card: str) -> str:
    base = f"{pid}:{kind}:{card}"
    existing = {t["id"] for t in store.tasks(pid)}
    if base not in existing:
        return base
    n = 2
    while f"{base}:{n}" in existing:
        n += 1
    return f"{base}:{n}"


def _png_size(raw: bytes) -> tuple[int, int]:
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) < 24:
        raise InputError("not a PNG")
    return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")


def parse_art_needed(store: Store, pid: str, handoff: dict) -> tuple[list[dict], dict[str, str]]:
    """The coder's `art_needed`, checked: each entry points at a placeholder PNG that exists inside this mod's textures, at the
    size it declares. Returns (accepted entries, {id or index: why it was dropped})."""
    raw = handoff.get("art_needed") or []
    if not isinstance(raw, list):
        return [], {"art_needed": "must be a list"}
    ws = Path(store.project(pid)["root"])
    root = f"src/main/resources/assets/{pid}/textures/"
    ok, dropped, seen = [], {}, set()
    for i, e in enumerate(raw[:MAX_ASSETS]):
        key = str(e.get("id")) if isinstance(e, dict) and e.get("id") else f"#{i}"
        if not isinstance(e, dict):
            dropped[key] = "not an object"; continue
        ident, kind, path = str(e.get("id", "")), str(e.get("kind", "")), str(e.get("path", "")).replace("\\", "/")
        if not ID.match(ident) or ident in seen:
            dropped[key] = "id must be unique snake_case"; continue
        if kind not in KINDS:
            dropped[key] = f"kind must be one of {KINDS}"; continue
        if not path.startswith(root) or not path.endswith(".png") or ".." in path.split("/"):
            dropped[key] = f"path must be a .png under {root}"; continue
        size = e.get("size")
        if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and 4 <= v <= 256 for v in size)):
            dropped[key] = "size must be [width, height], 4-256 each"; continue
        f = ws / path
        try:
            actual = _png_size(f.read_bytes())
        except (OSError, InputError):
            dropped[key] = f"no placeholder PNG at {path}"; continue
        if list(actual) != size:
            dropped[key] = f"the placeholder is {actual[0]}x{actual[1]}, not {size[0]}x{size[1]}"; continue
        what = " ".join(str(e.get("what", "")).split())[:400]
        if not what:
            dropped[key] = "say what it is and how it is seen in the game"; continue
        fors = [str(x) for x in (e.get("for") or []) if isinstance(x, str)][:6]
        seen.add(ident)
        ok.append({"id": ident, "kind": kind, "path": path, "size": size, "for": fors, "what": what,
                   "placeholder": hashlib.sha256(f.read_bytes()).hexdigest()})
    if len(raw) > MAX_ASSETS:
        dropped["…"] = f"only the first {MAX_ASSETS} are taken"
    return ok, dropped


def _owner_kind(spec, ident: str) -> str | None:
    if any(m.identifier == ident for m in spec.mobs):
        return "mob"
    f = next((f for f in spec.features if f.identifier == ident), None)
    if f is not None:
        return f.kind
    if any(fd.identifier == ident for fd in spec.foods):
        return "food"
    return None


ART_INSTRUCTIONS = """
## Your job on this task (designer — art for what the coder built)
The coder implemented a mechanic and gave every visible thing it added its own placeholder texture. Paint each texture listed
below and write it to `models/art/<id>.png` at EXACTLY the size given (the in-game code already points at it; a different size
breaks it). Use a small stdlib-only Python script (zlib/struct, no PIL) kept at `models/art/paint.py`.
Each one belongs to something in this mod: paint it in that thing's art direction (given below with it) so they read as one
creature or one set. Where the mob's skin exists (`models/<mob>.png`), read it and take its colours. Make it read at its real size
in the game: a clear shape, a darker edge, light from the top-left, transparent background unless it fills a whole surface.
The controller refuses a texture that is missing, not the declared size, a single flat colour, or still the placeholder.
Report every PNG path in `changed_files`. Do not touch `src/`: the controller installs them, and the coder checks the wiring afterwards.
"""


def request_art(store: Store, pid: str, source_task: str, card: str, assets: list[dict]) -> dict:
    """Queue ART (designer) and ARTWIRE (coder, after ART) for the coder's accepted art_needed."""
    from .art import brief as art_brief
    from .models import user_words, theme_block
    from .specedit import _load
    spec = _load(store, pid)
    art_task, wire_task = _tid(store, pid, "ART", card), _tid(store, pid, "ARTWIRE", card)
    lines = [ART_INSTRUCTIONS, user_words(store, pid), theme_block(store, pid), "\n## Textures to paint"]
    for a in assets:
        lines.append(f"\n### {a['id']} ({a['kind']}, {a['size'][0]}x{a['size'][1]}) -> models/art/{a['id']}.png")
        lines.append(f"what it is: {a['what']}")
        for owner in a["for"]:
            kind = _owner_kind(spec, owner)
            if kind:
                lines.append(f"it belongs to {owner} ({kind}); its art direction:\n" + art_brief(spec, kind, owner))
                if kind == "mob":
                    lines.append(f"its skin: models/{owner}.png (if it exists)")
    store.add_task(pid, art_task, "designer", f"Paint the art the coder needs ({len(assets)} texture{'s' if len(assets) != 1 else ''})")
    wire = [f"The designer painted the textures your earlier task ({source_task}) asked for; the controller installed them at:"]
    wire += [f"- {a['path']} ({a['kind']}, {a['size'][0]}x{a['size'][1]}): {a['what']}" for a in assets]
    wire += ["Make sure everything uses them: item/entity/particle models and renderers point at these textures, nothing falls back to a vanilla texture,",
             "registrations and lang names are in place. Do not repaint or resize them. Change nothing else.",
             "Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    store.add_task(pid, wire_task, "coder", f"Wire the painted art in ({card})", after=[art_task])
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (art_task, "\n".join(lines)))
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (wire_task, "\n".join(wire)))
    store.add_event(pid, "controller", "ART_REQUESTED", {"task": art_task, "wire_task": wire_task, "source": source_task, "card": card, "assets": assets})
    return {"art_task": art_task, "wire_task": wire_task, "assets": [a["id"] for a in assets]}


def after_coder_done(store: Store, pid: str, task_id: str, handoff: dict) -> dict | None:
    """On a FEATURE / CHANGE / ARTPASS DONE: keep the animation contract and queue the art the coder listed. Never fails the coder's
    task: what cannot be taken is recorded with the reason."""
    record_contract(store, pid, task_id, handoff)
    assets, dropped = parse_art_needed(store, pid, handoff)
    if dropped:
        store.add_event(pid, "controller", "ART_REQUEST_DROPPED", {"task": task_id, "dropped": dropped})
    if not assets:
        return None
    card = task_id.split(":")[2] if task_id.count(":") >= 2 else "feature"
    return request_art(store, pid, task_id, card, assets)


def install_art(store: Store, pid: str, task_id: str, *, run_id: str, actor: str) -> dict:
    """Check models/art/<id>.png for every texture of the ART task and copy the ones that pass over the coder's placeholders."""
    from .fabric import accept_changes
    from .models import _png_info
    ev = next((e for e in store.events(pid, 500) if e["kind"] == "ART_REQUESTED" and e["payload"].get("task") == task_id), None)
    if ev is None:
        raise StateError(f"No art request recorded for {task_id}")
    ws = Path(store.project(pid)["root"])
    installed, rejected = [], {}
    for a in ev["payload"]["assets"]:
        src = ws / ART_DIR / f"{a['id']}.png"
        if not src.is_file():
            rejected[a["id"]] = "missing"; continue
        raw = src.read_bytes()
        try:
            w, h, _alpha, ncol = _png_info(raw)
        except InputError as exc:
            rejected[a["id"]] = str(exc); continue
        if [w, h] != a["size"]:
            rejected[a["id"]] = f"{w}x{h}, need {a['size'][0]}x{a['size'][1]}"; continue
        if hashlib.sha256(raw).hexdigest() == a["placeholder"]:
            rejected[a["id"]] = "still the placeholder"; continue
        if ncol < 2:
            rejected[a["id"]] = "a single flat colour"; continue
        (ws / a["path"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, ws / a["path"]); installed.append(a["path"])
    if rejected:   # all or nothing: the wiring task expects every texture
        raise InputError("art deliverables rejected: " + "; ".join(f"{k}: {v}" for k, v in rejected.items()))
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=installed)
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "controller", "ART_INSTALLED", {"task": task_id, "run": run_id, "installed": installed, "wire_task": ev["payload"]["wire_task"]})
    return {"installed": installed, "accepted": accepted["accepted"], "wire_task": ev["payload"]["wire_task"]}


def request_art_pass(store: Store, pid: str, card_id: str) -> dict:
    """USER-ONLY: a feature that already borrows vanilla visuals (a mob spitting slime balls) gets its own art: a coder task that gives
    each borrowed visual its own placeholder and lists it; ART and ARTWIRE follow on their own."""
    from .modmap import mod_map
    if store.project(pid)["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first")
    card = next((c for c in mod_map(store, pid)["cards"] if c["id"] == card_id), None)
    if card is None or card["kind"] == "vanilla":
        raise InputError(f"Unknown card {card_id!r}")
    task_id = _tid(store, pid, "ARTPASS", card_id)
    brief = [f"Give the feature \"{card['title']}\" its own art. Read its files (the mod map in your packet lists them): {', '.join(card.get('files') or []) or 'see the mod map'}.",
             "Find every visible thing it shows with a texture, model, item or particle that is not this mod's own (a vanilla one reused).",
             "Give each its own placeholder texture and switch the code to it, keeping the behaviour exactly as it is. Change nothing else."]
    brief += CODER_ART_RULE
    brief += ["If everything it shows is already this mod's own, change nothing and leave `art_needed` empty.",
              "Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    store.add_task(pid, task_id, "coder", f"Own art for: {card['title']}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(brief)))
    store.add_event(pid, "user", "ART_PASS_REQUESTED", {"card": card_id, "task": task_id})
    return {"task": task_id, "card": card_id, "next": {"action": "dispatch", "payload": {"task": task_id}}}
