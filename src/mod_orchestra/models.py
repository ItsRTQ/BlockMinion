"""R6 slice 2: the designer worker authors a real Blockbench/GeckoLib model for each mob.

Task <project>:MODEL:<mob> (role designer) runs with two MCP servers: minecraft-orchestra and the
vendored zero-dependency `blockbench-mcp-safe` (tools/blockbench-mcp-safe, packaged under resources/),
started by the controller with --root <workspace>/models --allow-write. The worker writes
models/<mob>.bbmodel, exports models/<mob>.geo.json + models/<mob>.animation.json, and leaves a 64x32
(or declared) PNG next to them. The controller validates the trio against the mob and the
DefaultedEntityGeoModel layout, then installs it over the placeholders as a manifest revision.
The .bbmodel stays in models/ as the editable source for the user.
"""
from __future__ import annotations
import json
import re
import shutil
from pathlib import Path

from .fabric import accept_changes
from .state import Store, StateError
from .validation import InputError

SAFE_DIR = Path(__file__).resolve().parent / "resources" / "blockbench-mcp-safe"
SAFE_SERVER = SAFE_DIR / "src" / "server.mjs"
MODEL_DIR = "models"


def blockbench_server_config(workspace: Path) -> dict:
    """MCP server entry for the designer worker. Node only; no npm, no network."""
    root = workspace / MODEL_DIR
    root.mkdir(parents=True, exist_ok=True)
    return {"command": "node", "args": [str(SAFE_SERVER), "--root", str(root), "--allow-write"]}


def _safe_dirname(name: str) -> str:
    """Windows forbids : * ? " < > | and friends in directory names."""
    return re.sub(r'[<>:"/\\|?*]', "-", name)


def theme_block(store: Store, pid: str) -> str:
    theme = (store.project(pid)["spec"].get("theme") or "").strip()
    if not theme:
        return "\n## Visual theme\nNo theme set for this mod yet: pick a coherent palette and motif family from the mod's idea and state it in `assumptions`.\n"
    return f"\n## Visual theme of this mod (follow it in every colour and motif)\n{theme}\n"


def model_task_id(pid: str, mob_id: str) -> str:
    return f"{pid}:MODEL:{mob_id}"


MODEL_INSTRUCTIONS = """
## Your job on this task (designer)
Author the Blockbench/GeckoLib model for the mob named in the task using the `blockbench` MCP server (tools
prefixed `mcp__blockbench__bbmodel_*`). Its root is `models/` inside this workspace; only top-level files there.
Deliver, in `models/`: `<mob>.bbmodel` (format geckolib_model, identifier = the mob id, mod id = this mod),
`<mob>.geo.json`, `<mob>.animation.json` and `<mob>.png` (the texture, matching the model resolution).
Required: a readable rig (body/head/limbs as bones with sensible pivots), animations named exactly
`animation.<mob>.idle` and `animation.<mob>.walk` (loop), `bbmodel_geckolib_validate` with
`require_idle_walk: true` passing, `bbmodel_render` used at least once to look at the result (rest + a walk frame),
and both exports written with `overwrite: true` when re-exporting. Keep the texture simple but not noise:
flat colours per body part on the UV layout is enough for v1. Report the four file paths in `changed_files`
(relative to the workspace, e.g. `models/<mob>.geo.json`) and the validator result under `checks_run`.
Never touch `src/` or `assets/` yourself: the controller installs the exports over the placeholders.
"""


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"{path.name}: {exc}")


def validate_model_files(workspace: Path, mob_id: str) -> dict:
    """Check the designer's deliverables against the mob and GeckoLib's expectations."""
    root = workspace / MODEL_DIR
    files = {k: root / f"{mob_id}.{ext}" for k, ext in (("bbmodel", "bbmodel"), ("geo", "geo.json"), ("anim", "animation.json"), ("png", "png"))}
    missing = [f.name for f in files.values() if not f.is_file()]
    if missing:
        raise InputError(f"designer deliverables missing in models/: {', '.join(missing)}")
    geo = _load(files["geo"])
    try:
        g = geo["minecraft:geometry"][0]
        desc = g["description"]
        bones = {b["name"] for b in g["bones"]}
    except (KeyError, IndexError, TypeError):
        raise InputError("geo.json is not Bedrock 1.12.0 geometry with minecraft:geometry[0].bones")
    if desc.get("identifier") != f"geometry.{mob_id}":
        raise InputError(f"geo identifier must be geometry.{mob_id}, got {desc.get('identifier')!r}")
    if not bones:
        raise InputError("geo.json has no bones")
    anim = _load(files["anim"])
    clips = anim.get("animations") or {}
    for req in (f"animation.{mob_id}.idle", f"animation.{mob_id}.walk"):
        if req not in clips:
            raise InputError(f"animation.json lacks {req} (has: {', '.join(clips) or 'none'})")
    unknown = sorted({b for c in clips.values() for b in (c.get("bones") or {}) if b not in bones})
    if unknown:
        raise InputError(f"animation.json animates bones that are not in geo.json: {unknown}")
    png = files["png"].read_bytes()
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise InputError("texture is not a PNG")
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    tw, th = desc.get("texture_width"), desc.get("texture_height")
    if (tw, th) != (w, h):
        raise InputError(f"texture is {w}x{h} but geo declares {tw}x{th}")
    cubes = sum(len(b.get("cubes", [])) for b in g["bones"])
    return {"bones": sorted(bones), "cubes": cubes, "animations": sorted(clips), "texture": [w, h],
            "files": {k: str(v.relative_to(workspace)).replace("\\", "/") for k, v in files.items()}}


def install_model(store: Store, pid: str, mob_id: str, *, run_id: str, actor: str) -> dict:
    """Validate and copy the designer's exports over the placeholder assets, as a manifest revision."""
    proj = store.project(pid)
    ws = Path(proj["root"])
    info = validate_model_files(ws, mob_id)
    res = ws / "src" / "main" / "resources" / "assets" / pid
    targets = {
        "geo": res / "geo" / "entity" / f"{mob_id}.geo.json",
        "anim": res / "animations" / "entity" / f"{mob_id}.animation.json",
        "png": res / "textures" / "entity" / f"{mob_id}.png",
    }
    for key, dst in targets.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ws / info["files"][key], dst)
    changed = [str(t.relative_to(ws)).replace("\\", "/") for t in targets.values()]
    # Keep this run's previews + texture so the UI can show versions after feedback rounds.
    history = ws / ".mod-orchestra" / "previews" / _safe_dirname(run_id)
    history.mkdir(parents=True, exist_ok=True)
    for png in sorted((ws / MODEL_DIR).glob(f"{mob_id}_*.png")) + [ws / info["files"]["png"]]:
        shutil.copyfile(png, history / png.name)
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=changed)
    store.add_event(pid, "controller", "MODEL_INSTALLED", {"mob": mob_id, "run": run_id, **{k: v for k, v in info.items() if k != "files"}})
    return info | {"installed": changed, "accepted": accepted["accepted"], "source": info["files"]["bbmodel"]}


# ---------------------------------------------------------------------------------------------
# Adding a mob AFTER generation (UI "Add a mob"). The controller writes the mob's own new files
# deterministically (nothing an agent could have edited), merges lang keys, and hands the only
# shared-file edits (ModMain/ModClient registrations, GeckoLib dependency if this is the first mob)
# to a coder task with the exact reference snippets. Then the designer task and a fresh BUILD.
# ---------------------------------------------------------------------------------------------
import json as _json
from dataclasses import replace as _replace
from .spec import Mob, read_spec, validate_spec_content
from .geckolib import (entity_java, renderer_java, client_init_java, main_registrations, placeholder_geo, placeholder_animation,
                       entity_loot, class_name, gradle_dependency_lines, GECKOLIB_VERSION)
from .fabric import placeholder_png


def add_mob_after_generation(store: Store, pid: str, mob: Mob) -> dict:
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first; before generation use `craftctl add-mob`")
    spec = read_spec(proj["spec"])
    if any(m.identifier == mob.identifier for m in spec.mobs):
        raise InputError(f"Mob {mob.identifier!r} already exists")
    new_spec = _replace(spec, mobs=list(spec.mobs) + [mob])
    validate_spec_content(new_spec)
    first_mob = not spec.mobs
    ws = Path(proj["root"])
    java_dir = ws / "src/main/java" / spec.package.replace(".", "/")
    res = ws / "src/main/resources"
    assets = res / "assets" / pid
    written: list[str] = []

    def put(rel: Path, data: bytes):
        if rel.exists():
            raise InputError(f"Refusing to overwrite {rel.relative_to(ws)}")
        rel.parent.mkdir(parents=True, exist_ok=True); rel.write_bytes(data); written.append(str(rel.relative_to(ws)).replace("\\", "/"))

    put(java_dir / "entity" / f"{class_name(mob)}Entity.java", entity_java(new_spec, mob).encode())
    put(java_dir / "client" / f"{class_name(mob)}Renderer.java", renderer_java(new_spec, mob).encode())
    put(assets / "geo/entity" / f"{mob.identifier}.geo.json", (_json.dumps(placeholder_geo(mob), indent=2) + "\n").encode())
    put(assets / "animations/entity" / f"{mob.identifier}.animation.json", (_json.dumps(placeholder_animation(mob), indent=2) + "\n").encode())
    put(assets / "textures/entity" / f"{mob.identifier}.png", placeholder_png(pid + "/entity/" + mob.identifier, 64, 32))
    put(res / "data" / pid / "loot_table/entities" / f"{mob.identifier}.json", (_json.dumps(entity_loot(new_spec, mob), indent=2) + "\n").encode())
    put(assets / "models/item" / f"{mob.identifier}_spawn_egg.json", (_json.dumps({"parent": "minecraft:item/template_spawn_egg"}, indent=2) + "\n").encode())
    lang_file = assets / "lang/en_us.json"
    lang = _json.loads(lang_file.read_text(encoding="utf8")) if lang_file.is_file() else {}
    lang[f"entity.{pid}.{mob.identifier}"] = mob.label
    lang[f"item.{pid}.{mob.identifier}_spawn_egg"] = f"{mob.label} Spawn Egg"
    lang_file.write_text(_json.dumps(lang, indent=2, sort_keys=True) + "\n", encoding="utf8"); written.append(f"src/main/resources/assets/{pid}/lang/en_us.json")

    # spec update (status unchanged; approval stays: adding a mob is an additive, user-initiated change)
    with store.tx() as con:
        con.execute("UPDATE projects SET spec_json=? WHERE id=?", (_json.dumps(new_spec.to_dict(), sort_keys=True), pid))
        store.event(con, pid, "user", "SPEC_CHANGED", {"reason": f"add mob {mob.identifier} after generation"})
    accepted = accept_changes(ws, run_id=f"add-mob:{mob.identifier}", actor="user", changed=written)
    from .dispatch import _source_changed
    _source_changed(store, pid)

    # coder task with the exact registration snippets; MODEL after it; BUILD requeued after MODEL
    imports, fields, init = main_registrations(_replace(spec, mobs=[mob]))
    client_lines = [l for l in client_init_java(new_spec).splitlines() if "EntityRendererRegistry.register" in l and class_name(mob) in l]
    extra = [f"import {i};" for i in imports if class_name(mob) in i or "EntityType" in i or "MobCategory" in i or "SpawnEggItem" in i or "FabricDefaultAttributeRegistry" in i]
    instructions = ["Register the new mob in the shared files (do not touch anything else):",
                    f"1. {java_dir.relative_to(ws)}/ModMain.java — add imports:"] + ["   " + l for l in extra] + \
                   ["   add fields:"] + ["   " + l for l in fields] + ["   in onInitialize():"] + ["   " + l for l in init] + \
                   [f"   and, if the mod has a creative tab (TAB), add `output.accept({mob.identifier.upper()}_SPAWN_EGG);` to its displayItems.",
                    f"2. {java_dir.relative_to(ws)}/client/ModClient.java — add inside onInitializeClient():"] + ["   " + l.strip() for l in client_lines]
    if first_mob:
        repo_block, dep_line = gradle_dependency_lines()
        instructions += ["3. This is the mod's first mob: build.gradle needs the GeckoLib repository block and dependency, gradle.properties needs "
                         f"`geckolib_version={GECKOLIB_VERSION}`, fabric.mod.json needs the client entrypoint `{spec.package}.client.ModClient` "
                         "and `\"geckolib\": \">=4.7\"` under depends, and src/main/java/.../client/ModClient.java must be created (ClientModInitializer).",
                         "   repository block:", *("   " + l for l in repo_block.splitlines()), "   dependency line:", "   " + dep_line.strip()]
    instructions += ["4. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    task_add = f"{pid}:ADD_MOB:{mob.identifier}"
    task_model = model_task_id(pid, mob.identifier)
    store.add_task(pid, task_add, "coder", f"Register new mob {mob.label} in ModMain/ModClient" + (" + GeckoLib dependency" if first_mob else ""))
    store.add_task(pid, task_model, "designer", f"Blockbench/GeckoLib model + idle/walk + texture for mob: {mob.label}", after=[task_add])
    store.add_event(pid, "controller", "MOB_ADDED", {"mob": mob.identifier, "files": written, "tasks": [task_add, task_model], "first_mob": first_mob})
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_add, "\n".join(instructions)))
    return {"mob": mob.identifier, "files": written, "accepted": accepted["accepted"], "tasks": [task_add, task_model], "first_mob": first_mob,
            "next": {"action": "dispatch", "payload": {"task": task_add}}}


def set_mob_drops(store: Store, pid: str, mob_id: str, drops: list) -> dict:
    """Replace a mob's death loot. Before generation it edits the spec; after, it also rewrites the
    (controller-owned) loot table file as a user revision."""
    from .spec import coerce_mob_drop
    proj = store.project(pid)
    spec = read_spec(proj["spec"])
    mob = next((m for m in spec.mobs if m.identifier == mob_id), None)
    if mob is None:
        raise InputError(f"Unknown mob {mob_id!r}")
    new_mob = _replace(mob, drops=tuple(coerce_mob_drop(d) for d in drops))
    new_spec = _replace(spec, mobs=[new_mob if m.identifier == mob_id else m for m in spec.mobs])
    validate_spec_content(new_spec)
    with store.tx() as con:
        con.execute("UPDATE projects SET spec_json=? WHERE id=?", (_json.dumps(new_spec.to_dict(), sort_keys=True), pid))
        store.event(con, pid, "user", "SPEC_CHANGED", {"reason": f"drops of {mob_id}"})
    out = {"mob": mob_id, "drops": [d.__dict__ for d in new_mob.drops]}
    if proj["status"] in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        ws = Path(proj["root"])
        loot = ws / "src/main/resources/data" / pid / "loot_table/entities" / f"{mob_id}.json"
        loot.parent.mkdir(parents=True, exist_ok=True)
        loot.write_text(_json.dumps(entity_loot(new_spec, new_mob), indent=2) + "\n", encoding="utf8")
        rel = str(loot.relative_to(ws)).replace("\\", "/")
        accepted = accept_changes(ws, run_id=f"drops:{mob_id}", actor="user", changed=[rel])
        from .dispatch import _source_changed, _reopen_build
        _source_changed(store, pid); _reopen_build(store, pid)
        out |= {"file": rel, "accepted": accepted["accepted"], "note": "Loot table rewritten; rebuild to apply."}
    return out


# ---------------------------------------------------------------------------------------------
# SPRITES task: the designer paints 16x16 item/block sprites by script (path A). The controller
# validates (size, transparency, not flat) and installs them over the tinted placeholders.
# ---------------------------------------------------------------------------------------------
SPRITES_INSTRUCTIONS = """
## Your job on this task (designer — sprites)
Paint 16x16 pixel-art sprites for the items listed under "Sprites to paint" and write each one to
`models/sprites/<identifier>.png` (exact names). Use a small Python script with the stdlib only (zlib/struct,
no PIL) that writes RGBA PNGs; keep the script at `models/sprites/paint.py` so it can be rerun.
Rules: transparent background (blocks are the exception: fully opaque 16x16 tile); 4–8 colours per sprite; a
1px darker outline around the shape; a lighter highlight on the top-left; readable silhouette at 1x (a sword
is a diagonal blade with a guard; a gem is a faceted lozenge; food is a round shape with a stem/leaf).
Minecraft's own style is 16x16 with soft shading, no anti-aliasing. Then write a contact sheet
`models/sprites/contact_sheet.png` scaled x8 with every sprite side by side so the user can judge them in the
UI. Re-read your own PNGs' pixel grids before finishing: a sprite whose silhouette is not readable at 1x
(blob, no outline, wrong proportions) must be repainted, not reported.
Report every PNG path in `changed_files`. Do not touch `src/` or `assets/`; the controller installs them.
"""


ARMOR_LAYER_GUIDE = """
Worn-armor layers (64x32 RGBA, classic player-model layout, transparent where there is no armor):
- layer 1 = helmet + chestplate + boots; layer 2 = leggings.
- Head box (helmet): x 0–31, y 0–15 (6 faces of an 8x8 cube: top at (8,0), front at (8,8), right (0,8), left (16,8), back (24,8), bottom (16,0)).
- Body (chestplate / leggings upper): x 16–39, y 16–31 (front 20–27, back 32–39, sides 16–19 and 28–31; top 20–27 y 16–19).
- Arm (chestplate sleeves): x 40–55, y 16–31 (front 44–47). Leg (leggings / boots): x 0–15, y 16–31 (front 4–7).
- Boots: only the lower ~5 rows of the leg box (y 27–31). Leggings: body lower rows (y 20–31) + the leg box.
Write `models/sprites/<material>_layer_1.png` and `models/sprites/<material>_layer_2.png`.
FIRST read the existing inventory icons of the set (src/main/resources/assets/<mod>/textures/item/<material>_helmet.png,
_chestplate.png, _leggings.png, _boots.png — decode the PNGs in your script and print their colour counts): the worn
armor must use the SAME palette and the same visual motifs (plates, rivets, trim lines, gem inlays) so the equipped
armor looks like the icon's material. Add a slightly darker underside and outline every face edge.
"""


def request_sprites(store: Store, pid: str, identifiers: list[str], notes: str = "", armor_materials: list[str] | None = None) -> dict:
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first")
    spec = read_spec(proj["spec"])
    catalogue = {}
    for f in spec.features:
        catalogue[f.identifier] = {"kind": f.kind, "label": f.label, "hint": f.shape or ("cube" if f.kind == "block" else "")}
    for m in spec.materials:
        for k in m.tools: catalogue[f"{m.identifier}_{k}"] = {"kind": "tool", "label": f"{m.label} {k}", "hint": f"{k}, material colour {m.color or 'any'}"}
        for k in m.armor: catalogue[f"{m.identifier}_{k}"] = {"kind": "armor", "label": f"{m.label} {k}", "hint": f"{k} icon, material colour {m.color or 'any'}"}
    for fd in spec.foods:
        catalogue[fd.identifier] = {"kind": "food", "label": fd.label, "hint": "food"}
    unknown = [i for i in identifiers if i not in catalogue]
    if unknown:
        raise InputError(f"Unknown identifiers: {unknown}")
    armor_materials = [a for a in (armor_materials or []) if a]
    mats = {m.identifier: m for m in spec.materials}
    bad = [a for a in armor_materials if a not in mats or not mats[a].armor]
    if bad:
        raise InputError(f"Not materials with armor: {bad}")
    if not identifiers and not armor_materials:
        raise InputError("Pick at least one item or armor set")
    n = sum(1 for t in store.tasks(pid) if ":SPRITES:" in t["id"]) + 1
    task_id = f"{pid}:SPRITES:{n}"
    lines = ["Sprites to paint (identifier → what it is):"] + [f"- {i}: {catalogue[i]['label']} ({catalogue[i]['kind']}{', ' + catalogue[i]['hint'] if catalogue[i]['hint'] else ''})" for i in identifiers]
    if armor_materials:
        lines += ["", "Worn-armor layers to paint for material(s): " + ", ".join(f"{a} (pieces: {', '.join(mats[a].armor)})" for a in armor_materials), ARMOR_LAYER_GUIDE]
    if notes.strip():
        lines += ["", "Style notes from the user:", notes.strip()[:800]]
    store.add_task(pid, task_id, "designer", f"Paint {len(identifiers)} item sprite(s)" + (f" + armor layers for {', '.join(armor_materials)}" if armor_materials else ""))
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(lines)))
    store.add_event(pid, "user", "SPRITES_REQUESTED", {"task": task_id, "items": identifiers, "armor": armor_materials, "notes": notes[:300]})
    return {"task": task_id, "items": identifiers, "armor": armor_materials, "next": {"action": "dispatch", "payload": {"task": task_id}}}


def _png_info(raw: bytes) -> tuple[int, int, bool]:
    """(width, height, has_alpha_variation) using zlib only."""
    import zlib as _z, struct as _s
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise InputError("not a PNG")
    w, h, depth, ctype = _s.unpack(">IIBB", raw[16:26])
    if depth != 8 or ctype not in (2, 6):
        raise InputError("PNG must be 8-bit RGB or RGBA")
    pos, idat = 8, b""
    while pos < len(raw):
        ln = _s.unpack(">I", raw[pos:pos + 4])[0]; kind = raw[pos + 4:pos + 8]
        if kind == b"IDAT": idat += raw[pos + 8:pos + 8 + ln]
        pos += 12 + ln
    px = _z.decompress(idat); bpp = 4 if ctype == 6 else 3
    alphas = set(); colours = set()
    for y in range(h):
        row = px[y * (w * bpp + 1) + 1:(y + 1) * (w * bpp + 1)]
        for x in range(w):
            p = row[x * bpp:(x + 1) * bpp]
            colours.add(p[:3]); alphas.add(p[3] if bpp == 4 else 255)
    return w, h, len(alphas) > 1, len(colours)


def install_sprites(store: Store, pid: str, task_id: str, identifiers: list[str], *, run_id: str, actor: str, armor_materials: list[str] | None = None) -> dict:
    proj = store.project(pid); ws = Path(proj["root"]); spec = read_spec(proj["spec"])
    blocks = {f.identifier for f in spec.features if f.kind == "block"}
    installed, rejected = [], {}
    for mat in (armor_materials or []):
        for n in (1, 2):
            src = ws / "models" / "sprites" / f"{mat}_layer_{n}.png"
            key = f"{mat}_layer_{n}"
            if not src.is_file():
                rejected[key] = "missing"; continue
            try:
                w, h, alpha_var, ncol = _png_info(src.read_bytes())
            except InputError as exc:
                rejected[key] = str(exc); continue
            if (w, h) != (64, 32):
                rejected[key] = f"{w}x{h}, need 64x32"; continue
            if not alpha_var:
                rejected[key] = "fully opaque: armor layers need transparent areas"; continue
            rel = f"src/main/resources/assets/{pid}/textures/models/armor/{key}.png"
            (ws / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, ws / rel); installed.append(rel)
    for ident in identifiers:
        src = ws / "models" / "sprites" / f"{ident}.png"
        if not src.is_file():
            rejected[ident] = "missing"; continue
        try:
            w, h, alpha_var, ncol = _png_info(src.read_bytes())
        except InputError as exc:
            rejected[ident] = str(exc); continue
        if (w, h) != (16, 16):
            rejected[ident] = f"{w}x{h}, need 16x16"; continue
        if ncol < 2:
            rejected[ident] = "flat single colour"; continue
        if ident not in blocks and not alpha_var:
            rejected[ident] = "no transparency (items need a transparent background)"; continue
        rel = f"src/main/resources/assets/{pid}/textures/{'block' if ident in blocks else 'item'}/{ident}.png"
        (ws / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, ws / rel); installed.append(rel)
    if not installed:
        raise InputError("no sprite passed validation: " + "; ".join(f"{k}: {v}" for k, v in rejected.items()))
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=installed)
    sheet = ws / "models" / "sprites" / "contact_sheet.png"
    history = ws / ".mod-orchestra" / "previews" / _safe_dirname(run_id); history.mkdir(parents=True, exist_ok=True)
    if sheet.is_file():
        shutil.copyfile(sheet, history / "sprites_contact_sheet.png")
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "controller", "SPRITES_INSTALLED", {"task": task_id, "run": run_id, "installed": installed, "rejected": rejected})
    return {"installed": installed, "rejected": rejected, "accepted": accepted["accepted"], "contact_sheet": f".mod-orchestra/previews/{_safe_dirname(run_id)}/sprites_contact_sheet.png" if sheet.is_file() else None}


# ---------------------------------------------------------------------------------------------
# ARMOR task: the designer paints the two worn-armor layers for a material and MUST look at them
# worn, using the shipped player template (resources/blockbench/player_armor.bbmodel) + bbmodel_render.
# ---------------------------------------------------------------------------------------------
TEMPLATE_DIR = Path(__file__).resolve().parent / "resources" / "blockbench"

ARMOR_INSTRUCTIONS = """
## Your job on this task (designer — worn armor for material `<material>`)
Paint the two armor layer textures (64x32 RGBA) so the set looks good WORN, in the mod's theme and matching
the material's inventory icons (read `src/main/resources/assets/<mod>/textures/item/<material>_*.png` first
and reuse their palette and motifs).
Files to write, exact names, in `models/`:
- `models/sprites/<material>_layer_1.png` — helmet + chestplate (body and both arms) + boots (lower rows of the leg box)
- `models/sprites/<material>_layer_2.png` — leggings (lower body rows + leg boxes)
Layout (classic 64x32 player-model nets; everything else transparent):
- head cube net at (0,0): top (8,0), bottom (16,0), right (0,8), front (8,8), left (16,8), back (24,8); each 8x8. Leave an
  opening on the front face (eyes/mouth area, about cols 1–6, rows 3–7) unless the helmet is a full-face design.
- body net at (16,16): top (20,16) 8x4, bottom (28,16) 8x4, right (16,20) 4x12, front (20,20) 8x12, left (28,20) 4x12, back (32,20) 8x12.
- arm net at (40,16): top (44,16) 4x4, bottom (48,16) 4x4, right (40,20) 4x12, front (44,20) 4x12, left (48,20) 4x12, back (52,20) 4x12.
- leg net at (0,16): top (4,16) 4x4, bottom (8,16) 4x4, right (0,20) 4x12, front (4,20) 4x12, left (8,20) 4x12, back (12,20) 4x12.
Craft (edges matter most, owner feedback): NO hard dark outlines. Edges are a soft 1px gradient step, 15–20% darker
than the fill (never black or near-black), and adjacent faces of the same piece share their edge colour so the
piece reads as one surface, not a grid of boxes. Shade by light: top faces lighter, sides mid, bottoms darker,
with a 2-step gradient toward the edges. Reserve strong lines for deliberate seams, straps or trim. Add plates,
rivets, gems or motifs as the theme suggests; keep 4–8 colours per material. Write the PNGs with a stdlib Python script
(`models/sprites/paint_armor.py`, rerunnable).
LOOK AT IT WORN before finishing (mandatory): `models/<material>_armor.bbmodel` is a player template already
placed in `models/`. For each layer: `bbmodel_geckolib_set_texture {file: "<material>_armor.bbmodel",
png_file: "sprites/<material>_layer_1.png", expected_revision: ...}` then `bbmodel_render {file, output_file:
"<material>_armor_layer1.png", overwrite: true}` (and the same with layer 2 → `<material>_armor_layer2.png`).
Inspect the renders; if a region is misplaced, the face is covered, or it reads as a flat blob, fix the PNG and
render again. Report the two layer PNGs and the two renders in `changed_files`. Never touch `src/` or `assets/`.
"""


def request_armor_design(store: Store, pid: str, material: str, notes: str = "") -> dict:
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first")
    spec = read_spec(proj["spec"])
    m = next((x for x in spec.materials if x.identifier == material), None)
    if m is None or not m.armor:
        raise InputError(f"{material!r} is not a material with armor pieces")
    ws = Path(proj["root"])
    (ws / MODEL_DIR / "sprites").mkdir(parents=True, exist_ok=True)
    target = ws / MODEL_DIR / f"{material}_armor.bbmodel"
    if not target.is_file():
        shutil.copyfile(TEMPLATE_DIR / "player_armor.bbmodel", target)
    n = sum(1 for t in store.tasks(pid) if f":ARMOR:{material}" in t["id"]) + 1
    task_id = f"{pid}:ARMOR:{material}" + (f":{n}" if n > 1 else "")
    lines = [f"Material: {material} ({m.label}); pieces: {', '.join(m.armor)}; material colour hint: {m.color or 'derive from icons'}"]
    prior = [e["payload"].get("notes", "") for e in store.events(pid, 300) if e["kind"] == "ARMOR_REQUESTED" and e["payload"].get("material") == material and e["payload"].get("notes")]
    if notes.strip():
        lines += ["", "User notes for this round:", notes.strip()[:800]]
    if prior:
        lines += ["", "Earlier user notes on this armor (apply them too):"] + [f"- {p}" for p in prior[-5:]]
    store.add_task(pid, task_id, "designer", f"Design worn armor textures for {m.label}")
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(lines)))
    store.add_event(pid, "user", "ARMOR_REQUESTED", {"task": task_id, "material": material, "notes": notes[:300]})
    return {"task": task_id, "material": material, "next": {"action": "dispatch", "payload": {"task": task_id}}}


def install_armor_design(store: Store, pid: str, task_id: str, material: str, *, run_id: str, actor: str) -> dict:
    ws = Path(store.project(pid)["root"])
    renders = sorted((ws / MODEL_DIR).glob(f"{material}_armor_layer*.png"))
    if not renders:
        raise InputError("no worn-armor render found (models/<material>_armor_layer1.png); the designer must look at it worn")
    out = install_sprites(store, pid, task_id, [], run_id=run_id, actor=actor, armor_materials=[material])
    if not out["installed"]:
        raise InputError("no armor layer passed validation: " + "; ".join(f"{k}: {v}" for k, v in out["rejected"].items()))
    history = ws / ".mod-orchestra" / "previews" / _safe_dirname(run_id); history.mkdir(parents=True, exist_ok=True)
    for r in renders:
        shutil.copyfile(r, history / r.name)
    out["previews"] = [f".mod-orchestra/previews/{_safe_dirname(run_id)}/{r.name}" for r in renders]
    store.add_event(pid, "controller", "ARMOR_INSTALLED", {"task": task_id, "run": run_id, "material": material, "installed": out["installed"], "rejected": out["rejected"]})
    return out
