"""Block variants (stairs, slab, fence, wall) and data-driven enchantments — deterministic generator output.

Variants reuse vanilla template models (`minecraft:block/stairs`, `slab`, `fence_post`, `template_wall_*`) textured with
the base block's texture, standard blockstates (stairs: all shapes/facings/halves; fence & wall: multipart), loot tables
(slab drops 2 when double), recipes with the vanilla patterns, connectivity tags (`minecraft:fences`, `minecraft:walls`)
and tool tags like the base block. Enchantments are 1.21 JSON under data/<mod>/enchantment/.
"""
from __future__ import annotations
from .spec import Spec, Feature, Recipe, Enchantment

VARIANT_CLASS = {"stairs": "StairBlock", "slab": "SlabBlock", "fence": "FenceBlock", "wall": "WallBlock"}
VARIANT_LABEL = {"stairs": "Stairs", "slab": "Slab", "fence": "Fence", "wall": "Wall"}
VARIANT_RECIPE = {"stairs": (["X  ", "XX ", "XXX"], {"X": None}, 4), "slab": (["XXX"], {"X": None}, 6),
                  "fence": (["XSX", "XSX"], {"X": None, "S": "minecraft:stick"}, 3), "wall": (["XXX", "XXX"], {"X": None}, 6)}

FACINGS = ("north", "east", "south", "west")


def variant_ids(spec: Spec) -> list[tuple[Feature, str, str]]:
    return [(f, v, f"{f.identifier}_{v}") for f in spec.features if f.kind == "block" for v in f.variants]


def variant_java(spec: Spec) -> tuple[list[str], list[str], list[str]]:
    """(imports, ModMain fields, onInitialize creative-tab lines)."""
    ids = variant_ids(spec)
    if not ids:
        return [], [], []
    imports = [f"net.minecraft.world.level.block.{c}" for c in sorted({VARIANT_CLASS[v] for _, v, _ in ids})]
    fields, init = [], []
    for f, v, vid in ids:
        base = f.identifier.upper(); const = vid.upper(); klass = VARIANT_CLASS[v]
        props = f"BlockBehaviour.Properties.ofFullCopy({base})"
        ctor = f"new StairBlock({base}.defaultBlockState(), {props})" if v == "stairs" else f"new {klass}({props})"
        fields.append(f'    public static final Block {const} = Registry.register(BuiltInRegistries.BLOCK, id("{vid}"), {ctor});')
        fields.append(f'    public static final Item {const}_ITEM = Registry.register(BuiltInRegistries.ITEM, id("{vid}"), new BlockItem({const}, new Item.Properties()));')
        init.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept({const}_ITEM));")
    return imports, fields, init


def _stairs_blockstate(mod: str, vid: str) -> dict:
    variants = {}
    base = f"{mod}:block/{vid}"
    rot = {"east": 0, "south": 90, "west": 180, "north": 270}
    for facing in FACINGS:
        for half in ("bottom", "top"):
            for shape in ("straight", "inner_left", "inner_right", "outer_left", "outer_right"):
                model = base if shape == "straight" else f"{base}_inner" if shape.startswith("inner") else f"{base}_outer"
                y = rot[facing]
                if shape in ("inner_left", "outer_left"): y = (y - 90) % 360
                if half == "top" and shape in ("inner_left", "inner_right", "outer_left", "outer_right"): y = (y + 90) % 360
                entry = {"model": model}
                if y: entry["y"] = y
                if half == "top": entry["x"] = 180
                if y or half == "top": entry["uvlock"] = True
                variants[f"facing={facing},half={half},shape={shape}"] = entry
    return {"variants": variants}


def variant_resources(spec: Spec) -> dict[str, object]:
    """Relative resource paths (under src/main/resources) -> JSON objects."""
    mod = spec.mod_id; out: dict[str, object] = {}
    for f, v, vid in variant_ids(spec):
        tex = f"{mod}:block/{f.identifier}"
        a = f"assets/{mod}"
        if v == "stairs":
            out[f"{a}/models/block/{vid}.json"] = {"parent": "minecraft:block/stairs", "textures": {"bottom": tex, "top": tex, "side": tex}}
            out[f"{a}/models/block/{vid}_inner.json"] = {"parent": "minecraft:block/inner_stairs", "textures": {"bottom": tex, "top": tex, "side": tex}}
            out[f"{a}/models/block/{vid}_outer.json"] = {"parent": "minecraft:block/outer_stairs", "textures": {"bottom": tex, "top": tex, "side": tex}}
            out[f"{a}/blockstates/{vid}.json"] = _stairs_blockstate(mod, vid)
            out[f"{a}/models/item/{vid}.json"] = {"parent": f"{mod}:block/{vid}"}
            out[f"data/{mod}/loot_table/blocks/{vid}.json"] = {"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": f"{mod}:{vid}"}], "conditions": [{"condition": "minecraft:survives_explosion"}]}]}
        elif v == "slab":
            out[f"{a}/models/block/{vid}.json"] = {"parent": "minecraft:block/slab", "textures": {"bottom": tex, "top": tex, "side": tex}}
            out[f"{a}/models/block/{vid}_top.json"] = {"parent": "minecraft:block/slab_top", "textures": {"bottom": tex, "top": tex, "side": tex}}
            out[f"{a}/blockstates/{vid}.json"] = {"variants": {"type=bottom": {"model": f"{mod}:block/{vid}"}, "type=top": {"model": f"{mod}:block/{vid}_top"}, "type=double": {"model": f"{mod}:block/{f.identifier}"}}}
            out[f"{a}/models/item/{vid}.json"] = {"parent": f"{mod}:block/{vid}"}
            out[f"data/{mod}/loot_table/blocks/{vid}.json"] = {"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": f"{mod}:{vid}",
                "functions": [{"function": "minecraft:set_count", "count": 2, "conditions": [{"condition": "minecraft:block_state_property", "block": f"{mod}:{vid}", "properties": {"type": "double"}}]},
                              {"function": "minecraft:explosion_decay"}]}]}]}
        elif v == "fence":
            out[f"{a}/models/block/{vid}_post.json"] = {"parent": "minecraft:block/fence_post", "textures": {"texture": tex}}
            out[f"{a}/models/block/{vid}_side.json"] = {"parent": "minecraft:block/fence_side", "textures": {"texture": tex}}
            out[f"{a}/models/block/{vid}_inventory.json"] = {"parent": "minecraft:block/fence_inventory", "textures": {"texture": tex}}
            out[f"{a}/blockstates/{vid}.json"] = {"multipart": [{"apply": {"model": f"{mod}:block/{vid}_post"}}] + [
                {"when": {d: "true"}, "apply": {"model": f"{mod}:block/{vid}_side", "y": y, "uvlock": True} if y else {"model": f"{mod}:block/{vid}_side", "uvlock": True}}
                for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270))]}
            out[f"{a}/models/item/{vid}.json"] = {"parent": f"{mod}:block/{vid}_inventory"}
            out[f"data/{mod}/loot_table/blocks/{vid}.json"] = {"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": f"{mod}:{vid}"}], "conditions": [{"condition": "minecraft:survives_explosion"}]}]}
        elif v == "wall":
            out[f"{a}/models/block/{vid}_post.json"] = {"parent": "minecraft:block/template_wall_post", "textures": {"wall": tex}}
            out[f"{a}/models/block/{vid}_side.json"] = {"parent": "minecraft:block/template_wall_side", "textures": {"wall": tex}}
            out[f"{a}/models/block/{vid}_side_tall.json"] = {"parent": "minecraft:block/template_wall_side_tall", "textures": {"wall": tex}}
            out[f"{a}/models/block/{vid}_inventory.json"] = {"parent": "minecraft:block/wall_inventory", "textures": {"wall": tex}}
            parts = [{"when": {"up": "true"}, "apply": {"model": f"{mod}:block/{vid}_post"}}]
            for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
                for height, suffix in (("low", "_side"), ("tall", "_side_tall")):
                    apply = {"model": f"{mod}:block/{vid}{suffix}", "uvlock": True}
                    if y: apply["y"] = y
                    parts.append({"when": {d: height}, "apply": apply})
            out[f"{a}/blockstates/{vid}.json"] = {"multipart": parts}
            out[f"{a}/models/item/{vid}.json"] = {"parent": f"{mod}:block/{vid}_inventory"}
            out[f"data/{mod}/loot_table/blocks/{vid}.json"] = {"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": f"{mod}:{vid}"}], "conditions": [{"condition": "minecraft:survives_explosion"}]}]}
    # connectivity tags
    fences = [f"{mod}:{vid}" for _, v, vid in variant_ids(spec) if v == "fence"]
    walls = [f"{mod}:{vid}" for _, v, vid in variant_ids(spec) if v == "wall"]
    if fences:
        out["data/minecraft/tags/block/fences.json"] = {"replace": False, "values": fences}
        out["data/minecraft/tags/item/fences.json"] = {"replace": False, "values": fences}
    if walls:
        out["data/minecraft/tags/block/walls.json"] = {"replace": False, "values": walls}
        out["data/minecraft/tags/item/walls.json"] = {"replace": False, "values": walls}
    return out


def variant_recipes(spec: Spec) -> list[Recipe]:
    out = []
    for f, v, vid in variant_ids(spec):
        pattern, key, count = VARIANT_RECIPE[v]
        out.append(Recipe(id=vid, kind="shaped", result=vid, count=count, pattern=tuple(pattern), key={k: (f.identifier if val is None else val) for k, val in key.items()}))
    return out


def variant_lang(spec: Spec) -> dict[str, str]:
    return {f"block.{spec.mod_id}.{vid}": f"{f.label} {VARIANT_LABEL[v]}" for f, v, vid in variant_ids(spec)}


def variant_tag_members(spec: Spec) -> dict[str, list[str]]:
    """Tool tags: variants mine like their base block."""
    tags: dict[str, list[str]] = {}
    for f, v, vid in variant_ids(spec):
        tool = f.tool or "pickaxe"
        if tool == "none":
            continue
        tags.setdefault(f"mineable/{tool}", []).append(f"{spec.mod_id}:{vid}")
        level = f.mining_level or "wood"
        if level in ("stone", "iron", "diamond"):
            tags.setdefault(f"needs_{level}_tool", []).append(f"{spec.mod_id}:{vid}")
        elif level == "netherite":
            tags.setdefault("needs_diamond_tool", []).append(f"{spec.mod_id}:{vid}")
    return tags


def enchantment_json(spec: Spec, e: Enchantment) -> dict:
    base = {"description": {"translate": f"enchantment.{spec.mod_id}.{e.identifier}"}, "supported_items": e.items, "weight": e.weight, "max_level": e.max_level,
            "min_cost": {"base": 5, "per_level_above_first": 8}, "max_cost": {"base": 25, "per_level_above_first": 8}, "anvil_cost": 2}
    if e.kind == "damage":
        base["slots"] = ["mainhand"]
        base["effects"] = {"minecraft:damage": [{"effect": {"type": "minecraft:add", "value": {"type": "minecraft:linear", "base": 1.0, "per_level_above_first": 0.5}}}]}
    elif e.kind == "protection":
        base["slots"] = ["armor"]
        base["effects"] = {"minecraft:damage_protection": [{"effect": {"type": "minecraft:add", "value": {"type": "minecraft:linear", "base": 1.0, "per_level_above_first": 1.0}}}]}
    elif e.kind == "fire_aspect":
        base["slots"] = ["mainhand"]
        base["effects"] = {"minecraft:post_attack": [{"enchanted": "attacker", "affected": "victim", "effect": {"type": "minecraft:ignite", "duration": {"type": "minecraft:linear", "base": 4.0, "per_level_above_first": 4.0}}}]}
    return base
