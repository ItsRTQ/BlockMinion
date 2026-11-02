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
class Feature:
    kind: str
    identifier: str
    label: str
    shape: str = ""        # placeholder texture silhouette: gem | ingot | food | block (default by kind)
    color: str = ""        # optional hex (#RRGGBB) tint for the placeholder texture

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
    egg_colors: tuple[int, int] = DEFAULT_EGG_COLORS


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

    def to_dict(self) -> dict:
        return asdict(self)

    def local_ids(self) -> set[str]:
        ids = {f.identifier for f in self.features}
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


def validate_mob(spec: "Spec", m: Mob) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", m.identifier):
        raise InputError(f"Mob identifier must be snake_case (2-50 chars): {m.identifier!r}")
    if m.identifier in spec.local_ids() or f"{m.identifier}_spawn_egg" in spec.local_ids():
        raise InputError(f"Mob identifier {m.identifier!r} collides with an item/block (its spawn egg is <id>_spawn_egg)")
    if m.behavior not in MOB_BEHAVIORS:
        raise InputError(f"Mob behavior must be one of {MOB_BEHAVIORS}")
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
    for mat in spec.materials:
        validate_material(spec, mat)
        for i in mat.item_ids():
            if i in seen_all: raise InputError(f"Material item {i!r} collides with {seen_all[i]}")
            seen_all[i] = f"material {mat.identifier}"
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

def read_spec(raw: dict) -> Spec:
    """Reads schema 1 (items/blocks only) and 2 (recipes, drops, tab). Older specs upgrade in memory."""
    if raw.get("schema_version") not in (1, 2):
        raise InputError("Unsupported spec revision")
    spec = Spec(
        schema_version=SCHEMA_VERSION, name=str(raw["name"]), mod_id=normalize_id(raw["mod_id"]),
        package=validate_package(raw["package"]), idea=str(raw["idea"]),
        profile=str(raw["profile"]),
        features=[Feature(**f) for f in raw.get("features", [])],
        questions=list(raw.get("questions", [])), assumptions=list(raw.get("assumptions", [])),
        recipes=[Recipe(**{**r, "pattern": tuple(r.get("pattern", ())), "ingredients": tuple(r.get("ingredients", ()))}) for r in raw.get("recipes", [])],
        drops=[Drop(**d) for d in raw.get("drops", [])],
        tab=raw.get("tab"), tab_icon=raw.get("tab_icon"),
        materials=[Material(**{**m, "tools": tuple(m.get("tools", ())), "armor": tuple(m.get("armor", ())), "armor_defense": tuple(m.get("armor_defense", (2, 6, 5, 2)))}) for m in raw.get("materials", [])],
        foods=[Food(**{**f, "effects": tuple(f.get("effects", ()))}) for f in raw.get("foods", [])],
        theme=str(raw.get("theme") or "")[:600],
        mobs=[Mob(**{**m, "drops": tuple(coerce_mob_drop(d) for d in m.get("drops", ())),
                      "egg_colors": tuple(m.get("egg_colors") or default_egg_colors(m.get("identifier", ""), m.get("behavior", "passive")))})
              for m in raw.get("mobs", [])],
    )
    validate_spec_content(spec)
    return spec
