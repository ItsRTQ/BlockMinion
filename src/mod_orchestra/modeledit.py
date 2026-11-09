"""Modify an existing mob model instead of redesigning it, and bring in a model made outside the orchestra.

A *modification* ("add a tail") is a designer run with a short brief: the current model is the source of truth and only the
change is made. Before the run the controller snapshots the installed exports (geo, animation, texture); when the designer
reports DONE, `check_edit` compares the new exports with that snapshot and the install is refused if anything the user did
not open for change was touched: an existing bone (pivot, rotation, cubes, UV), its keyframes in an existing clip, a clip's
length or loop, or a pixel of an existing cube's texture. New bones, new cubes, new clips and new keyframes on new bones are
free. The user may open existing parts for change (`may_change`); the designer can never widen that on its own.

*Use my model* installs a .bbmodel the user made or downloaded (or re-installs their own Blockbench edits): the controller
exports geo and animations from it with the vendored Blockbench server's exporter, takes the texture embedded in it (or a PNG
given next to it), validates everything like a designer delivery and installs it as a user revision. A modification then works
on it like on any other model.
"""
from __future__ import annotations

import base64
import json
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

EDIT_DIR = ".mod-orchestra/model-edits"
EXPORTS = (("geo", "geo.json"), ("anim", "animation.json"), ("png", "png"), ("bbmodel", "bbmodel"))
MAX_REQUEST = 2000
MAX_IMPORT_BYTES = 5 * 1024 * 1024   # the UI posts base64 under ui.MAX_BODY


def _models(store: Store, pid: str) -> Path:
    from .models import MODEL_DIR
    return Path(store.project(pid)["root"]) / MODEL_DIR


def _mob_ids(store: Store, pid: str) -> set[str]:
    return {m["identifier"] for m in store.project(pid)["spec"].get("mobs", [])}


def current_bones(store: Store, pid: str, mob: str) -> list[str]:
    """Bone names of the mob's current model (models/<mob>.geo.json), in file order; [] before a model exists."""
    geo = _models(store, pid) / f"{mob}.geo.json"
    try:
        return [b["name"] for b in json.loads(geo.read_text(encoding="utf8"))["minecraft:geometry"][0]["bones"]]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return []


# ---------------------------------------------------------------------------------------------------- request

def _requeue_model(store: Store, pid: str, mob: str, reason: str) -> str:
    task_id = f"{pid}:MODEL:{mob}"
    task = next((t for t in store.tasks(pid) if t["id"] == task_id), None)
    if task is None:
        raise StateError(f"No MODEL task for {mob}; plan the project first")
    if task["state"] == "DONE":
        with store.tx() as con:
            con.execute("UPDATE tasks SET state='READY',version=version+1,lease_owner=NULL,lease_expiry=NULL,attempt=attempt+1 WHERE id=?", (task_id,))
            store.event(con, pid, "user", "TASK_REQUEUED", {"task": task_id, "from": "DONE", "reason": reason})
    elif task["state"] in ("FAILED", "WAITING_USER", "BLOCKED"):
        store.requeue(task_id, reason)
    elif task["state"] in ("RUNNING", "LEASED"):
        raise StateError(f"The designer is working on {mob} right now; wait for it to finish")
    return task_id


def request_model_edit(store: Store, pid: str, mob: str, text: str, *, may_change: list[str] | None = None) -> dict:
    """USER-ONLY: ask the designer to change the existing model (add a tail, longer horns) and keep everything else as it is."""
    text = (text or "").strip()
    if not text:
        raise InputError("Say what to change on the model, in your own words (e.g. what to add)")
    if len(text) > MAX_REQUEST:
        raise InputError(f"Keep the request under {MAX_REQUEST} characters")
    if mob not in _mob_ids(store, pid):
        raise InputError(f"Unknown mob {mob!r}")
    models = _models(store, pid)
    missing = [f"{mob}.{ext}" for _, ext in EXPORTS if not (models / f"{mob}.{ext}").is_file()]
    if missing:
        raise StateError(f"{mob} has no finished model to modify yet (missing in models/: {', '.join(missing)}): let the designer make it first, or use your own model")
    bones = current_bones(store, pid, mob)
    allowed = list(dict.fromkeys(str(b) for b in (may_change or [])))
    unknown = [b for b in allowed if b not in bones]
    if unknown:
        raise InputError(f"These are not parts of the current model: {unknown}; its bones are {bones}")
    edit = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(2)
    snap = Path(store.project(pid)["root"]) / EDIT_DIR / mob / edit
    snap.mkdir(parents=True, exist_ok=True)
    for _, ext in EXPORTS:
        shutil.copyfile(models / f"{mob}.{ext}", snap / f"before.{ext}")
    (snap / "request.json").write_text(json.dumps({"text": text, "may_change": allowed}, indent=2) + "\n", encoding="utf8")
    task_id = _requeue_model(store, pid, mob, "model modification")
    store.add_event(pid, "user", "MODEL_EDIT_REQUESTED", {"mob": mob, "edit": edit, "text": text[:600], "may_change": allowed, "task": task_id})
    return {"mob": mob, "edit": edit, "task": task_id, "may_change": allowed, "state": "READY",
            "next": {"action": "dispatch", "payload": {"task": task_id}}}


def pending_edit(store: Store, pid: str, mob: str) -> dict | None:
    """The modification the MODEL task is working on: the newest MODEL_EDIT_REQUESTED for the mob, unless a redesign request,
    an install or a cancel came after it."""
    for e in store.events(pid, 500):
        p = e["payload"]
        if p.get("mob") != mob:
            continue
        if e["kind"] in ("MODEL_INSTALLED", "MODEL_FEEDBACK", "MODEL_EDIT_CANCELLED", "MODEL_IMPORTED"):
            return None
        if e["kind"] == "MODEL_EDIT_REQUESTED":
            snap = Path(store.project(pid)["root"]) / EDIT_DIR / mob / p["edit"]
            return p | {"snapshot": str(snap)} if (snap / "before.geo.json").is_file() else None
    return None


EDIT_INSTRUCTIONS = """
## Your job on this task (designer — MODIFY an existing model)
This is a modification, not a new design. The model in `models/<mob>.bbmodel` is finished and the user likes it: it is the source
of truth. Make the change the user asks for below and nothing else. Do not explore takes, do not restart from a rig, do not
restyle, recolour or "improve" anything that was not asked.

What must stay exactly as it is (the controller compares your exports with a snapshot taken before this run and refuses the
install otherwise): every existing bone's name, parent, pivot and rotation; every existing cube (position, size, UV); every
keyframe of existing bones in existing clips, and each clip's length and loop; every pixel of the existing cubes' texture.
<allowed>
What you may do freely: add bones (a new part is a new bone, usually the child of the existing bone it grows from) and cubes in
them; add keyframes for the new bones to the existing clips (keeping each clip's length), so the new parts move with the rest; add
new clips.

Texture: give the new cubes box-UV space that no existing cube uses. If the atlas has no free room, call
`mcp__minecraft-orchestra__orchestra_grow_texture {project, mob}` once: it doubles the texture height and keeps every existing UV
and pixel in place. Paint only the new parts with `mcp__minecraft-orchestra__orchestra_paint_skin` and `only_bones: [the new
bones]` (it keeps every other pixel); match the colours and surface of the part they grow from, unless the user asks otherwise.
Then `bbmodel_geckolib_set_texture`, `bbmodel_render` to look at it, `bbmodel_geckolib_validate`, and re-export geo and
animations with `overwrite: true`.

Before you finish, call `mcp__minecraft-orchestra__orchestra_check_model_edit {project, mob}` and fix everything it lists until it
lists nothing. If the request cannot be done without changing a part you were not given, do not change it: finish with
WAITING_USER and name the parts that would have to change, so the user can allow them.
"""


def edit_brief(store: Store, pid: str, mob: str, edit: dict) -> str:
    allowed = edit.get("may_change") or []
    allow = (f"Parts the user opened for change: {', '.join(allowed)}. You may move, resize, re-pivot, re-animate and repaint those "
             "(and only those) as the request needs; they also remain the same bones (same names)." if allowed else
             "The user opened no existing part for change: this modification only adds.")
    bones = current_bones(store, pid, mob)
    return (EDIT_INSTRUCTIONS.replace("<mob>", mob).replace("<allowed>", allow)
            + f"\nThe current model's bones: {', '.join(bones)}.\n\n## The modification the user asked for (their words, verbatim)\n{edit['text']}\n")


# ---------------------------------------------------------------------------------------------------- the check

def _geo(raw: dict) -> tuple[dict, int, int]:
    g = raw["minecraft:geometry"][0]
    d = g["description"]
    return {b["name"]: b for b in g["bones"]}, int(d.get("texture_width") or 0), int(d.get("texture_height") or 0)


def _bone_shape(b: dict) -> str:
    """Everything that decides how an existing bone looks and pivots (not its children: those are their own bones)."""
    cubes = sorted(json.dumps(c, sort_keys=True) for c in b.get("cubes") or [])
    return json.dumps({k: b.get(k) for k in ("parent", "pivot", "rotation", "mirror", "inflate")} | {"cubes": cubes}, sort_keys=True)


def _strips(cube: dict) -> list[tuple[int, int, int, int]]:
    """The two box-UV rectangles a cube paints (top row: up/down; bottom row: the four sides), in UV units."""
    from .skin import face_rects
    uv, size = cube.get("uv"), cube.get("size")
    if not (isinstance(uv, list) and len(uv) == 2 and isinstance(size, list) and len(size) == 3):
        return []
    w, h, d = (max(1, int(abs(v))) for v in size)
    return list(face_rects({"u": int(uv[0]), "v": int(uv[1]), "w": w, "h": h, "d": d}).values())


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def check_edit(before: Path, after: Path, mob: str, may_change: list[str] | None = None) -> dict:
    """Compare a model's exports after a modification (folder `after`, files <mob>.geo.json, .animation.json, .png) with the
    snapshot (folder `before`, files before.*). Returns {violations, added_bones, changed_bones}; violations empty = accepted."""
    from .skin import decode_png
    allowed = set(may_change or [])
    v: list[str] = []
    try:
        old_bones, otw, oth = _geo(json.loads((before / "before.geo.json").read_text(encoding="utf8")))
        new_bones, ntw, nth = _geo(json.loads((after / f"{mob}.geo.json").read_text(encoding="utf8")))
        old_anim = json.loads((before / "before.animation.json").read_text(encoding="utf8")).get("animations") or {}
        new_anim = json.loads((after / f"{mob}.animation.json").read_text(encoding="utf8")).get("animations") or {}
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        return {"violations": [f"cannot read the exports: {exc}"], "added_bones": [], "changed_bones": []}
    added = [n for n in new_bones if n not in old_bones]
    changed = []
    for name, b in old_bones.items():
        if name not in new_bones:
            if name not in allowed:
                v.append(f"bone {name} was removed")
            continue
        if _bone_shape(b) != _bone_shape(new_bones[name]):
            changed.append(name)
            if name not in allowed:
                v.append(f"bone {name} changed (pivot, rotation, parent or its cubes/UV) but it was not opened for change")
    if ntw < otw or nth < oth or (otw and ntw % otw) or (oth and nth % oth) or (ntw != otw and nth != oth):
        v.append(f"the texture layout went from {otw}x{oth} to {ntw}x{nth}: it may only grow, keeping every existing UV (orchestra_grow_texture)")
    for clip, c in old_anim.items():
        if clip not in new_anim:
            v.append(f"clip {clip} was removed"); continue
        n = new_anim[clip]
        for key in ("loop", "animation_length"):
            if c.get(key) != n.get(key):
                v.append(f"clip {clip}: {key} changed from {c.get(key)} to {n.get(key)}")
        for bone in old_bones:
            if bone in allowed:
                continue
            if json.dumps((c.get("bones") or {}).get(bone), sort_keys=True) != json.dumps((n.get("bones") or {}).get(bone), sort_keys=True):
                v.append(f"clip {clip}: the keyframes of {bone} changed but it was not opened for change")
                if bone not in changed:
                    changed.append(bone)
    try:
        ow, oh, opx = decode_png((before / "before.png").read_bytes())
        nw, nh, npx = decode_png((after / f"{mob}.png").read_bytes())
    except (OSError, ValueError) as exc:
        v.append(f"cannot read the texture: {exc}")
        return {"violations": v, "added_bones": added, "changed_bones": changed}
    s_old, s_new = (ow // otw if otw else 0), (nw // ntw if ntw else 0)
    if not s_old or s_old != s_new:
        v.append(f"the texture's pixels per UV unit changed ({s_old} -> {s_new}): keep the same resolution so the existing pixels stay where they are")
        return {"violations": v, "added_bones": added, "changed_bones": changed}
    s = s_old
    kept = [(name, r) for name, b in old_bones.items() if name not in allowed for c in b.get("cubes") or [] for r in _strips(c)]
    for name, (x0, y0, x1, y1) in kept:
        diff = 0
        for y in range(y0 * s, min(y1 * s, oh, nh)):
            for x in range(x0 * s, min(x1 * s, ow, nw)):
                i, j = (y * ow + x) * 4, (y * nw + x) * 4
                if opx[i:i + 4] != npx[j:j + 4]:
                    diff += 1
        if diff:
            v.append(f"{diff} texture pixels of {name} changed but it was not opened for change")
    for name in added:
        for c in new_bones[name].get("cubes") or []:
            for r in _strips(c):
                hit = next((o for o, k in kept if _overlap(r, k)), None)
                if hit:
                    v.append(f"new bone {name} has a cube whose UV overlaps the texture of {hit}: give it free UV space"); break
    return {"violations": list(dict.fromkeys(v)), "added_bones": added, "changed_bones": sorted(set(changed))}


def check_pending(store: Store, pid: str, mob: str) -> dict:
    """What the designer's check tool and the install use: the pending modification against the current models/ exports."""
    edit = pending_edit(store, pid, mob)
    if edit is None:
        return {"mob": mob, "modification": None, "violations": [], "note": "no modification pending for this mob"}
    out = check_edit(Path(edit["snapshot"]), _models(store, pid), mob, edit.get("may_change"))
    return {"mob": mob, "modification": edit["edit"], **out,
            "rule": "fix every violation (put back what changed) and call this again; the install is refused otherwise" if out["violations"] else "ok"}


def grow_texture(store: Store, pid: str, mob: str) -> dict:
    """Designer tool: double the texture height of models/<mob>.bbmodel and pad models/<mob>.png with transparent rows. Every
    existing UV and pixel stays where it is; the new half is free room for new parts."""
    from .skin import decode_png, encode_png
    models = _models(store, pid)
    src, png_file = models / f"{mob}.bbmodel", models / f"{mob}.png"
    if not src.is_file() or not png_file.is_file():
        raise StateError(f"models/{mob}.bbmodel and models/{mob}.png must exist")
    model = json.loads(src.read_text(encoding="utf8"))
    res = model.get("resolution") or {}
    rw, rh = int(res.get("width", 0)), int(res.get("height", 0))
    w, h, px = decode_png(png_file.read_bytes())
    if not rw or not rh or w % rw or h % rh or w // rw != h // rh:
        raise StateError(f"the PNG ({w}x{h}) is not the model resolution ({rw}x{rh}) or a uniform multiple of it")
    if rh * 2 > 2048:
        raise InputError("the texture cannot grow further")
    png = encode_png(w, h * 2, px + bytes(w * h * 4))
    model["resolution"] = {"width": rw, "height": rh * 2}
    for t in model.get("textures") or []:
        t["source"] = "data:image/png;base64," + base64.b64encode(png).decode()
        t["height"] = h * 2
        if "uv_height" in t:
            t["uv_height"] = rh * 2
    png_file.write_bytes(png)
    src.write_text(json.dumps(model), encoding="utf8")
    return {"resolution": [rw, rh * 2], "texture": [w, h * 2], "free_rows": [rh, rh * 2],
            "next": "place the new cubes' UV in the new rows, paint them with orchestra_paint_skin only_bones, then set the texture and re-export"}


def cancel_model_edit(store: Store, pid: str, mob: str) -> dict:
    edit = pending_edit(store, pid, mob)
    if edit is None:
        raise InputError(f"No modification pending for {mob}")
    store.add_event(pid, "user", "MODEL_EDIT_CANCELLED", {"mob": mob, "edit": edit["edit"]})
    return {"mob": mob, "cancelled": edit["edit"]}


# ---------------------------------------------------------------------------------------------------- use my model

EXPORT_SCRIPT = Path(__file__).resolve().parent / "resources" / "blockbench" / "export_bbmodel.mjs"


def export_bbmodel(bbmodel: Path, out_dir: Path, mob: str, mod_id: str) -> dict:
    """Write <mob>.geo.json and <mob>.animation.json (and <mob>.png when the texture is embedded) from a .bbmodel, with the
    vendored Blockbench server's own exporter. Node only, no network; the identifier and mod id are set to this mob's."""
    try:
        r = subprocess.run(["node", str(EXPORT_SCRIPT), str(bbmodel), str(out_dir), mob, mod_id], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise StateError("Node.js is needed to read a .bbmodel (the designer uses it too); install it or run `craftctl doctor`") from None
    except subprocess.TimeoutExpired:
        raise StateError("Exporting the .bbmodel took too long") from None
    if r.returncode != 0:
        raise InputError("The .bbmodel could not be exported: " + (r.stderr.strip().splitlines() or ["unknown error"])[-1][:400])
    return json.loads(r.stdout)


def _embed_texture(src: Path, png: Path, dst: Path) -> None:
    """The installed .bbmodel carries the texture that is installed, so Open in Blockbench shows what the game shows."""
    model = json.loads(src.read_text(encoding="utf8"))
    raw = png.read_bytes()
    w, h = int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
    res = model.get("resolution") or {}
    tex = {"name": png.name, "folder": "", "namespace": "", "id": "0", "uuid": (model.get("textures") or [{}])[0].get("uuid") or secrets.token_hex(16),
           "source": "data:image/png;base64," + base64.b64encode(raw).decode(), "mode": "bitmap", "saved": False,
           "width": w, "height": h, "uv_width": res.get("width"), "uv_height": res.get("height")}
    model["textures"] = [tex]
    dst.write_text(json.dumps(model), encoding="utf8")


def import_model(store: Store, pid: str, mob: str, files: dict[str, bytes]) -> dict:
    """USER-ONLY: install a model the user made or downloaded. `files` holds a .bbmodel ("bbmodel") and optionally a PNG ("png")
    when the texture is not embedded. The model is exported, validated like a designer delivery and installed as a user revision;
    models/<mob>.* become this model, so Open in Blockbench, Modify and Redesign work on it."""
    from .content import GENERATED_STATUSES
    from .models import MODEL_DIR, install_model, _safe_dirname
    if mob not in _mob_ids(store, pid):
        raise InputError(f"Unknown mob {mob!r}")
    proj = store.project(pid)
    if proj["status"] not in GENERATED_STATUSES:
        raise StateError("Generate the project first: a model is installed into the generated workspace")
    raw = files.get("bbmodel")
    if not raw:
        raise InputError("Give the .bbmodel file (File > Save Model in Blockbench)")
    if sum(len(b) for b in files.values() if b) > MAX_IMPORT_BYTES:
        raise InputError("The files are too large (5 MB at most)")
    try:
        meta = json.loads(raw.decode("utf8")).get("meta") or {}
    except (UnicodeDecodeError, ValueError, AttributeError):
        raise InputError("That is not a .bbmodel (Blockbench project JSON)") from None
    if meta.get("box_uv") is False:
        raise InputError("This model uses per-face UV; only box-UV models are supported here (Blockbench: a GeckoLib or Modded Entity model with Box UV)")
    ws = Path(proj["root"])
    models = ws / MODEL_DIR
    stage = ws / ".mod-orchestra" / "imports" / _safe_dirname(time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(2))
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "source.bbmodel").write_bytes(raw)
    exported = export_bbmodel(stage / "source.bbmodel", stage, mob, pid)
    if files.get("png"):   # a PNG the user gave explicitly wins over the embedded one
        (stage / f"{mob}.png").write_bytes(files["png"])
    elif not (stage / f"{mob}.png").is_file() and files.get("png_fallback"):
        (stage / f"{mob}.png").write_bytes(files["png_fallback"])
    if not (stage / f"{mob}.png").is_file():
        raise InputError("The .bbmodel has no embedded texture: give its PNG too")
    _embed_texture(stage / "out.bbmodel", stage / f"{mob}.png", stage / f"{mob}.bbmodel")
    from .models import validate_model_files
    from .specedit import _load
    from .geckolib import held_item_for
    spec = _load(store, pid)
    m = next(x for x in spec.mobs if x.identifier == mob)
    probe = stage / "probe"
    (probe / MODEL_DIR).mkdir(parents=True, exist_ok=True)
    for ext in ("bbmodel", "geo.json", "animation.json", "png"):
        shutil.copyfile(stage / f"{mob}.{ext}", probe / MODEL_DIR / f"{mob}.{ext}")
    validate_model_files(probe, mob, m.behavior, needs_held_item=bool(held_item_for(spec, m)))   # raises with the reason, nothing installed yet
    models.mkdir(parents=True, exist_ok=True)
    for ext in ("bbmodel", "geo.json", "animation.json", "png"):
        shutil.copyfile(stage / f"{mob}.{ext}", models / f"{mob}.{ext}")
    shutil.rmtree(probe, ignore_errors=True)
    run_id = f"import:{mob}:{stage.name}"
    installed = install_model(store, pid, mob, run_id=run_id, actor="user")
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "user", "MODEL_IMPORTED", {"mob": mob, "run": run_id, "bones": installed["bones"], "animations": installed["animations"], **exported})
    return {"mob": mob, "installed": installed["installed"], "bones": installed["bones"], "animations": installed["animations"],
            "texture": installed["texture"], "note": "Installed as your model. Rebuild to see it in the game."}


def reinstall_from_blockbench(store: Store, pid: str, mob: str) -> dict:
    """USER-ONLY: install the edits the user made by hand to models/<mob>.bbmodel (Open in Blockbench, edit, save)."""
    source = _models(store, pid) / f"{mob}.bbmodel"
    if not source.is_file():
        raise InputError(f"models/{mob}.bbmodel does not exist yet")
    png = source.with_suffix(".png")
    return import_model(store, pid, mob, {"bbmodel": source.read_bytes(), "png_fallback": png.read_bytes() if png.is_file() else b""})
