"""Conservative deterministic intake; unsupported ideas remain questions, not fake output."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
import hashlib
import re
from .validation import normalize_id, project_id, validate_package, InputError

DEFAULT_EGG_COLORS = (0x8A6DD1, 0xE6D8FF)


def default_egg_colors(identifier: str, behavior: str = "passive") -> tuple[int, int]:
    """Deterministic spawn-egg tint per mob so two eggs in one tab never look alike: hostile mobs get a dark
    base with a saturated spot colour, passive ones a bright base with a pale spot colour."""
    digest = hashlib.sha256(identifier.encode()).digest()
    r, g, b = digest[0], digest[1], digest[2]
    if behavior == "hostile":
        base = (r // 4, g // 4, b // 4)
        spot = (128 + r // 2, 64 + g // 4, 64 + b // 4)
    else:
        base = (96 + r // 2, 96 + g // 2, 96 + b // 2)
        spot = (200 + r // 5, 200 + g // 5, 200 + b // 5)
    pack = lambda c: (c[0] << 16) | (c[1] << 8) | c[2]
    return pack(base), pack(spot)

@dataclass(frozen=True)
class Art:
    """Art direction for one entity (item, block, tool/armor set, food, mob): what it looks like and why, as concrete visual cues the designer
    paints from. Written by the interpreter from the idea and the theme, editable in the UI; a deterministic derivation fills the gaps (art.py)."""
    concept: str = ""            # one or two sentences: what it is and how it looks
    tags: tuple = ()             # concrete cues: shapes, materials, colours, wear ("serrated edge", "bone teeth", "rust red"), not "cool" or "epic"
    silhouette: str = ""         # optional: the shape in a phrase ("cleaver", "crescent blade", "spiked club")
    pieces: dict = field(default_factory=dict)   # material sets only: tool/armor kind -> its own concept ({"sword": "...", "helmet": "..."})


ART_TEXT = re.compile(r"^[^\x00-\x1f<>{}\[\]\\]+$")


def coerce_art(value) -> "Art | None":
    """None, "", {} -> None; a string is a concept; a dict is read field by field; an Art passes through."""
    if value is None or value == "" or value == {} or value == []:
        return None
    if isinstance(value, Art):
        return value
    if isinstance(value, str):
        return Art(concept=value.strip())
    if not isinstance(value, dict):
        raise InputError(f"Bad art: {value!r}")
    tags = value.get("tags") or ()
    if isinstance(tags, str):
        tags = [t for t in re.split(r"[,;\n]", tags)]
    pieces = value.get("pieces") or {}
    if not isinstance(pieces, dict):
        raise InputError("art.pieces must map a tool/armor kind to a sentence")
    return Art(concept=str(value.get("concept") or "").strip(), tags=tuple(str(t).strip() for t in tags if str(t).strip()),
               silhouette=str(value.get("silhouette") or "").strip(), pieces={str(k): str(v).strip() for k, v in pieces.items() if str(v).strip()})


def validate_art(art: "Art | None", label: str, piece_kinds: tuple = ()) -> None:
    if art is None:
        return
    if len(art.concept) > 320 or (art.concept and not ART_TEXT.match(art.concept)):
        raise InputError(f"{label}: art.concept must be plain text up to 320 characters")
    if len(art.tags) > 16 or any(not (2 <= len(t) <= 48) or not ART_TEXT.match(t) for t in art.tags):
        raise InputError(f"{label}: art.tags are at most 16 phrases of 2-48 characters")
    if len(art.silhouette) > 60 or (art.silhouette and not ART_TEXT.match(art.silhouette)):
        raise InputError(f"{label}: art.silhouette is a short phrase (up to 60 characters)")
    for kind, text in art.pieces.items():
        if kind not in piece_kinds:
            raise InputError(f"{label}: art.pieces has {kind!r}, which is not one of this set's pieces {list(piece_kinds)}")
        if len(text) > 320 or not ART_TEXT.match(text):
            raise InputError(f"{label}: art.pieces.{kind} must be plain text up to 320 characters")


@dataclass(frozen=True)
class Feature:
    kind: str
    identifier: str
    label: str
    shape: str = ""        # placeholder texture silhouette: gem | ingot | food | block (default by kind)
    color: str = ""        # optional hex (#RRGGBB) tint for the placeholder texture
    tool: str = ""         # blocks: pickaxe | axe | shovel | hoe | none (default pickaxe); "none" = breaks by hand
    mining_level: str = "" # blocks: wood | stone | iron | diamond | netherite (default wood = any pickaxe)
    variants: tuple = ()   # blocks: subset of stairs | slab | fence | wall — generated as <id>_stairs etc. with recipes
    art: object = None     # Art direction (concept, tags, silhouette) the sprite designer paints from

@dataclass(frozen=True)
class Recipe:
    """One vanilla recipe. Ingredients/results are local ids (a feature of this mod), namespaced ids
    (minecraft:stick) or tags (#minecraft:planks)."""
    id: str                       # recipe file name, e.g. ruby_block
    kind: str                     # shaped | shapeless | smelting | blasting | campfire_cooking | smoking
    result: str
    count: int = 1
    pattern: tuple[str, ...] = ()           # shaped: 1-3 rows of 1-3 chars; " " = empty
    key: dict = field(default_factory=dict)  # shaped: symbol -> ingredient
    ingredients: tuple[str, ...] = ()       # shapeless (1-9) / cooking (exactly 1)
    experience: float = 0.0                 # cooking
    cooking_time: int = 200                 # cooking, ticks
    group: str = ""


@dataclass(frozen=True)
class Drop:
    """Block loot beyond drop-self: ore -> item, with the vanilla ore conventions."""
    block: str
    item: str
    count_min: int = 1
    count_max: int = 1
    fortune: bool = False
    silk_touch: bool = False


@dataclass(frozen=True)
class MobDrop:
    """One entry of a mob's death loot: item id, count range and drop chance (0-1)."""
    item: str
    count_min: int = 1
    count_max: int = 1
    chance: float = 1.0


def coerce_mob_drop(value) -> MobDrop:
    if isinstance(value, MobDrop):
        return value
    if isinstance(value, str):
        return MobDrop(item=value)
    if isinstance(value, dict):
        return MobDrop(item=str(value.get("item", "")), count_min=int(value.get("count_min", 1)), count_max=int(value.get("count_max", 1)),
                       chance=float(value.get("chance", 1.0)))
    raise InputError(f"Bad mob drop: {value!r}")


@dataclass(frozen=True)
class Spawn:
    """Natural spawning: where (biome tags like #minecraft:is_forest, biome ids, or 'overworld'), how often, group size."""
    biomes: tuple = ("overworld",)
    weight: int = 10            # relative to other mobs in the biome (zombie 95, cow 8)
    min_group: int = 1
    max_group: int = 3


@dataclass(frozen=True)
class Mob:
    """v1 criterion 6 'simple mob': GeckoLib-rendered entity with idle + walk, basic AI, spawn egg, loot."""
    identifier: str
    label: str
    behavior: str = "passive"          # passive | neutral (retaliates when hurt) | hostile
    health: float = 10.0
    speed: float = 0.25
    width: float = 0.8
    height: float = 0.9
    attack_damage: float = 3.0         # hostile only
    drops: tuple = ()                  # MobDrop entries (strings and dicts are coerced on read)
    spawn: object = None               # Spawn or None (egg-only)
    egg_colors: tuple[int, int] = DEFAULT_EGG_COLORS
    body_plan: str = "quadruped"      # base rig the model starts from: quadruped | biped | bird | fish | serpent | insect
    art: object = None                # Art direction: concept, tags and silhouette; feeds the skin's palette, zones and face
    held_item: str = ""               # what the mob carries in its main hand and draws on the model's `held_item` bone: "" = the best tool/weapon in
                                      # its drops (biped plan only), "none" = empty-handed, or an item id (local or minecraft:...)


TOOL_KINDS = ("sword", "pickaxe", "axe", "shovel", "hoe")
ARMOR_KINDS = ("helmet", "chestplate", "leggings", "boots")
MINING_LEVELS = ("wood", "stone", "iron", "diamond", "netherite")


@dataclass(frozen=True)
class Material:
    """A tier (like iron or diamond) and the tool/armor set made from it."""
    identifier: str
    label: str
    ingredient: str                       # local item id or minecraft:id — repair + recipes
    tools: tuple = ()                     # subset of TOOL_KINDS
    armor: tuple = ()                     # subset of ARMOR_KINDS
    durability: int = 500                 # tool uses (iron 250, diamond 1561)
    mining_speed: float = 6.0             # iron 6, diamond 8
    attack_damage_bonus: float = 2.0      # iron 2, diamond 3
    mining_level: str = "iron"            # which blocks drop: wood|stone|iron|diamond|netherite
    enchantability: int = 14              # iron 14, diamond 10, gold 22
    armor_defense: tuple = (2, 6, 5, 2)   # helmet, chestplate, leggings, boots (iron 2/6/5/2, diamond 3/8/6/3)
    armor_durability: int = 15            # multiplier (iron 15, diamond 33)
    toughness: float = 0.0                # diamond 2, netherite 3
    knockback_resistance: float = 0.0     # netherite 0.1
    recipes: bool = True                  # standard crafting patterns
    color: str = ""                       # optional hex tint for tool/armor textures (default: stable hue from identifier)
    accent: str = ""                      # optional hex highlight
    armor_style: str = "textured"         # textured (vanilla layers) | 3d (GeckoLib armor model designed in Blockbench)
    art: object = None                    # Art direction of the whole set; art.pieces gives a piece its own concept

    def item_ids(self) -> list[str]:
        return [f"{self.identifier}_{k}" for k in self.tools] + [f"{self.identifier}_{k}" for k in self.armor]


@dataclass(frozen=True)
class Food:
    identifier: str
    label: str
    nutrition: int = 4                    # half-drumsticks ×2 (apple 4, steak 8)
    saturation: float = 0.3               # saturation modifier (apple 0.3, steak 0.8)
    effects: tuple = ()                   # ({"effect": "minecraft:regeneration", "duration": 100, "amplifier": 0, "chance": 1.0}, ...)
    always_edible: bool = False
    fast: bool = False
    color: str = ""
    art: object = None


BLOCK_VARIANTS = ("stairs", "slab", "fence", "wall")
ENCHANT_KINDS = {"damage": "minecraft:damage", "protection": "minecraft:damage_protection", "efficiency": "minecraft:attributes", "fire_aspect": "minecraft:post_attack"}


@dataclass(frozen=True)
class Enchantment:
    """Data-driven enchantment (1.21 JSON). kind picks the vanilla effect component and sensible numbers."""
    identifier: str
    label: str
    kind: str = "damage"          # damage | protection | fire_aspect
    max_level: int = 3
    items: str = "#minecraft:enchantable/weapon"   # tag of items it can go on
    weight: int = 5
    treasure: bool = False


@dataclass(frozen=True)
class Structure:
    """A small structure from text layers (bottom layer first; rows run north→south, characters west→east).
    legend maps a character to a block: local id, minecraft:id, optionally with [props]. '.' or ' ' = air."""
    identifier: str
    label: str
    layers: tuple = ()            # tuple of tuples of strings, e.g. (("SSS","S S","SSS"), ("S.S","...","S.S"))
    legend: dict = field(default_factory=dict)
    spacing: int = 32             # chunks between attempts (vanilla village 34)
    separation: int = 8           # minimum chunks apart (village 8)
    biomes: tuple = ("overworld",)
    step: str = "surface_structures"   # generation step; underground_structures for buried ones
    salt: int = 0                 # 0 = derived from identifier


@dataclass(frozen=True)
class Biome:
    identifier: str
    label: str
    temperature: float = 0.8
    downfall: float = 0.4
    sky_color: str = "#78A7FF"
    fog_color: str = "#C0D8FF"
    water_color: str = "#3F76E4"
    grass_color: str = ""         # optional override
    foliage_color: str = ""
    base: str = "plains"          # vanilla biome whose features/carvers to copy: plains | forest | desert | taiga | snowy_plains | swamp
    mobs: tuple = ()              # local mob ids that spawn here (weight 10, group 1-3)
    precipitation: bool = True


@dataclass(frozen=True)
class Dimension:
    identifier: str
    label: str
    biomes: tuple = ()            # local biome ids (first is the default); empty = minecraft:plains
    key_item: str = ""            # local item id that teleports on right-click (created if missing: <id>_key)
    sky: str = "overworld"        # overworld (day/night) | nether (no sky) | end
    fixed_time: int = -1          # -1 = normal cycle, else 0-24000
    noise: str = "minecraft:overworld"   # noise settings: minecraft:overworld | minecraft:floating_islands | minecraft:caves | minecraft:amplified


@dataclass(frozen=True)
class Ore:
    """World generation for an ore block: veins of `vein_size` blocks, `veins_per_chunk` times per chunk,
    between min_y and max_y (trapezoid: most common in the middle), in the given biomes (same syntax as Spawn)."""
    block: str
    vein_size: int = 9
    veins_per_chunk: int = 8
    min_y: int = -64
    max_y: int = 64
    biomes: tuple = ("overworld",)
    discard_on_air: float = 0.0   # 0-1: chance to skip ore exposed to air (diamond uses 0.7 for buried-only)


@dataclass(frozen=True)
class Sound:
    """A SoundEvent `<mod>:<identifier>` backed by assets/<mod>/sounds/<identifier>.ogg (the user uploads the .ogg)."""
    identifier: str
    label: str                 # subtitle shown with "show subtitles"
    category: str = "neutral"  # master|music|record|weather|block|hostile|neutral|player|ambient|voice


@dataclass(frozen=True)
class Spec:
    schema_version: int
    name: str
    mod_id: str
    package: str
    idea: str
    profile: str
    features: list[Feature]
    questions: list[str]
    assumptions: list[str]
    recipes: list[Recipe] = field(default_factory=list)
    drops: list[Drop] = field(default_factory=list)
    tab: str | None = None        # creative tab label; id is derived (<mod_id>_tab)
    tab_icon: str | None = None   # local item id shown as the tab icon
    mobs: list[Mob] = field(default_factory=list)
    materials: list[Material] = field(default_factory=list)
    foods: list[Food] = field(default_factory=list)
    theme: str = ""               # visual brief every designer task receives: era, palette, motifs, mood
    sounds: list[Sound] = field(default_factory=list)
    ores: list[Ore] = field(default_factory=list)
    enchantments: list[Enchantment] = field(default_factory=list)
    structures: list[Structure] = field(default_factory=list)
    biomes: list[Biome] = field(default_factory=list)
    dimensions: list[Dimension] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def local_ids(self) -> set[str]:
        ids = {f.identifier for f in self.features}
        for f in self.features:
            ids.update(f"{f.identifier}_{v}" for v in f.variants)
        ids.update((d.key_item or f"{d.identifier}_key") for d in self.dimensions)
        for m in self.materials:
            ids.update(m.item_ids())
        ids.update(f.identifier for f in self.foods)
        return ids


SCHEMA_VERSION = 2
RECIPE_KINDS = ("shaped", "shapeless", "smelting", "blasting", "smoking", "campfire_cooking")
INGREDIENT_RE = re.compile(r"^#?[a-z0-9_.-]+:[a-z0-9_./-]+$")


def resolve_ingredient(spec_ids: set[str], mod_id: str, value: str) -> dict:
    """Return the vanilla JSON ingredient object for a local id, a namespaced id or a tag."""
    v = value.strip()
    if v.startswith("#"):
        if not INGREDIENT_RE.match(v):
            raise InputError(f"Bad tag ingredient: {value!r} (expected #namespace:path)")
        return {"tag": v[1:]}
    if ":" in v:
        if not INGREDIENT_RE.match(v):
            raise InputError(f"Bad namespaced ingredient: {value!r}")
        return {"item": v}
    if v not in spec_ids:
        raise InputError(f"Unknown local ingredient {value!r}; it must be an item or block of this mod, or namespaced like minecraft:stick")
    return {"item": f"{mod_id}:{v}"}


def resolve_result(spec_ids: set[str], mod_id: str, value: str) -> str:
    v = value.strip()
    if ":" in v:
        if v.startswith("#") or not INGREDIENT_RE.match(v):
            raise InputError(f"Bad result id: {value!r}")
        return v
    if v not in spec_ids:
        raise InputError(f"Unknown result {value!r}; recipes can only produce items/blocks of this mod or namespaced ids")
    return f"{mod_id}:{v}"


def validate_recipe(spec_ids: set[str], mod_id: str, r: Recipe) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", r.id):
        raise InputError(f"Recipe id must be snake_case (2-50 chars): {r.id!r}")
    if r.kind not in RECIPE_KINDS:
        raise InputError(f"Recipe kind must be one of {RECIPE_KINDS}: {r.kind!r}")
    if not (1 <= r.count <= 64):
        raise InputError("Recipe result count must be 1-64")
    resolve_result(spec_ids, mod_id, r.result)
    if r.kind == "shaped":
        if not (1 <= len(r.pattern) <= 3) or any(not (1 <= len(row) <= 3) for row in r.pattern):
            raise InputError("Shaped pattern needs 1-3 rows of 1-3 characters")
        if len({len(row) for row in r.pattern}) != 1:
            raise InputError("Shaped pattern rows must all have the same width")
        used = {c for row in r.pattern for c in row if c != " "}
        if not used:
            raise InputError("Shaped pattern is empty")
        missing = used - set(r.key)
        if missing:
            raise InputError(f"Shaped pattern uses symbols without a key: {sorted(missing)}")
        for sym, ing in r.key.items():
            if len(sym) != 1 or sym == " ":
                raise InputError(f"Shaped key symbols must be single non-space characters: {sym!r}")
            resolve_ingredient(spec_ids, mod_id, ing)
    elif r.kind == "shapeless":
        if not (1 <= len(r.ingredients) <= 9):
            raise InputError("Shapeless recipes take 1-9 ingredients")
        for ing in r.ingredients:
            resolve_ingredient(spec_ids, mod_id, ing)
    else:
        if len(r.ingredients) != 1:
            raise InputError(f"{r.kind} recipes take exactly one ingredient")
        resolve_ingredient(spec_ids, mod_id, r.ingredients[0])
        if not (0 <= r.experience <= 100) or not (1 <= r.cooking_time <= 72000):
            raise InputError("Cooking experience must be 0-100 and cooking_time 1-72000 ticks")


def validate_drop(spec: "Spec", d: Drop) -> None:
    blocks = {f.identifier for f in spec.features if f.kind == "block"}
    if d.block not in blocks:
        raise InputError(f"Drop block {d.block!r} is not a block of this mod")
    resolve_result(spec.local_ids(), spec.mod_id, d.item)
    if not (0 <= d.count_min <= d.count_max <= 64):
        raise InputError("Drop counts must satisfy 0 <= min <= max <= 64")


MOB_BEHAVIORS = ("passive", "neutral", "hostile")
TOOLS_FOR_BLOCKS = ("pickaxe", "axe", "shovel", "hoe", "none")
BIOME_RE = re.compile(r"^(#?[a-z0-9_.-]+:[a-z0-9_./-]+|overworld|nether|end)$")


def coerce_spawn(value):
    if value is None or isinstance(value, Spawn):
        return value
    if isinstance(value, dict):
        return Spawn(biomes=tuple(str(b) for b in value.get("biomes", ("overworld",))), weight=int(value.get("weight", 10)),
                     min_group=int(value.get("min_group", 1)), max_group=int(value.get("max_group", 3)))
    raise InputError(f"Bad spawn: {value!r}")


def validate_mob(spec: "Spec", m: Mob) -> None:
    validate_art(m.art, f"mob {m.identifier}")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", m.identifier):
        raise InputError(f"Mob identifier must be snake_case (2-50 chars): {m.identifier!r}")
    if m.identifier in spec.local_ids() or f"{m.identifier}_spawn_egg" in spec.local_ids():
        raise InputError(f"Mob identifier {m.identifier!r} collides with an item/block (its spawn egg is <id>_spawn_egg)")
    if m.behavior not in MOB_BEHAVIORS:
        raise InputError(f"Mob behavior must be one of {MOB_BEHAVIORS}")
    from .rigs import BODY_PLANS
    if m.body_plan not in BODY_PLANS:
        raise InputError(f"Mob body_plan must be one of {BODY_PLANS}")
    if m.held_item not in ("", "none"):
        resolve_result(spec.local_ids(), spec.mod_id, m.held_item)   # same rule as a drop: an item of this mod or a namespaced id
    if not (1 <= m.health <= 1024) or not (0.05 <= m.speed <= 1.5) or not (0.1 <= m.width <= 4) or not (0.1 <= m.height <= 4):
        raise InputError("Mob health 1-1024, speed 0.05-1.5, width/height 0.1-4")
    if not (0 <= m.attack_damage <= 100):
        raise InputError("Mob attack_damage 0-100")
    for d in m.drops:
        d = coerce_mob_drop(d)
        resolve_result(spec.local_ids(), spec.mod_id, d.item)
        if not (0 <= d.count_min <= d.count_max <= 64):
            raise InputError(f"Mob drop {d.item}: counts must satisfy 0 <= min <= max <= 64")
        if not (0 < d.chance <= 1):
            raise InputError(f"Mob drop {d.item}: chance must be in (0, 1]")
    if len(m.egg_colors) != 2 or any(not (0 <= c <= 0xFFFFFF) for c in m.egg_colors):
        raise InputError("egg_colors must be two 24-bit RGB ints")
    sp = coerce_spawn(m.spawn)
    if sp is not None:
        if not sp.biomes or any(not BIOME_RE.match(b) for b in sp.biomes):
            raise InputError("spawn.biomes: use biome ids (minecraft:plains), biome tags (#minecraft:is_forest) or overworld|nether|end")
        if not (1 <= sp.weight <= 1000) or not (1 <= sp.min_group <= sp.max_group <= 16):
            raise InputError("spawn: weight 1-1000, 1 <= min_group <= max_group <= 16")


EFFECT_RE = re.compile(r"^minecraft:[a-z_]+$")


def validate_material(spec: "Spec", m: Material) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", m.identifier):
        raise InputError(f"Material identifier must be snake_case (2-41 chars): {m.identifier!r}")
    for k in m.tools:
        if k not in TOOL_KINDS: raise InputError(f"Unknown tool kind {k!r}; allowed: {TOOL_KINDS}")
    for k in m.armor:
        if k not in ARMOR_KINDS: raise InputError(f"Unknown armor kind {k!r}; allowed: {ARMOR_KINDS}")
    if not m.tools and not m.armor:
        raise InputError("A material needs at least one tool or armor piece")
    if m.mining_level not in MINING_LEVELS:
        raise InputError(f"mining_level must be one of {MINING_LEVELS}")
    if m.armor_style not in ("textured", "3d"):
        raise InputError("armor_style must be textured or 3d")
    if not (1 <= m.durability <= 10000) or not (0.5 <= m.mining_speed <= 50) or not (0 <= m.attack_damage_bonus <= 50) or not (0 <= m.enchantability <= 50):
        raise InputError("Material numbers out of range (durability 1-10000, mining_speed 0.5-50, attack bonus 0-50, enchantability 0-50)")
    if len(m.armor_defense) != 4 or any(not (0 <= int(d) <= 20) for d in m.armor_defense) or not (1 <= m.armor_durability <= 100):
        raise InputError("armor_defense needs four values 0-20 (helmet, chestplate, leggings, boots); armor_durability 1-100")
    resolve_ingredient(spec.local_ids(), spec.mod_id, m.ingredient)


def validate_food(spec: "Spec", f: Food) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", f.identifier):
        raise InputError(f"Food identifier must be snake_case: {f.identifier!r}")
    if not (0 <= f.nutrition <= 20) or not (0 <= f.saturation <= 2):
        raise InputError("nutrition 0-20, saturation 0-2")
    for e in f.effects:
        if not isinstance(e, dict) or not EFFECT_RE.match(str(e.get("effect", ""))):
            raise InputError(f"Food effect needs a vanilla id like minecraft:regeneration: {e!r}")
        if not (1 <= int(e.get("duration", 100)) <= 72000) or not (0 <= int(e.get("amplifier", 0)) <= 9) or not (0 < float(e.get("chance", 1.0)) <= 1):
            raise InputError("Food effect: duration 1-72000 ticks, amplifier 0-9, chance (0,1]")


def validate_spec_content(spec: "Spec") -> None:
    ids = spec.local_ids()
    seen_all: dict[str, str] = {}
    for f in spec.features:
        seen_all[f.identifier] = "feature"
        if f.kind == "block":
            for v in f.variants:
                if v not in BLOCK_VARIANTS:
                    raise InputError(f"Block {f.identifier}: variants must be from {BLOCK_VARIANTS}")
                vid = f"{f.identifier}_{v}"
                if vid in seen_all: raise InputError(f"Variant {vid!r} collides with {seen_all[vid]}")
                seen_all[vid] = f"variant of {f.identifier}"
            if f.tool and f.tool not in TOOLS_FOR_BLOCKS:
                raise InputError(f"Block {f.identifier}: tool must be one of {TOOLS_FOR_BLOCKS}")
            if f.mining_level and f.mining_level not in MINING_LEVELS:
                raise InputError(f"Block {f.identifier}: mining_level must be one of {MINING_LEVELS}")
    for f in spec.features:
        validate_art(f.art, f"{f.kind} {f.identifier}")
    for fd in spec.foods:
        validate_art(fd.art, f"food {fd.identifier}")
    for mat in spec.materials:
        validate_art(mat.art, f"material {mat.identifier}", tuple(mat.tools) + tuple(mat.armor))
        validate_material(spec, mat)
        for i in mat.item_ids():
            if i in seen_all: raise InputError(f"Material item {i!r} collides with {seen_all[i]}")
            seen_all[i] = f"material {mat.identifier}"
    local_blocks = {f.identifier for f in spec.features if f.kind == "block"} | {f"{f.identifier}_{v}" for f in spec.features for v in f.variants}
    for st in spec.structures:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", st.identifier):
            raise InputError(f"Structure identifier must be snake_case: {st.identifier!r}")
        if not st.layers or not all(st.layers) or any(not isinstance(row, str) for layer in st.layers for row in layer):
            raise InputError(f"Structure {st.identifier}: layers must be non-empty tuples of strings")
        w = len(st.layers[0][0]); d = len(st.layers[0])
        for layer in st.layers:
            if len(layer) != d or any(len(row) != w for row in layer):
                raise InputError(f"Structure {st.identifier}: every layer must be {w}x{d} (same width and depth)")
        if w > 48 or d > 48 or len(st.layers) > 48:
            raise InputError("Structure: at most 48x48x48")
        chars = {c for layer in st.layers for row in layer for c in row} - {".", " "}
        for c in chars:
            if c not in st.legend:
                raise InputError(f"Structure {st.identifier}: character {c!r} has no legend entry")
            block = st.legend[c].split("[")[0]
            if ":" not in block and block not in local_blocks:
                raise InputError(f"Structure {st.identifier}: {block!r} is not a block of this mod (use minecraft:... for vanilla)")
        if not (1 <= st.separation < st.spacing <= 256):
            raise InputError("Structure: 1 <= separation < spacing <= 256")
        if st.step not in ("surface_structures", "underground_structures"):
            raise InputError("Structure step must be surface_structures or underground_structures")
        if any(not BIOME_RE.match(b) for b in st.biomes):
            raise InputError("Structure biomes: overworld|nether|end, tags or biome ids")
    local_mobs = {m.identifier for m in spec.mobs}
    for b in spec.biomes:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", b.identifier):
            raise InputError(f"Biome identifier must be snake_case: {b.identifier!r}")
        if b.base not in ("plains", "forest", "desert", "taiga", "snowy_plains", "swamp"):
            raise InputError("Biome base must be plains, forest, desert, taiga, snowy_plains or swamp")
        for c in (b.sky_color, b.fog_color, b.water_color, b.grass_color, b.foliage_color):
            if c and not re.fullmatch(r"#[0-9a-fA-F]{6}", c):
                raise InputError("Biome colours must be #RRGGBB")
        if not (-2 <= b.temperature <= 2) or not (0 <= b.downfall <= 1):
            raise InputError("Biome temperature -2..2, downfall 0..1")
        bad = [m for m in b.mobs if m not in local_mobs]
        if bad:
            raise InputError(f"Biome {b.identifier}: unknown mobs {bad}")
    local_biomes = {b.identifier for b in spec.biomes}
    for dm in spec.dimensions:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", dm.identifier):
            raise InputError(f"Dimension identifier must be snake_case: {dm.identifier!r}")
        bad = [b for b in dm.biomes if b not in local_biomes]
        if bad:
            raise InputError(f"Dimension {dm.identifier}: unknown biomes {bad}")
        if dm.sky not in ("overworld", "nether", "end") or not (-1 <= dm.fixed_time <= 24000):
            raise InputError("Dimension sky must be overworld|nether|end; fixed_time -1 or 0..24000")
        if dm.noise not in ("minecraft:overworld", "minecraft:floating_islands", "minecraft:caves", "minecraft:amplified"):
            raise InputError("Dimension noise must be a vanilla noise settings id")
    for e in spec.enchantments:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", e.identifier):
            raise InputError(f"Enchantment identifier must be snake_case: {e.identifier!r}")
        if e.kind not in ("damage", "protection", "fire_aspect"):
            raise InputError("Enchantment kind must be damage, protection or fire_aspect")
        if not (1 <= e.max_level <= 10) or not (1 <= e.weight <= 100) or not e.items.startswith("#"):
            raise InputError("Enchantment: max_level 1-10, weight 1-100, items must be a tag (#minecraft:enchantable/weapon)")
    blocks = {f.identifier for f in spec.features if f.kind == "block"}
    seen_ores: set[str] = set()
    for o in spec.ores:
        if o.block not in blocks:
            raise InputError(f"Ore {o.block!r} is not a block of this mod")
        if o.block in seen_ores:
            raise InputError(f"One worldgen rule per block: {o.block}")
        seen_ores.add(o.block)
        if not (1 <= o.vein_size <= 64) or not (1 <= o.veins_per_chunk <= 64) or not (-64 <= o.min_y < o.max_y <= 320) or not (0 <= o.discard_on_air <= 1):
            raise InputError("Ore: vein_size 1-64, veins_per_chunk 1-64, -64 <= min_y < max_y <= 320, discard_on_air 0-1")
        if not o.biomes or any(not BIOME_RE.match(b) for b in o.biomes):
            raise InputError("Ore biomes: overworld|nether|end, biome tags (#minecraft:is_mountain) or biome ids")
    for sd in spec.sounds:
        if not re.fullmatch(r"[a-z][a-z0-9_.]{1,49}", sd.identifier):
            raise InputError(f"Sound identifier must be snake_case: {sd.identifier!r}")
        if sd.category not in ("master", "music", "record", "weather", "block", "hostile", "neutral", "player", "ambient", "voice"):
            raise InputError("Sound category must be a vanilla SoundSource name")
    for fd in spec.foods:
        validate_food(spec, fd)
        if fd.identifier in seen_all: raise InputError(f"Food {fd.identifier!r} collides with {seen_all[fd.identifier]}")
        seen_all[fd.identifier] = "food"
    seen_mobs: set[str] = set()
    for m in spec.mobs:
        if m.identifier in seen_mobs:
            raise InputError(f"Duplicate mob: {m.identifier}")
        seen_mobs.add(m.identifier)
        validate_mob(spec, m)
    seen: set[str] = set()
    for r in spec.recipes:
        if r.id in seen:
            raise InputError(f"Duplicate recipe id: {r.id}")
        seen.add(r.id)
        validate_recipe(ids, spec.mod_id, r)
    seen_blocks: set[str] = set()
    for d in spec.drops:
        if d.block in seen_blocks:
            raise InputError(f"Only one drop rule per block: {d.block}")
        seen_blocks.add(d.block)
        validate_drop(spec, d)
    if spec.tab is not None and not (1 <= len(spec.tab.strip()) <= 40):
        raise InputError("Creative tab label must be 1-40 chars")
    if spec.tab_icon is not None and spec.tab_icon not in ids:
        raise InputError(f"Tab icon {spec.tab_icon!r} must be an item or block of this mod")

# Deterministic supported syntax; natural language is preserved, not silently hallucinated.
PATTERNS = [
    ("item", re.compile(r"\b(?:item|items)\s*:\s*([^;\n]+)", re.I)),
    ("block", re.compile(r"\b(?:block|blocks)\s*:\s*([^;\n]+)", re.I)),
]
TAB_PATTERN = re.compile(r"\btab\s*:\s*([^;\n]+)", re.I)
MOB_PATTERNS = [("hostile", re.compile(r"\bhostile\s+(?:mob|mobs)\s*:\s*([^;\n]+)", re.I)),
                ("neutral", re.compile(r"\bneutral\s+(?:mob|mobs)\s*:\s*([^;\n]+)", re.I)),
                ("passive", re.compile(r"(?<!hostile )(?<!neutral )\b(?:mob|mobs)\s*:\s*([^;\n]+)", re.I))]
# Java constant names the generator reserves inside ModMain; user content may not shadow them.
RESERVED_JAVA_NAMES = {"MOD_ID"}


def java_constant_names(feature: Feature) -> list[str]:
    """Constant names ModMain.java will declare for a feature (mirrors fabric.py)."""
    base = feature.identifier.upper()
    return [base, base + "_ITEM"] if feature.kind == "block" else [base]


def check_java_name_collisions(features: list[Feature], extra_ids: list[str] = ()) -> None:
    owners: dict[str, str] = {name: "generator reserved" for name in RESERVED_JAVA_NAMES}
    for feature in features:
        for name in java_constant_names(feature):
            if name in owners:
                raise InputError(
                    f"{feature.kind} '{feature.identifier}' would declare Java constant {name}, "
                    f"which collides with {owners[name]}. Rename one of them.")
            owners[name] = f"{feature.kind} '{feature.identifier}'"
    for ident in extra_ids:
        name = ident.upper()
        if name in owners:
            raise InputError(f"'{ident}' would declare Java constant {name}, which collides with {owners[name]}. Rename one of them.")
        owners[name] = f"'{ident}'"


UNSUPPORTED = re.compile(r"\b(?:mob|entity|boss|biome|dimension|structure|worldgen|geckolib|animate|animation|portal|spell|GUI|HUD|multiplayer)\b", re.I)

def interpret(*, name: str, mod_id: str, package: str, idea: str, profile: str) -> Spec:
    from .config import SUPPORTED_PROFILE
    mid = project_id(mod_id)
    pkg = validate_package(package)
    if profile != SUPPORTED_PROFILE:
        raise InputError(f"Only {SUPPORTED_PROFILE!r} is implemented; other versions require a verified adapter")
    if not (1 <= len(name.strip()) <= 80 and 4 <= len(idea.strip()) <= 8000):
        raise InputError("Name (1–80 chars) and idea (4–8000 chars) are required")
    found: list[Feature] = []
    seen: set[str] = set()
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(idea):
            for raw in match.group(1).split(","):
                label = raw.strip().strip(". ")
                if not label:
                    continue
                identifier = normalize_id(label, content=True)
                if identifier in seen:
                    raise InputError("Item and block identifiers must be unique: " + identifier)
                seen.add(identifier)
                found.append(Feature(kind=kind, identifier=identifier, label=label))
    check_java_name_collisions(found)
    questions = []
    if not found and not any(p.search(idea) for _, p in MOB_PATTERNS):
        questions.append("For the deterministic starter, specify content as 'items: copper coin, ruby; blocks: ruby ore'. Other ideas can be retained for a human/agent implementation plan.")
    if UNSUPPORTED.search(idea):
        questions.append("Advanced mechanics/entities/worldgen are not generated by the current deterministic backend. Should they be planned as manually implemented future work?")
    if len(found) > 24:
        raise InputError("Prototype supports at most 24 item/block entries per generation")
    tab = None
    m = TAB_PATTERN.search(idea)
    if m:
        tab = m.group(1).strip().strip(". ")[:40] or None
    mobs: list[Mob] = []
    for behavior, pattern in MOB_PATTERNS:
        for match in pattern.finditer(idea):
            for raw in match.group(1).split(","):
                label = raw.strip().strip(". ")
                if label:
                    ident = normalize_id(label, content=True)
                    mobs.append(Mob(identifier=ident, label=label, behavior=behavior, egg_colors=default_egg_colors(ident, behavior)))
    if (mobs or found) and not questions:
        pass
    if mobs and not found:
        questions = [q for q in questions if "specify content" not in q]
    spec = Spec(SCHEMA_VERSION, name.strip(), mid, pkg, idea.strip(), profile, found, questions,
                ["Vanilla-inspired generated placeholder textures; visual assets require review", "New local Fabric project, not an edit to an existing mod"],
                tab=tab, tab_icon=(found[0].identifier if (tab and found) else None), mobs=mobs)
    validate_spec_content(spec)
    return spec

def has_content(spec: "Spec") -> bool:
    """True when the spec describes something the generator can emit: items/blocks, but also mobs, material sets (tools and
    armor), foods, enchantments, structures, biomes, dimensions or sounds on their own. One definition for the interpreter
    and the generator, so a mobs-only or gear-only mod is not rejected by one of them."""
    return bool(spec.features or spec.mobs or spec.materials or spec.foods or spec.enchantments
                or spec.structures or spec.biomes or spec.dimensions or spec.sounds)


def read_spec(raw: dict) -> Spec:
    """Reads schema 1 (items/blocks only) and 2 (recipes, drops, tab). Older specs upgrade in memory."""
    if raw.get("schema_version") not in (1, 2):
        raise InputError("Unsupported spec revision")
    spec = Spec(
        schema_version=SCHEMA_VERSION, name=str(raw["name"]), mod_id=normalize_id(raw["mod_id"]),
        package=validate_package(raw["package"]), idea=str(raw["idea"]),
        profile=str(raw["profile"]),
        features=[Feature(**{**f, "variants": tuple(f.get("variants", ())), "art": coerce_art(f.get("art"))}) for f in raw.get("features", [])],
        questions=list(raw.get("questions", [])), assumptions=list(raw.get("assumptions", [])),
        recipes=[Recipe(**{**r, "pattern": tuple(r.get("pattern", ())), "ingredients": tuple(r.get("ingredients", ()))}) for r in raw.get("recipes", [])],
        drops=[Drop(**d) for d in raw.get("drops", [])],
        tab=raw.get("tab"), tab_icon=raw.get("tab_icon"),
        materials=[Material(**{**m, "tools": tuple(m.get("tools", ())), "armor": tuple(m.get("armor", ())), "armor_defense": tuple(m.get("armor_defense", (2, 6, 5, 2))), "art": coerce_art(m.get("art"))}) for m in raw.get("materials", [])],
        foods=[Food(**{**f, "effects": tuple(f.get("effects", ())), "art": coerce_art(f.get("art"))}) for f in raw.get("foods", [])],
        theme=str(raw.get("theme") or "")[:600],
        sounds=[Sound(**x) for x in raw.get("sounds", [])],
        ores=[Ore(**{**o, "biomes": tuple(o.get("biomes", ("overworld",)))}) for o in raw.get("ores", [])],
        enchantments=[Enchantment(**e) for e in raw.get("enchantments", [])],
        structures=[Structure(**{**x, "layers": tuple(tuple(l) for l in x.get("layers", ())), "biomes": tuple(x.get("biomes", ("overworld",)))}) for x in raw.get("structures", [])],
        biomes=[Biome(**{**b, "mobs": tuple(b.get("mobs", ()))}) for b in raw.get("biomes", [])],
        dimensions=[Dimension(**{**d, "biomes": tuple(d.get("biomes", ()))}) for d in raw.get("dimensions", [])],
        mobs=[Mob(**{**m, "drops": tuple(coerce_mob_drop(d) for d in m.get("drops", ())), "spawn": coerce_spawn(m.get("spawn")), "art": coerce_art(m.get("art")),
                      "egg_colors": tuple(m.get("egg_colors") or default_egg_colors(m.get("identifier", ""), m.get("behavior", "passive")))})
              for m in raw.get("mobs", [])],
    )
    validate_spec_content(spec)
    return spec
