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
from .spec import Feature, TOOL_KINDS, check_java_name_collisions, read_spec, validate_spec_content
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
        files = sorted(d.glob(f"{material}_armor_layer*.png")) + sorted(d.glob(f"{material}_armor_render*.png"))
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
                    "drop": next((d for d in spec.get("drops", []) if d["block"] == key), None),
                    "ore": next((o for o in spec.get("ores", []) if o["block"] == key), None)})
    for m in spec.get("materials", []):
        for kind in list(m.get("tools", [])) + list(m.get("armor", [])):
            key = f"{m['identifier']}_{kind}"; tex = f"src/main/resources/assets/{pid}/textures/item/{key}.png"
            out.append({"kind": "tool" if kind in ("sword", "pickaxe", "axe", "shovel", "hoe") else "armor", "identifier": key, "label": f"{m['label']} {kind.capitalize()}",
                        "texture": tex if (ws / tex).is_file() else None, "material": m["identifier"], "recipes": [key] if m.get("recipes", True) else [], "drop": None,
                        "armor_layers": [f"src/main/resources/assets/{pid}/textures/models/armor/{m['identifier']}_layer_{n}.png" for n in (1, 2)] if kind in ("helmet", "chestplate", "leggings", "boots") else None,
                        "armor_previews": _armor_previews(store, pid, ws, m["identifier"]) if kind == "helmet" else None, "armor_style": m.get("armor_style", "textured")})
    for f in spec.get("foods", []):
        tex = f"src/main/resources/assets/{pid}/textures/item/{f['identifier']}.png"
        out.append({"kind": "food", "identifier": f["identifier"], "label": f["label"], "texture": tex if (ws / tex).is_file() else None,
                    "food": {"nutrition": f["nutrition"], "saturation": f["saturation"], "effects": f.get("effects", [])}, "recipes": [], "drop": None})
    return out


def list_art(store: Store, pid: str) -> dict:
    """Every entity's effective art direction, keyed "kind:identifier" (item, block, tool, armor, food, set, mob): concept, tags, silhouette, source."""
    from .art import effective_art
    spec = read_spec(store.project(pid)["spec"])
    keys = [(f.kind, f.identifier, f.label) for f in spec.features] + [("food", f.identifier, f.label) for f in spec.foods] + [("mob", m.identifier, m.label) for m in spec.mobs]
    for m in spec.materials:
        keys.append(("set", m.identifier, m.label))
        keys += [("tool" if k in TOOL_KINDS else "armor", f"{m.identifier}_{k}", f"{m.label} {k}") for k in tuple(m.tools) + tuple(m.armor)]
    out = {}
    for kind, ident, label in keys:
        a = effective_art(spec, kind, ident)
        out[f"{kind}:{ident}"] = {"label": label, "kind": kind, "identifier": ident, "concept": a["concept"], "tags": a["tags"], "silhouette": a["silhouette"], "source": a["source"],
                                  "reference": a["reference"], "avoid": a["avoid"]}
    return out


def set_art(store: Store, pid: str, kind: str, identifier: str, *, concept: str = "", tags=None, silhouette: str = "", reference: str = "", avoid=None) -> dict:
    """Write the art direction of one entity. kind: item | block | food | mob | set (a whole tool/armor set: concept, tags, silhouette) | tool | armor (one piece of a set:
    its own concept sentence only). Empty fields clear it. Before generation this resets the spec approval like any spec edit; afterwards it is cosmetic."""
    from .spec import Art, coerce_art
    proj = store.project(pid); spec = read_spec(proj["spec"])
    tags = [t.strip() for t in (tags if isinstance(tags, (list, tuple)) else re.split(r"[,;\n]", str(tags or ""))) if t.strip()]
    new_art = coerce_art({"concept": concept, "tags": tags, "silhouette": silhouette, "reference": reference, "avoid": avoid or []})
    if kind in ("item", "block"):
        if not any(f.identifier == identifier and f.kind == kind for f in spec.features):
            raise InputError(f"Unknown {kind} {identifier!r}")
        new_spec = replace(spec, features=[replace(f, art=new_art) if f.identifier == identifier else f for f in spec.features])
    elif kind == "food":
        if not any(f.identifier == identifier for f in spec.foods):
            raise InputError(f"Unknown food {identifier!r}")
        new_spec = replace(spec, foods=[replace(f, art=new_art) if f.identifier == identifier else f for f in spec.foods])
    elif kind == "mob":
        if not any(m.identifier == identifier for m in spec.mobs):
            raise InputError(f"Unknown mob {identifier!r}")
        new_spec = replace(spec, mobs=[replace(m, art=new_art) if m.identifier == identifier else m for m in spec.mobs])
    elif kind == "set":
        mat = next((m for m in spec.materials if m.identifier == identifier), None)
        if mat is None:
            raise InputError(f"Unknown material {identifier!r}")
        keep = mat.art.pieces if mat.art else {}
        merged = coerce_art({"concept": concept, "tags": tags, "silhouette": silhouette, "pieces": keep, "reference": reference, "avoid": avoid or []})
        new_spec = replace(spec, materials=[replace(m, art=merged) if m.identifier == identifier else m for m in spec.materials])
    elif kind in ("tool", "armor"):
        mat = next((m for m in spec.materials if identifier.startswith(m.identifier + "_") and identifier[len(m.identifier) + 1:] in tuple(m.tools) + tuple(m.armor)), None)
        if mat is None:
            raise InputError(f"Unknown {kind} {identifier!r}")
        piece = identifier[len(mat.identifier) + 1:]
        base = mat.art or Art()
        pieces = {k: v for k, v in base.pieces.items() if k != piece}
        if concept.strip():
            pieces[piece] = concept.strip()
        merged = replace(base, pieces=pieces)
        merged = None if not (merged.concept or merged.tags or merged.silhouette or merged.pieces or merged.reference or merged.avoid) else merged
        new_spec = replace(spec, materials=[replace(m, art=merged) if m.identifier == mat.identifier else m for m in spec.materials])
    else:
        raise InputError("kind must be item, block, food, mob, set, tool or armor")
    if proj["status"] in GENERATED_STATUSES:
        _save_spec(store, pid, new_spec, f"art {kind}:{identifier}")
    else:
        from .specedit import _save
        _save(store, pid, new_spec, f"art {kind}:{identifier}")
    return {"kind": kind, "identifier": identifier, "art": list_art(store, pid)[f"{kind}:{identifier}"]}


def set_behavior_carriers(store: Store, pid: str, behavior: str, carriers: list[str]) -> dict:
    """Change which mobs carry a capability (the infection, a freezing touch ...). Before generation it is a spec edit (the approval is reset like any edit);
    afterwards the spec is updated and the code follows: a coder task that has not started gets its brief rewritten with the new carriers, one that has
    gets a change request that wires or unwires only the carriers."""
    from .spec import behavior_id
    proj = store.project(pid); spec = read_spec(proj["spec"])
    b = next((x for x in spec.behaviors if behavior_id(x.title) == behavior), None)
    if b is None:
        raise InputError(f"Unknown behavior {behavior!r}; the project has {[behavior_id(x.title) for x in spec.behaviors]}")
    if b.kind != "capability":
        raise InputError(f"{b.title!r} is a mechanic, not a capability: only capabilities have carriers")
    mobs = {m.identifier for m in spec.mobs}
    new = list(dict.fromkeys(str(c) for c in carriers))
    if not new or [c for c in new if c not in mobs]:
        raise InputError(f"Carriers are one or more mobs of this project ({sorted(mobs)}), got {new}")
    if tuple(new) == tuple(b.affects):
        return {"behavior": behavior, "carriers": new, "changed": False, "task": None}
    added, removed = [c for c in new if c not in b.affects], [c for c in b.affects if c not in new]
    new_spec = replace(spec, behaviors=[replace(x, affects=tuple(new)) if x is b else x for x in spec.behaviors])
    if proj["status"] not in GENERATED_STATUSES:
        from .specedit import _save
        _save(store, pid, new_spec, f"carriers of {behavior}: +{added} -{removed}")
        return {"behavior": behavior, "carriers": new, "changed": True, "task": None, "spec_state": "DRAFT"}
    _save_spec(store, pid, new_spec, f"carriers of {behavior}: +{added} -{removed}")
    from .modmap import custom_cards, update_card, request_change, feature_instructions, plan_behaviors
    card = custom_cards(store, pid).get(behavior)
    if card is None:
        return {"behavior": behavior, "carriers": new, "changed": True, "task": (plan_behaviors(store, pid) or [None])[0]}   # never planned: plan it now with the new carriers
    update_card(store, pid, behavior, by="user", note=f"carriers: +{added} -{removed}", derived_from=new)
    task_id = f"{pid}:FEATURE:{behavior}"
    feature = next((t for t in store.tasks(pid) if t["id"] == task_id), None)
    if feature is not None and feature["state"] in ("BACKLOG", "READY"):
        card = custom_cards(store, pid)[behavior]
        with store.tx() as con:
            con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(feature_instructions(card, kind="capability", carriers=new))))
        return {"behavior": behavior, "carriers": new, "changed": True, "task": task_id, "how": "brief rewritten: the coder has not started it"}
    request = (f"The carriers of this capability changed. " + (f"Give it to: {', '.join(added)}: wire the existing component into their entity classes and add a GameTest per new carrier. " if added else "")
               + (f"Take it away from: {', '.join(removed)}: remove only their wiring and their GameTests. " if removed else "")
               + f"Do not duplicate the component; the carriers are now {', '.join(new)}.")
    out = request_change(store, pid, behavior, request)
    return {"behavior": behavior, "carriers": new, "changed": True, "task": out["task"], "how": "change request for the coder"}


def _save_spec(store: Store, pid: str, spec, reason: str) -> None:
    validate_spec_content(spec)
    with store.tx() as con:
        con.execute("UPDATE projects SET spec_json=? WHERE id=?", (json.dumps(spec.to_dict(), sort_keys=True), pid))
        store.event(con, pid, "user", "SPEC_CHANGED", {"reason": reason})


def add_feature(store: Store, pid: str, *, kind: str, label: str, identifier: str | None = None, shape: str = "", color: str = "", tool: str = "", mining_level: str = "", variants: list[str] | None = None) -> dict:
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
    feature = Feature(kind=kind, identifier=ident, label=label.strip() or ident, shape=shape, color=color, tool=tool if kind == "block" else "", mining_level=mining_level if kind == "block" else "", variants=tuple(variants or ()) if kind == "block" else ())
    new_spec = replace(spec, features=list(spec.features) + [feature])
    check_java_name_collisions(new_spec.features)
    if proj["status"] not in GENERATED_STATUSES:
        from .specedit import _save
        return _save(store, pid, new_spec, f"add {kind} {ident}") | {"identifier": ident, "generated": False}
    if feature.variants:
        raise InputError("Variants (stairs/slab/fence/wall) can be chosen for new blocks before generation; after generation ask for them as a change on the block's card")
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
        from .fabric import block_tags
        for tag, members in block_tags(new_spec).items():
            tf = res / "data/minecraft/tags/block" / f"{tag}.json"; tf.parent.mkdir(parents=True, exist_ok=True)
            tf.write_text(json.dumps({"replace": False, "values": members}, indent=2) + "\n", encoding="utf8"); written.append(str(tf.relative_to(ws)).replace("\\", "/"))
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
        props = "BlockBehaviour.Properties.of().strength(3.0F)" + ("" if (tool or "pickaxe") == "none" else ".requiresCorrectToolForDrops()")
        lines = [f'    public static final Block {const} = Registry.register(BuiltInRegistries.BLOCK, id("{ident}"), new Block({props}));',
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


def paint_mob_skin(store: Store, pid: str, mob: str, recipe: dict, *, install: bool = False) -> dict:
    """USER-ONLY, no agent: paint models/<mob>.png from a skin recipe (what the designer's orchestra_paint_skin takes: palette, zones, surface, face, scale, seed),
    and with `install` put it in the game as the mob's texture. This is how an already installed mob gets a new look for the price of nothing."""
    from . import skin
    from .models import MODEL_DIR
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", mob):
        raise InputError("mob must be the mob identifier (snake_case)")
    if not isinstance(recipe, dict) or "palette" not in recipe:
        raise InputError("the recipe is an object with at least a `palette` ({\"base\": \"#rrggbb\", ...}); it may also have zones, surface, face, scale and seed")
    models = Path(store.project(pid)["root"]) / MODEL_DIR
    source = models / f"{mob}.bbmodel"
    if not source.is_file():
        raise StateError(f"models/{mob}.bbmodel does not exist: the mob's MODEL task stages its model there")
    png, report = skin.paint_skin(json.loads(source.read_text(encoding="utf8")), palette=recipe["palette"], zones=recipe.get("zones") or [], face=recipe.get("face", {}),
                                  scale=int(recipe.get("scale", 2)), seed=str(recipe.get("seed") or mob)[:64], surface=recipe.get("surface"))
    (models / f"{mob}.png").write_bytes(png)
    out = {"file": f"{MODEL_DIR}/{mob}.png", "size": report["size"], "face_check": report["face_check"], "adjusted": report["adjusted"], "installed": False}
    if install:
        installed = set_texture(store, pid, kind="entity", identifier=mob, png_base64=_b64.b64encode(png).decode())
        out["installed"] = True; out["texture"] = installed
    return out


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


def set_sound_file(store: Store, pid: str, *, identifier: str, ogg_base64: str) -> dict:
    """Install the user's .ogg for a registered sound event (assets/<mod>/sounds/<id>.ogg)."""
    proj = store.project(pid)
    if proj["status"] not in GENERATED_STATUSES:
        raise StateError("Generate the project first")
    spec = read_spec(proj["spec"])
    if identifier not in {sd.identifier for sd in spec.sounds}:
        raise InputError(f"No sound event {identifier!r} in the spec (craftctl add-sound before generating)")
    try:
        raw = _b64.b64decode(ogg_base64, validate=True)
    except Exception:
        raise InputError("ogg_base64 is not valid base64")
    if not raw.startswith(b"OggS") or len(raw) > 5_000_000:
        raise InputError("Not an Ogg file (or larger than 5 MB). Minecraft needs Ogg Vorbis, mono for positional sounds.")
    ws = Path(proj["root"]); rel = f"src/main/resources/assets/{pid}/sounds/{identifier}.ogg"
    (ws / rel).parent.mkdir(parents=True, exist_ok=True); (ws / rel).write_bytes(raw)
    accepted = accept_changes(ws, run_id=f"sound:{identifier}", actor="user", changed=[rel])
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "user", "SOUND_UPLOADED", {"identifier": identifier, "file": rel, "bytes": len(raw)})
    return {"file": rel, "accepted": accepted["accepted"], "note": "Sound installed; rebuild to apply."}


def add_ore_any(store: Store, pid: str, **kw) -> dict:
    """Before generation: spec. After: worldgen JSON written by the controller + a coder task for the ModMain line."""
    from .specedit import add_ore
    from .spec import Ore
    from .gear import ore_worldgen_files, ore_registrations
    proj = store.project(pid)
    if proj["status"] not in GENERATED_STATUSES:
        return add_ore(store, pid, **kw) | {"generated": False}
    spec = read_spec(proj["spec"])
    ore = Ore(block=kw["block"], vein_size=int(kw.get("vein_size", 9)), veins_per_chunk=int(kw.get("veins_per_chunk", 8)), min_y=int(kw.get("min_y", -64)), max_y=int(kw.get("max_y", 64)),
              biomes=tuple(kw.get("biomes") or ("overworld",)), discard_on_air=float(kw.get("discard_on_air", 0.0)))
    if any(o.block == ore.block for o in spec.ores):
        raise InputError(f"{ore.block} already has worldgen; remove it first")
    new_spec = replace(spec, ores=list(spec.ores) + [ore]); validate_spec_content(new_spec)
    ws = Path(proj["root"]); written = []
    for rel, data in ore_worldgen_files(replace(new_spec, ores=[ore])).items():
        f = ws / "src/main/resources" / rel; f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf8"); written.append(str(f.relative_to(ws)).replace("\\", "/"))
    _save_spec(store, pid, new_spec, f"ore worldgen {ore.block} after generation")
    accepted = accept_changes(ws, run_id=f"ore:{ore.block}", actor="user", changed=written)
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid)
    imports, lines = ore_registrations(replace(new_spec, ores=[ore]))
    task_id = f"{pid}:ADD_ORE:{ore.block}"
    instructions = [f"Register the ore worldgen for `{ore.block}` in src/main/java/{spec.package.replace('.', '/')}/ModMain.java (the datapack JSON is already written):",
                    "1. Add these imports if missing:"] + ["   import " + i + ";" for i in imports] + ["2. In onInitialize(), add:"] + ["   " + l.strip() for l in lines] + [
                    "3. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    store.add_task(pid, task_id, "coder", f"Register ore worldgen for {ore.block}")
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(instructions)))
    _reopen_build(store, pid)
    store.add_event(pid, "controller", "FEATURE_ADDED", {"kind": "ore", "identifier": ore.block, "files": written, "task": task_id})
    return {"block": ore.block, "generated": True, "files": written, "accepted": accepted["accepted"], "task": task_id, "next": {"action": "dispatch", "payload": {"task": task_id}}}


def add_enchantment_any(store: Store, pid: str, **kw) -> dict:
    """Enchantments are datapack JSON: after generation the controller writes the file and lang entry directly (no coder)."""
    from .specedit import add_enchantment
    from .spec import Enchantment
    from .variants import enchantment_json
    proj = store.project(pid)
    if proj["status"] not in GENERATED_STATUSES:
        return add_enchantment(store, pid, **kw) | {"generated": False}
    spec = read_spec(proj["spec"])
    e = Enchantment(identifier=kw["identifier"], label=kw["label"], kind=kw.get("kind", "damage"), max_level=int(kw.get("max_level", 3)),
                    items=kw.get("items") or ("#minecraft:enchantable/armor" if kw.get("kind") == "protection" else "#minecraft:enchantable/weapon"), weight=int(kw.get("weight", 5)))
    new_spec = replace(spec, enchantments=[x for x in spec.enchantments if x.identifier != e.identifier] + [e]); validate_spec_content(new_spec)
    ws = Path(proj["root"]); res = ws / "src/main/resources"
    f = res / "data" / pid / "enchantment" / f"{e.identifier}.json"; f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(enchantment_json(new_spec, e), indent=2) + "\n", encoding="utf8")
    lang_file = res / "assets" / pid / "lang/en_us.json"
    lang = json.loads(lang_file.read_text(encoding="utf8")) if lang_file.is_file() else {}
    lang[f"enchantment.{pid}.{e.identifier}"] = e.label
    lang_file.write_text(json.dumps(lang, indent=2, sort_keys=True) + "\n", encoding="utf8")
    written = [str(f.relative_to(ws)).replace("\\", "/"), f"src/main/resources/assets/{pid}/lang/en_us.json"]
    _save_spec(store, pid, new_spec, f"enchantment {e.identifier} after generation")
    accepted = accept_changes(ws, run_id=f"enchant:{e.identifier}", actor="user", changed=written)
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "user", "FEATURE_ADDED", {"kind": "enchantment", "identifier": e.identifier, "files": written})
    return {"identifier": e.identifier, "generated": True, "files": written, "accepted": accepted["accepted"], "note": "Enchantment JSON written; rebuild to apply."}
