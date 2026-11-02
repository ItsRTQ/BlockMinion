"""Items and blocks after generation (UI "Features → Items"): add, rename, list.

Same pattern as adding a mob: the controller writes the feature's own new files deterministically
(exactly what the generator would have produced), merges the lang file, updates the spec, and
hands the one shared-file edit (ModMain constant + creative-tab line) to a coder task with the
exact snippet. Removal after generation is not offered (it would need code surgery across files);
before generation the spec is simply edited.
"""
from __future__ import annotations
import json
import re
from dataclasses import replace
from pathlib import Path

from .fabric import accept_changes, loot_table_json, placeholder_png, feature_texture
from .textures import tinted_item_png, armor_layer_png, material_colors, palette_from_png
from .spec import Feature, check_java_name_collisions, read_spec, validate_spec_content
from .state import Store, StateError
from .validation import InputError, normalize_id

GENERATED_STATUSES = ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED")


def _armor_previews(store: Store, pid: str, ws: Path, material: str) -> list[str]:
    root = ws / ".mod-orchestra" / "previews"
    if not root.is_dir():
        return []
    runs = {r["id"]: r.get("created_at", 0) for r in store.runs(pid)}
    dirs = sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: runs.get(d.name, 0))
    for d in reversed(dirs):
        files = sorted(d.glob(f"{material}_armor_layer*.png"))
        if files:
            return [f".mod-orchestra/previews/{d.name}/{f.name}" for f in files]
    return []


def latest_contact_sheet(store: Store, pid: str) -> str | None:
    root = Path(store.project(pid)["root"]) / ".mod-orchestra" / "previews"
    runs = {r["id"]: r.get("created_at", 0) for r in store.runs(pid)}
    sheets = sorted(root.glob("*/sprites_contact_sheet.png"), key=lambda p: runs.get(p.parent.name, 0)) if root.is_dir() else []
    return f".mod-orchestra/previews/{sheets[-1].parent.name}/sprites_contact_sheet.png" if sheets else None


def list_features(store: Store, pid: str) -> list[dict]:
    proj = store.project(pid)
    ws = Path(proj["root"]); assets = ws / "src/main/resources/assets" / pid
    spec = proj["spec"]
    out = []
    for f in spec.get("features", []):
        kind = f["kind"]; key = f["identifier"]
        tex = f"src/main/resources/assets/{pid}/textures/{'block' if kind == 'block' else 'item'}/{key}.png"
        out.append({"kind": kind, "identifier": key, "label": f["label"], "texture": tex if (ws / tex).is_file() else None,
                    "recipes": [r["id"] for r in spec.get("recipes", []) if r["result"] == key or key in json.dumps(r)],
                    "drop": next((d for d in spec.get("drops", []) if d["block"] == key), None)})
    for m in spec.get("materials", []):
        for kind in list(m.get("tools", [])) + list(m.get("armor", [])):
            key = f"{m['identifier']}_{kind}"; tex = f"src/main/resources/assets/{pid}/textures/item/{key}.png"
            out.append({"kind": "tool" if kind in ("sword", "pickaxe", "axe", "shovel", "hoe") else "armor", "identifier": key, "label": f"{m['label']} {kind.capitalize()}",
                        "texture": tex if (ws / tex).is_file() else None, "material": m["identifier"], "recipes": [key] if m.get("recipes", True) else [], "drop": None,
                        "armor_layers": [f"src/main/resources/assets/{pid}/textures/models/armor/{m['identifier']}_layer_{n}.png" for n in (1, 2)] if kind in ("helmet", "chestplate", "leggings", "boots") else None,
                        "armor_previews": _armor_previews(store, pid, ws, m["identifier"]) if kind == "helmet" else None})
    for f in spec.get("foods", []):
        tex = f"src/main/resources/assets/{pid}/textures/item/{f['identifier']}.png"
        out.append({"kind": "food", "identifier": f["identifier"], "label": f["label"], "texture": tex if (ws / tex).is_file() else None,
                    "food": {"nutrition": f["nutrition"], "saturation": f["saturation"], "effects": f.get("effects", [])}, "recipes": [], "drop": None})
    return out


def _save_spec(store: Store, pid: str, spec, reason: str) -> None:
    validate_spec_content(spec)
    with store.tx() as con:
        con.execute("UPDATE projects SET spec_json=? WHERE id=?", (json.dumps(spec.to_dict(), sort_keys=True), pid))
        store.event(con, pid, "user", "SPEC_CHANGED", {"reason": reason})


def add_feature(store: Store, pid: str, *, kind: str, label: str, identifier: str | None = None, shape: str = "", color: str = "") -> dict:
    """Before generation: spec edit (approval reset). After generation: files + coder task."""
    if kind not in ("item", "block"):
        raise InputError("kind must be item or block")
    proj = store.project(pid)
    spec = read_spec(proj["spec"])
    ident = normalize_id(identifier or label, content=True)
    if ident in spec.local_ids() or any(m.identifier == ident for m in spec.mobs):
        raise InputError(f"{ident!r} already exists in this mod")
    if shape and shape not in ("gem", "ingot", "food", "block"):
        raise InputError("shape must be gem, ingot, food or block")
    if color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise InputError("color must be #RRGGBB")
    feature = Feature(kind=kind, identifier=ident, label=label.strip() or ident, shape=shape, color=color)
    new_spec = replace(spec, features=list(spec.features) + [feature])
    check_java_name_collisions(new_spec.features)
    if proj["status"] not in GENERATED_STATUSES:
        from .specedit import _save
        return _save(store, pid, new_spec, f"add {kind} {ident}") | {"identifier": ident, "generated": False}
    ws = Path(proj["root"]); res = ws / "src/main/resources"; assets = res / "assets" / pid
    written: list[str] = []

    def put(rel: Path, data: bytes):
        if rel.exists():
            raise InputError(f"Refusing to overwrite {rel.relative_to(ws)}")
        rel.parent.mkdir(parents=True, exist_ok=True); rel.write_bytes(data); written.append(str(rel.relative_to(ws)).replace("\\", "/"))

    if kind == "item":
        put(assets / "models/item" / f"{ident}.json", (json.dumps({"parent": "item/generated", "textures": {"layer0": f"{pid}:item/{ident}"}}, indent=2) + "\n").encode())
        put(assets / "textures/item" / f"{ident}.png", feature_texture(new_spec, feature))
    else:
        put(assets / "blockstates" / f"{ident}.json", (json.dumps({"variants": {"": {"model": f"{pid}:block/{ident}"}}}, indent=2) + "\n").encode())
        put(assets / "models/block" / f"{ident}.json", (json.dumps({"parent": "block/cube_all", "textures": {"all": f"{pid}:block/{ident}"}}, indent=2) + "\n").encode())
        put(assets / "models/item" / f"{ident}.json", (json.dumps({"parent": f"{pid}:block/{ident}"}, indent=2) + "\n").encode())
        put(assets / "textures/block" / f"{ident}.png", feature_texture(new_spec, feature))
        put(res / "data" / pid / "loot_table/blocks" / f"{ident}.json", (json.dumps(loot_table_json(new_spec, ident, None), indent=2) + "\n").encode())
    lang_file = assets / "lang/en_us.json"
    lang = json.loads(lang_file.read_text(encoding="utf8")) if lang_file.is_file() else {}
    lang[f"{'block' if kind == 'block' else 'item'}.{pid}.{ident}"] = feature.label
    lang_file.write_text(json.dumps(lang, indent=2, sort_keys=True) + "\n", encoding="utf8"); written.append(f"src/main/resources/assets/{pid}/lang/en_us.json")
    _save_spec(store, pid, new_spec, f"add {kind} {ident} after generation")
    accepted = accept_changes(ws, run_id=f"add-{kind}:{ident}", actor="user", changed=written)
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid)
    const = ident.upper()
    if kind == "item":
        lines = [f'    public static final Item {const} = Registry.register(BuiltInRegistries.ITEM, id("{ident}"), new Item(new Item.Properties()));']
        tab_line = f"            output.accept({const});"; group = "INGREDIENTS"; accept_const = const
    else:
        lines = [f'    public static final Block {const} = Registry.register(BuiltInRegistries.BLOCK, id("{ident}"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));',
                 f'    public static final Item {const}_ITEM = Registry.register(BuiltInRegistries.ITEM, id("{ident}"), new BlockItem({const}, new Item.Properties()));']
        tab_line = f"            output.accept({const}_ITEM);"; group = "BUILDING_BLOCKS"; accept_const = const + "_ITEM"
    java_dir = f"src/main/java/{spec.package.replace('.', '/')}"
    instructions = [f"Register the new {kind} in {java_dir}/ModMain.java (do not touch anything else):",
                    "1. Add the static field(s) next to the other content fields:"] + ["   " + l for l in lines] + [
                    "2. In onInitialize(), add the vanilla creative-tab line:",
                    f"   ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.{group}).register(entries -> entries.accept({accept_const}));",
                    "3. If the mod has its own creative tab (a TAB field with displayItems), also add inside displayItems:", "   " + tab_line.strip(),
                    "4. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    task_id = f"{pid}:ADD_{kind.upper()}:{ident}"
    store.add_task(pid, task_id, "coder", f"Register new {kind} {feature.label} in ModMain")
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(instructions)))
    _reopen_build(store, pid)
    store.add_event(pid, "controller", "FEATURE_ADDED", {"kind": kind, "identifier": ident, "files": written, "task": task_id})
    return {"identifier": ident, "kind": kind, "generated": True, "files": written, "accepted": accepted["accepted"], "task": task_id,
            "next": {"action": "dispatch", "payload": {"task": task_id}}}


def rename_feature(store: Store, pid: str, identifier: str, label: str) -> dict:
    """Display name only (lang). The identifier never changes."""
    label = label.strip()
    if not (1 <= len(label) <= 60):
        raise InputError("Label must be 1-60 characters")
    proj = store.project(pid); spec = read_spec(proj["spec"])
    f = next((x for x in spec.features if x.identifier == identifier), None)
    if f is None:
        raise InputError(f"Unknown feature {identifier!r}")
    new_spec = replace(spec, features=[replace(x, label=label) if x.identifier == identifier else x for x in spec.features])
    out = {"identifier": identifier, "label": label}
    if proj["status"] in GENERATED_STATUSES:
        ws = Path(proj["root"]); lang_file = ws / "src/main/resources/assets" / pid / "lang/en_us.json"
        lang = json.loads(lang_file.read_text(encoding="utf8")) if lang_file.is_file() else {}
        lang[f"{'block' if f.kind == 'block' else 'item'}.{pid}.{identifier}"] = label
        lang_file.write_text(json.dumps(lang, indent=2, sort_keys=True) + "\n", encoding="utf8")
        rel = f"src/main/resources/assets/{pid}/lang/en_us.json"
        accept_changes(ws, run_id=f"rename:{identifier}", actor="user", changed=[rel])
        _save_spec(store, pid, new_spec, f"rename {identifier}")
        from .dispatch import _source_changed, _reopen_build
        _source_changed(store, pid); _reopen_build(store, pid)
        out |= {"file": rel, "note": "Lang updated; rebuild to apply."}
    else:
        from .specedit import _save
        _save(store, pid, new_spec, f"rename {identifier}")
    return out


def remove_feature(store: Store, pid: str, identifier: str) -> dict:
    proj = store.project(pid)
    if proj["status"] in GENERATED_STATUSES:
        raise StateError("Removing content after generation is not supported yet; ask a coder task to remove it, or create a new project")
    spec = read_spec(proj["spec"])
    if identifier not in spec.local_ids():
        raise InputError(f"Unknown feature {identifier!r}")
    used = [r.id for r in spec.recipes if r.result == identifier or identifier in r.key.values() or identifier in r.ingredients] + \
           [f"drop:{d.block}" for d in spec.drops if identifier in (d.block, d.item)] + \
           [f"tab icon" for _ in [0] if spec.tab_icon == identifier] + [f"mob drop:{m.identifier}" for m in spec.mobs for d in m.drops if getattr(d, "item", d) == identifier]
    if used:
        raise InputError(f"{identifier} is used by: {', '.join(used)} — remove those first")
    from .specedit import _save
    return _save(store, pid, replace(spec, features=[x for x in spec.features if x.identifier != identifier]), f"remove {identifier}") | {"removed": identifier}


# ---------------------------------------------------------------------------------------------
# Materials (tool/armor sets) and foods after generation: same shape as add_feature.
# ---------------------------------------------------------------------------------------------
def _write_gear_files(ws: Path, pid: str, package: str, new_spec, material=None, food=None) -> list[str]:
    from .gear import tier_java, cls as gear_cls, gear_recipes
    from .fabric import recipe_json, recipe_advancement_json
    res = ws / "src/main/resources"; assets = res / "assets" / pid; java_dir = ws / "src/main/java" / package.replace(".", "/")
    written: list[str] = []

    def put(rel: Path, data: bytes):
        if rel.exists():
            raise InputError(f"Refusing to overwrite {rel.relative_to(ws)}")
        rel.parent.mkdir(parents=True, exist_ok=True); rel.write_bytes(data); written.append(str(rel.relative_to(ws)).replace("\\", "/"))

    lang_file = assets / "lang/en_us.json"
    lang = json.loads(lang_file.read_text(encoding="utf8")) if lang_file.is_file() else {}
    if material:
        m = material
        base, acc = material_colors(pid + "/" + m.identifier, m.color or None, m.accent or None)
        put(java_dir / "gear" / f"{gear_cls(m.identifier)}Tier.java", tier_java(new_spec, m).encode())
        for kind in m.tools:
            key = f"{m.identifier}_{kind}"
            put(assets / "models/item" / f"{key}.json", (json.dumps({"parent": "item/handheld", "textures": {"layer0": f"{pid}:item/{key}"}}, indent=2) + "\n").encode())
            put(assets / "textures/item" / f"{key}.png", tinted_item_png(kind, base, acc)); lang[f"item.{pid}.{key}"] = f"{m.label} {kind.capitalize()}"
        for kind in m.armor:
            key = f"{m.identifier}_{kind}"
            put(assets / "models/item" / f"{key}.json", (json.dumps({"parent": "item/generated", "textures": {"layer0": f"{pid}:item/{key}"}}, indent=2) + "\n").encode())
            put(assets / "textures/item" / f"{key}.png", tinted_item_png("ingot" if kind in ("chestplate", "leggings") else "gem", base, acc)); lang[f"item.{pid}.{key}"] = f"{m.label} {kind.capitalize()}"
        if m.armor:
            put(assets / "textures/models/armor" / f"{m.identifier}_layer_1.png", armor_layer_png(1, base, acc, tuple(m.armor)))
            put(assets / "textures/models/armor" / f"{m.identifier}_layer_2.png", armor_layer_png(2, base, acc, tuple(m.armor)))
        for r in gear_recipes(replace(new_spec, materials=[m])):
            put(res / "data" / pid / "recipe" / f"{r.id}.json", (json.dumps(recipe_json(new_spec, r), indent=2) + "\n").encode())
            put(res / "data" / pid / "advancement/recipes" / f"{r.id}.json", (json.dumps(recipe_advancement_json(new_spec, r), indent=2) + "\n").encode())
    if food:
        f = food
        put(assets / "models/item" / f"{f.identifier}.json", (json.dumps({"parent": "item/generated", "textures": {"layer0": f"{pid}:item/{f.identifier}"}}, indent=2) + "\n").encode())
        base, acc = material_colors(pid + "/" + f.identifier, f.color or None)
        put(assets / "textures/item" / f"{f.identifier}.png", tinted_item_png("food", base, acc)); lang[f"item.{pid}.{f.identifier}"] = f.label
    lang_file.write_text(json.dumps(lang, indent=2, sort_keys=True) + "\n", encoding="utf8"); written.append(f"src/main/resources/assets/{pid}/lang/en_us.json")
    return written


def _gear_task(store: Store, pid: str, ws: Path, package: str, new_spec, only_spec, kind_label: str, ident: str, written: list[str]) -> dict:
    from .gear import gear_registrations, gear_item_ids
    imports, fields, init = gear_registrations(only_spec)
    accepted = accept_changes(ws, run_id=f"add-{kind_label}:{ident}", actor="user", changed=written)
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid)
    java_dir = f"src/main/java/{package.replace('.', '/')}"
    instructions = [f"Register the new {kind_label} '{ident}' in {java_dir}/ModMain.java (do not touch anything else):",
                    "1. Add these imports if missing:"] + ["   import " + i + ";" for i in imports] + [
                    "2. Add the static fields next to the other content fields (order matters: keep them after the plain items/blocks):"] + ["   " + l for l in fields] + [
                    "3. In onInitialize(), add:"] + ["   " + l.strip() for l in init] + [
                    "4. If the mod has its own creative tab (TAB with displayItems), also add inside displayItems:"] + [f"   output.accept({i.upper()});" for i in gear_item_ids(only_spec)] + [
                    "5. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    task_id = f"{pid}:ADD_{kind_label.upper()}:{ident}"
    store.add_task(pid, task_id, "coder", f"Register new {kind_label} {ident} in ModMain")
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(instructions)))
    _reopen_build(store, pid)
    store.add_event(pid, "controller", "FEATURE_ADDED", {"kind": kind_label, "identifier": ident, "files": written, "task": task_id})
    return {"identifier": ident, "kind": kind_label, "generated": True, "files": written, "accepted": accepted["accepted"], "task": task_id,
            "next": {"action": "dispatch", "payload": {"task": task_id}}}


def add_material_any(store: Store, pid: str, **kw) -> dict:
    from .spec import Material
    from .specedit import add_material
    proj = store.project(pid)
    if proj["status"] not in GENERATED_STATUSES:
        return add_material(store, pid, **kw) | {"generated": False}
    spec = read_spec(proj["spec"])
    mat = Material(identifier=kw["identifier"], label=kw["label"], ingredient=kw["ingredient"], tools=tuple(kw.get("tools") or ()), armor=tuple(kw.get("armor") or ()),
                   **{k: v for k, v in kw.items() if k not in ("identifier", "label", "ingredient", "tools", "armor") and v is not None})
    if any(m.identifier == mat.identifier for m in spec.materials):
        raise InputError(f"Material {mat.identifier!r} already exists")
    new_spec = replace(spec, materials=list(spec.materials) + [mat]); validate_spec_content(new_spec)
    ws = Path(proj["root"])
    written = _write_gear_files(ws, pid, spec.package, new_spec, material=mat)
    _save_spec(store, pid, new_spec, f"add material {mat.identifier} after generation")
    return _gear_task(store, pid, ws, spec.package, new_spec, replace(new_spec, materials=[mat], foods=[]), "material", mat.identifier, written)


def add_food_any(store: Store, pid: str, **kw) -> dict:
    from .spec import Food
    from .specedit import add_food
    proj = store.project(pid)
    if proj["status"] not in GENERATED_STATUSES:
        return add_food(store, pid, **kw) | {"generated": False}
    spec = read_spec(proj["spec"])
    food = Food(identifier=kw["identifier"], label=kw["label"], nutrition=int(kw.get("nutrition", 4)), saturation=float(kw.get("saturation", 0.3)),
                effects=tuple(kw.get("effects") or ()), always_edible=bool(kw.get("always_edible")), fast=bool(kw.get("fast")))
    if food.identifier in spec.local_ids():
        raise InputError(f"{food.identifier!r} already exists")
    new_spec = replace(spec, foods=list(spec.foods) + [food]); validate_spec_content(new_spec)
    ws = Path(proj["root"])
    written = _write_gear_files(ws, pid, spec.package, new_spec, food=food)
    _save_spec(store, pid, new_spec, f"add food {food.identifier} after generation")
    return _gear_task(store, pid, ws, spec.package, new_spec, replace(new_spec, materials=[], foods=[food]), "food", food.identifier, written)


# ---------------------------------------------------------------------------------------------
# User-supplied textures (UI upload): replaces a placeholder PNG as a user revision.
# ---------------------------------------------------------------------------------------------
import base64 as _b64
import struct as _struct

TEXTURE_TARGETS = {
    "item": ("textures/item/{id}.png", (16, 16)), "block": ("textures/block/{id}.png", (16, 16)),
    "entity": ("textures/entity/{id}.png", None), "armor_layer_1": ("textures/models/armor/{id}_layer_1.png", (64, 32)),
    "armor_layer_2": ("textures/models/armor/{id}_layer_2.png", (64, 32)),
}


def set_texture(store: Store, pid: str, *, kind: str, identifier: str, png_base64: str) -> dict:
    if kind not in TEXTURE_TARGETS:
        raise InputError(f"kind must be one of {sorted(TEXTURE_TARGETS)}")
    proj = store.project(pid)
    if proj["status"] not in GENERATED_STATUSES:
        raise StateError("Generate the project first; textures are files in the workspace")
    try:
        raw = _b64.b64decode(png_base64, validate=True)
    except Exception:
        raise InputError("png_base64 is not valid base64")
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 2_000_000:
        raise InputError("Not a PNG (or larger than 2 MB)")
    w, h = _struct.unpack(">II", raw[16:24])
    rel_tpl, expected = TEXTURE_TARGETS[kind]
    if expected and (w, h) != expected:
        raise InputError(f"{kind} textures must be {expected[0]}x{expected[1]} pixels; got {w}x{h}")
    if kind == "entity" and not (w in (32, 64, 128) and h in (32, 64, 128)):
        raise InputError("entity textures must be 32/64/128 square-ish (e.g. 64x32 or 64x64)")
    spec = read_spec(proj["spec"])
    known = spec.local_ids() | {m.identifier for m in spec.mobs} | {m.identifier for m in spec.materials}
    if identifier not in known:
        raise InputError(f"Unknown identifier {identifier!r}")
    ws = Path(proj["root"])
    rel = f"src/main/resources/assets/{pid}/" + rel_tpl.format(id=identifier)
    target = ws / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    accepted = accept_changes(ws, run_id=f"texture:{identifier}", actor="user", changed=[rel])
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "user", "TEXTURE_UPLOADED", {"kind": kind, "identifier": identifier, "file": rel, "size": [w, h]})
    return {"file": rel, "size": [w, h], "accepted": accepted["accepted"], "note": "Texture installed; rebuild to see it in-game."}


def retint_armor(store: Store, pid: str, material: str, color: str = "", accent: str = "", match_icon: bool = False) -> dict:
    """Rewrite a material's tool/armor icon textures and both worn-armor layers with the tinted silhouettes
    (deterministic; for projects generated before tinting or when the colour changes)."""
    proj = store.project(pid)
    if proj["status"] not in GENERATED_STATUSES:
        raise StateError("Generate the project first")
    spec = read_spec(proj["spec"])
    m = next((x for x in spec.materials if x.identifier == material), None)
    if m is None:
        raise InputError(f"Unknown material {material!r}")
    for c in (color, accent):
        if c and not re.fullmatch(r"#[0-9a-fA-F]{6}", c):
            raise InputError("colours must be #RRGGBB")
    if color or accent:
        new_m = replace(m, color=color or m.color, accent=accent or m.accent)
        _save_spec(store, pid, replace(spec, materials=[new_m if x.identifier == material else x for x in spec.materials]), f"retint {material}")
        m = new_m
    base, acc = material_colors(pid + "/" + m.identifier, m.color or None, m.accent or None)
    ws = Path(proj["root"]); assets = ws / "src/main/resources/assets" / pid
    source_icon = None
    if match_icon:
        for kind in ("chestplate", "helmet", "leggings", "boots"):
            icon = assets / "textures/item" / f"{m.identifier}_{kind}.png"
            if icon.is_file():
                pal = palette_from_png(icon.read_bytes())
                if pal:
                    base, acc = pal; source_icon = f"{m.identifier}_{kind}.png"; break
    written = []
    # Only the worn-armor layers: inventory icons may be designer- or user-made and are never overwritten here.
    if m.armor:
        for n in (1, 2):
            rel = assets / "textures/models/armor" / f"{m.identifier}_layer_{n}.png"; rel.parent.mkdir(parents=True, exist_ok=True)
            rel.write_bytes(armor_layer_png(n, base, acc, tuple(m.armor))); written.append(rel)
    rels = [str(w.relative_to(ws)).replace("\\", "/") for w in written]
    accepted = accept_changes(ws, run_id=f"retint:{material}", actor="user", changed=rels)
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "user", "ARMOR_RETINTED", {"material": material, "files": rels, "from_icon": source_icon})
    return {"material": material, "files": rels, "accepted": accepted["accepted"], "from_icon": source_icon,
            "note": (f"Worn-armor layers painted with the palette of {source_icon}" if source_icon else "Worn-armor layers rewritten") + " (icons untouched); rebuild to apply."}


def restore_designer_sprites(store: Store, pid: str) -> dict:
    """Reinstall every sprite the designer left in models/sprites/ (icons and armor layers) over the current textures."""
    from .models import install_sprites
    proj = store.project(pid); ws = Path(proj["root"]); spec = read_spec(proj["spec"])
    folder = ws / "models" / "sprites"
    if not folder.is_dir():
        raise StateError("No designer sprites in models/sprites/")
    known = spec.local_ids()
    ids = sorted(p.stem for p in folder.glob("*.png") if p.stem in known)
    mats = sorted({m.identifier for m in spec.materials if m.armor and (folder / f"{m.identifier}_layer_1.png").is_file()})
    if not ids and not mats:
        raise StateError("models/sprites/ has no sprites matching this mod's content")
    return install_sprites(store, pid, "restore", ids, run_id=f"restore-{int(__import__('time').time())}", actor="user", armor_materials=mats)
