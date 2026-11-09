"""R6 slice 2: the designer worker authors a real Blockbench/GeckoLib model for each mob.

Task <project>:MODEL:<mob> (role designer) runs with two MCP servers: minecraft-orchestra and the
vendored zero-dependency `blockbench-mcp-safe` (tools/blockbench-mcp-safe, packaged under resources/),
started by the controller with --root <workspace>/models --allow-write. The worker writes
models/<mob>.bbmodel, exports models/<mob>.geo.json + models/<mob>.animation.json, and leaves a 64x64
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


USER_WORDS_LIMIT = 3500


def user_words(store: Store, pid: str, subject: str = "") -> str:
    """The user's own text, verbatim, as the first thing an artist reads. Everything else in a packet is our interpretation of these words, made by a
    program that may have dropped nuance ("grotesque", "human skin", "like the Tank"); where they disagree the words win."""
    idea = str((store.project(pid)["spec"] or {}).get("idea") or "").strip()
    if not idea:
        return ""
    shown = idea if len(idea) <= USER_WORDS_LIMIT else idea[:USER_WORDS_LIMIT].rsplit(" ", 1)[0] + " ..."
    where = f" Look for what they said about {subject}." if subject else ""
    return ("\n## What the user wrote, in their own words (read this first: it wins over every summary below)\n" + shown + "\n"
            f"The art direction, mood and notes that follow are our interpretation of these words.{where} Where they disagree, follow the words: take what the user asks "
            "for seriously, and make it your own.\n")


def rig_block(store: Store, pid: str, mob_id: str, workspace: Path) -> str:
    """Stage the mob's base rig in models/ (if no source exists yet) and describe it to the designer."""
    from .rigs import stage_rig, load_rig, DEFAULT_BODY_PLAN
    from .specedit import _load
    spec = _load(store, pid)
    mob = next((m for m in spec.mobs if m.identifier == mob_id), None)
    plan = getattr(mob, "body_plan", DEFAULT_BODY_PLAN) if mob else DEFAULT_BODY_PLAN
    staged = stage_rig(workspace, plan, mob_id, spec.mod_id, MODEL_DIR)
    rec = load_rig(plan, "recipe")
    bones = ", ".join(f"{b['name']}" + (f" (child of {b['parent']})" if b.get("parent") else " (root)") for b in rec["bones"])
    state = "placed now" if staged["staged"] else "already present (edited before; keep working on it)"
    from .geckolib import held_item_for
    from .art import brief as art_brief
    art_text = ("\n## Art direction for this creature\n" + art_brief(spec, "mob", mob_id) + "\nIt describes; it does not dictate every detail. Reshape and detail the model "
                "so it shows these cues in a way of your own, and feed `orchestra_paint_skin` from it (palette, zones, surfaces, face). Do not paint a generic creature.\n") if mob else ""
    words = user_words(store, pid, f"{mob.label} (`{mob_id}`)" if mob else "") if mob else ""
    held = held_item_for(spec, mob) if mob else None
    held_text = (f" The entity holds `{held}` in its main hand and draws it on the empty `held_item` bone at the right palm: keep that bone "
                 f"(a child of the forearm), keep it at the grip when you reshape the arm, and give it a rotation if the weapon points the wrong way.") if held else ""
    return (f"{words}\n## Optional scaffold: {plan} — `{staged['path']}` {state}\n"
            f"A plain {plan} rig, there to save you the technical conventions, not to decide the design: use it, reshape it heavily, or ignore it and build your own from scratch. "
            f"Bones: {bones}. Texture {rec['texture_width']}x{rec['texture_height']}, box UV already packed without overlaps (`bbmodel_geckolib_validate` passes, "
            f"`bbmodel_quality_gates` clean). Notes on it, optional: {rec['notes']}{held_text}\n{art_text}")


MODEL_INSTRUCTIONS = """
## Your job on this task (designer)
Author the Blockbench/GeckoLib model for the mob named in the task using the `blockbench` MCP server (tools
prefixed `mcp__blockbench__bbmodel_*`). Its root is `models/` inside this workspace; only top-level files there.
Deliver, in `models/`: `<mob>.bbmodel` (format geckolib_model, identifier = the mob id, mod id = this mod),
`<mob>.geo.json`, `<mob>.animation.json` and `<mob>.png` (the texture: the model resolution or a 2x/4x multiple of it).
The controller also places an optional scaffold at `models/<mob>.bbmodel` (see "Optional scaffold" below): a plain rig that already passes
validation. It is yours to use, reshape heavily or ignore: you may build a creature of your own from scratch with `bbmodel_geckolib_create`
(your bones, your cubes, your UV, your clips). Never deliver the scaffold with only a recolour, and do not let it decide what the creature is:
the user's description does.
Explore before you build, the way a painter starts a new piece. First write three deliberately different takes on this creature (a
different silhouette, a different signature feature, a different colour story: not three variations of the first idea that came to mind), and
avoid the most typical version of it unless the description demands it. Pick one and record the three and your choice in your handoff as
`"design_notes": {"takes": ["...", "...", "..."], "chosen": 1, "why": "one sentence"}`; the user sees it and may ask for another take.
Required: a readable rig (body/head/limbs as bones with sensible pivots), animations named exactly
`animation.<mob>.idle` and `animation.<mob>.walk` (loop) — plus `animation.<mob>.attack` (one-shot, `loop: once`,
windup → impact → recovery → rest) for hostile and neutral mobs, which the entity triggers on every hit; the staged rig
already carries all three; if you build your own, write all three — `bbmodel_geckolib_validate` with
`require_idle_walk: true` passing, `bbmodel_render` used at least once to look at the result (rest + a walk frame),
and both exports written with `overwrite: true` when re-exporting.
Texture: do not paint pixels by hand. Call `mcp__minecraft-orchestra__orchestra_paint_skin {project, mob, palette, zones, surface, face}`
once the geometry is final: it paints `models/<mob>.png` at 2x (128x128 over a 64x64 layout) with a colour per zone, an optional surface per zone
(`flesh`, `rotten`, `hide`, `cloth`: mottling, veins, growths, scars, grime), face shading, edges and a head face (`angry`, `calm` or `grim`: small
deep-set eyes for anything grotesque) whose colours are pushed apart until they stand out, and returns the contrast report (`face_check.ok` must be
true; `orchestra_check_skin` measures any PNG). The colours come from the art direction and the palette of the task packet, never from an example and
never from habit; no regular stripes unless the art direction asks for them; honour its `reference` and `avoid`; and if it says hulking or massive,
reshape the cubes (thick shoulders and arms, a small head) before painting. Then `bbmodel_geckolib_set_texture` and `bbmodel_render` to look at it:
eyes and mouth must be readable at a glance and the creature must look like its art direction, not like a toy. Report the four file paths in `changed_files`
(relative to the workspace, e.g. `models/<mob>.geo.json`) and the validator result under `checks_run`.
Never touch `src/` or `assets/` yourself: the controller installs the exports over the placeholders.
"""


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"{path.name}: {exc}")


def required_clips(mob_id: str, behavior: str = "passive") -> list[str]:
    """idle + walk always; attack when the entity class triggers it (hostile and neutral mobs)."""
    clips = [f"animation.{mob_id}.idle", f"animation.{mob_id}.walk"]
    if behavior in ("hostile", "neutral"):
        clips.append(f"animation.{mob_id}.attack")
    return clips


def validate_model_files(workspace: Path, mob_id: str, behavior: str = "passive", needs_held_item: bool = False) -> dict:
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
    for req in required_clips(mob_id, behavior):
        if req not in clips:
            raise InputError(f"animation.json lacks {req} (has: {', '.join(clips) or 'none'})")
    unknown = sorted({b for c in clips.values() for b in (c.get("bones") or {}) if b not in bones})
    if unknown:
        raise InputError(f"animation.json animates bones that are not in geo.json: {unknown}")
    # Structure the renderer assumes (learned from boss-scale rigs): one root, acyclic parents, keys inside the clip,
    # every box-UV strip inside the atlas.
    parents = {b["name"]: b.get("parent") for b in g["bones"]}
    if needs_held_item and "held_item" not in parents:
        raise InputError("geo.json lacks the `held_item` bone: the entity holds a weapon and draws it on an empty bone named held_item at the right palm "
                         "(a child of the forearm); add it back, or set the mob's held_item to none in the spec")
    roots = [n for n, p in parents.items() if not p]
    if len(roots) != 1:
        raise InputError(f"geo.json must have exactly one root bone, found {roots}")
    for n in parents:
        seen, cur = set(), n
        while cur:
            if cur in seen:
                raise InputError(f"geo.json bone parents form a cycle at {n}")
            seen.add(cur); cur = parents.get(cur)
            if cur is not None and cur not in parents:
                raise InputError(f"geo.json bone {n} points at unknown parent {cur}")
    for name, c in clips.items():
        length = float(c.get("animation_length") or 0)
        for b, chans in (c.get("bones") or {}).items():
            for ch, keys in chans.items():
                if isinstance(keys, dict):
                    for t in keys:
                        try:
                            tt = float(t)
                        except ValueError:
                            raise InputError(f"{name}/{b}/{ch}: keyframe time {t!r} is not a number")
                        if not (0 <= tt <= length + 1e-6):
                            raise InputError(f"{name}/{b}/{ch}: keyframe at {t}s is outside the clip length {length}s")
    tw, th = int(desc.get("texture_width") or 0), int(desc.get("texture_height") or 0)
    for b in g["bones"]:
        for cube in b.get("cubes") or []:
            uv, size = cube.get("uv"), cube.get("size")
            if isinstance(uv, list) and len(uv) == 2 and isinstance(size, list) and len(size) == 3:
                w_, h_, d_ = (max(1, int(abs(v))) for v in size)
                if uv[0] < 0 or uv[1] < 0 or uv[0] + 2 * d_ + 2 * w_ > tw or uv[1] + d_ + h_ > th:
                    raise InputError(f"geo.json bone {b['name']}: a cube's box-UV strip at {uv} ({2*d_+2*w_}x{d_+h_}) leaves the {tw}x{th} texture")
    png = files["png"].read_bytes()
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise InputError("texture is not a PNG")
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    tw, th = desc.get("texture_width"), desc.get("texture_height")
    ok = tw and th and w % int(tw) == 0 and h % int(th) == 0 and w // int(tw) == h // int(th) and w >= int(tw)
    if not ok:   # the PNG may be the UV resolution or an integer multiple of it (2x/4x hi-res skins)
        raise InputError(f"texture is {w}x{h} but geo declares {tw}x{th} (the PNG must be that size or a uniform integer multiple of it)")
    cubes = sum(len(b.get("cubes", [])) for b in g["bones"])
    face = None
    try:   # informational: how much the head's front face stands out (a visor or helmet may be flat on purpose, so this never blocks the install)
        from .skin import face_report
        face = face_report(json.loads(files["bbmodel"].read_text(encoding="utf8")), png)
    except (OSError, ValueError, KeyError, TypeError):
        face = None
    return {"bones": sorted(bones), "cubes": cubes, "animations": sorted(clips), "texture": [w, h], "face": face,
            "files": {k: str(v.relative_to(workspace)).replace("\\", "/") for k, v in files.items()}}


def install_model(store: Store, pid: str, mob_id: str, *, run_id: str, actor: str) -> dict:
    """Validate and copy the designer's exports over the placeholder assets, as a manifest revision."""
    proj = store.project(pid)
    ws = Path(proj["root"])
    from .specedit import _load
    mob = next((x for x in _load(store, pid).mobs if x.identifier == mob_id), None)
    from .geckolib import held_item_for
    info = validate_model_files(ws, mob_id, mob.behavior if mob else "passive",
                                needs_held_item=bool(mob and held_item_for(_load(store, pid), mob)))
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
from .geckolib import (entity_java, renderer_java, client_init_java, main_registrations, placeholder_geo, placeholder_animation, placeholder_texture_size,
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
    put(assets / "textures/entity" / f"{mob.identifier}.png", placeholder_png(pid + "/entity/" + mob.identifier, *placeholder_texture_size(mob)))
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
Minecraft's own style is 16x16 with soft shading, no anti-aliasing.
Art direction: every item comes with a concept, visual cues and sometimes a silhouette. Paint what they describe: invent a shape that carries
the cues (an item that is described as unusual must not come out as the stock icon of its kind), use the palette hues, and
put at least two of the cues where they can be seen at 1x. Pieces of one set share palette and motifs but each has its own silhouette.
The controller REJECTS a sprite whose silhouette is 85% or more the stock template of its kind, one that is a copy of another sprite of the batch
(85% identical pixels), and one with fewer than 4 colours. Before you finish, call `mcp__minecraft-orchestra__orchestra_check_sprites {project}`
and repaint everything it lists as rejected until it lists none. Then write a contact sheet
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


def request_sprites(store: Store, pid: str, identifiers: list[str], notes: str = "", armor_materials: list[str] | None = None, *, initial: bool = False) -> dict:
    """The task that paints icons (and worn-armor layers). `initial` is the controller's own first design of everything; otherwise it is the user's
    redesign: icons the designer already painted need a note saying what should change, and the designer receives every earlier note (newest first)."""
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
    ws = Path(proj["root"])
    painted = [i for i in identifiers if (ws / "models" / "sprites" / f"{i}.png").is_file()] + \
              [f"{a}_layer_{n}" for a in armor_materials for n in (1, 2) if (ws / "models" / "sprites" / f"{a}_layer_{n}.png").is_file()]
    if painted and not initial and not notes.strip():
        raise InputError("These icons were already designed: say what should change (the designer edits its previous work and repaints only that). "
                         "Example: 'the sword blade is too thin and the grip needs a red wrap'.")
    n = sum(1 for t in store.tasks(pid) if ":SPRITES:" in t["id"]) + 1
    task_id = f"{pid}:SPRITES:{n}"
    from .art import brief as art_brief, effective_art
    from .spritecheck import catalogue as sprite_catalogue
    art_kinds = {i: v["art_kind"] for i, v in sprite_catalogue(spec).items()}
    lines = [user_words(store, pid, "these items"), "Sprites to paint (identifier → what it is, then its art direction; paint THAT, not the stock icon of its kind):"]
    for i in identifiers:
        lines.append(f"- {i}: {catalogue[i]['label']} ({catalogue[i]['kind']}{', ' + catalogue[i]['hint'] if catalogue[i]['hint'] else ''})")
        lines += ["    " + l for l in art_brief(spec, art_kinds[i], i, palette=False).splitlines()]
    sets = [m for m in spec.materials if any(f"{m.identifier}_{k}" in identifiers for k in tuple(m.tools) + tuple(m.armor))]
    for m in sets:
        lines += ["", f"Set {m.identifier} ({m.label}): pieces share this palette and these motifs, and differ in silhouette and details.", *["    " + l for l in art_brief(spec, "set", m.identifier, palette=False).splitlines()]]
    pal = effective_art(spec, art_kinds[identifiers[0]], identifiers[0])["palette"] if identifiers else []
    if pal:
        lines += ["", "Palette from the mod's theme (use these hues, with their light and dark steps): " + "; ".join(f"{p['name']} {p['hex']}" for p in pal)]
    if armor_materials:
        lines += ["", "Worn-armor layers to paint for material(s): " + ", ".join(f"{a} (pieces: {', '.join(mats[a].armor)})" for a in armor_materials), ARMOR_LAYER_GUIDE]
    if painted and not initial:
        earlier = [e["payload"]["notes"] for e in store.events(pid, 500) if e["kind"] == "SPRITES_REQUESTED" and e["payload"].get("notes")
                   and (set(e["payload"].get("items") or []) & set(identifiers) or set(e["payload"].get("armor") or []) & set(armor_materials))]
        lines += ["", f"REDESIGN: {len(painted)} of these were already painted by you. Their previous versions are in `models/sprites/` and the script is `models/sprites/paint.py`:",
                  "edit that script and repaint only what the feedback asks for; keep every sprite and detail it does not mention, and keep the art direction above.",
                  "", "User feedback (newest first):", f"- {notes.strip()[:800]}"] + [f"- {t}" for t in reversed(earlier[-6:])]
    elif notes.strip():
        lines += ["", "Style notes from the user:", notes.strip()[:800]]
    if initial:
        lines += ["", "First design of every icon in this mod: the placeholders in the game are tinted stock templates, replace them all."]
    title = ("Redesign" if painted and not initial else "Design" if initial else "Paint")
    store.add_task(pid, task_id, "designer", f"{title} {len(identifiers)} item sprite(s)" + (f" + armor layers for {', '.join(armor_materials)}" if armor_materials else ""))
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(lines)))
    store.add_event(pid, "controller" if initial else "user", "SPRITES_REQUESTED", {"task": task_id, "items": identifiers, "armor": armor_materials, "notes": notes[:600], "initial": initial})
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


def ensure_initial_sprites(store: Store, pid: str) -> dict | None:
    """Right after generation (and when Autopilot meets an older project) create the one task that designs every icon and the worn-armor layers of
    textured sets, so nobody has to ask for it: the placeholders are tinted stock templates. Skips what the user uploaded and does nothing once any
    SPRITES task exists, so a redesign never triggers it again. Autopilot dispatches the task like a MODEL task."""
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        return None
    if any(":SPRITES:" in t["id"] for t in store.tasks(pid)):
        return None
    from .spritecheck import catalogue
    spec = read_spec(proj["spec"])
    uploaded = {e["payload"].get("identifier") for e in store.events(pid, 1000) if e["kind"] == "TEXTURE_UPLOADED" and e["payload"].get("kind") in ("item", "block")}
    uploaded_layers = {e["payload"].get("identifier") for e in store.events(pid, 1000) if e["kind"] == "TEXTURE_UPLOADED" and str(e["payload"].get("kind", "")).startswith("armor_layer")}
    identifiers = [i for i in catalogue(spec) if i not in uploaded]
    armor = [m.identifier for m in spec.materials if m.armor and m.armor_style != "3d" and m.identifier not in uploaded_layers]
    if not identifiers and not armor:
        return None
    return request_sprites(store, pid, identifiers, armor_materials=armor, initial=True)


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
    staged: dict[str, tuple[Path, str]] = {}
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
        staged[ident] = (src, f"src/main/resources/assets/{pid}/textures/{'block' if ident in blocks else 'item'}/{ident}.png")
    from .spritecheck import check_sprites
    creative = check_sprites(spec, {i: s.read_bytes() for i, (s, _) in staged.items()})   # the stock template, a copy of a sibling, too few colours
    for ident, (src, rel) in staged.items():
        if ident in creative:
            rejected[ident] = creative[ident]; continue
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
    lines = [user_words(store, pid, f"the {m.label} armor"), f"Material: {material} ({m.label}); pieces: {', '.join(m.armor)}; material colour hint: {m.color or 'derive from icons'}"]
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
