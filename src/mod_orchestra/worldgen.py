"""Structures, biomes and dimensions as datapack JSON (+ the structure NBT and the dimension key item Java)."""
from __future__ import annotations
import hashlib
import json
from .spec import Spec, Structure, Biome, Dimension
from .nbt import structure_template
from .geckolib import biome_selector_java  # noqa: F401  (kept for parity; structures use biome tags, not Java)

BASE_FEATURES = {
    # feature lists copied from vanilla biomes (1.21.1 generation steps, 11 entries) — enough to feel like the base biome
    "plains": [[], ["minecraft:lake_lava_underground", "minecraft:lake_lava_surface"], ["minecraft:amethyst_geode"], ["minecraft:monster_room", "minecraft:monster_room_deep"], [],
               ["minecraft:ore_dirt", "minecraft:ore_gravel", "minecraft:ore_granite_upper", "minecraft:ore_granite_lower", "minecraft:ore_diorite_upper", "minecraft:ore_diorite_lower", "minecraft:ore_andesite_upper", "minecraft:ore_andesite_lower", "minecraft:ore_tuff", "minecraft:ore_coal_upper", "minecraft:ore_coal_lower", "minecraft:ore_iron_upper", "minecraft:ore_iron_middle", "minecraft:ore_iron_small", "minecraft:ore_gold", "minecraft:ore_gold_lower", "minecraft:ore_redstone", "minecraft:ore_redstone_lower", "minecraft:ore_diamond", "minecraft:ore_diamond_medium", "minecraft:ore_diamond_large", "minecraft:ore_diamond_buried", "minecraft:ore_lapis", "minecraft:ore_lapis_buried", "minecraft:ore_copper", "minecraft:underwater_magma", "minecraft:disk_sand", "minecraft:disk_clay", "minecraft:disk_gravel"],
               [], ["minecraft:spring_water", "minecraft:spring_lava"], ["minecraft:glow_lichen", "minecraft:patch_tall_grass_2", "minecraft:trees_plains", "minecraft:flower_plains", "minecraft:patch_grass_plain", "minecraft:brown_mushroom_normal", "minecraft:red_mushroom_normal", "minecraft:patch_sugar_cane", "minecraft:patch_pumpkin"], ["minecraft:freeze_top_layer"], []],
}
BASE_FEATURES["forest"] = [l[:] for l in BASE_FEATURES["plains"]]; BASE_FEATURES["forest"][8] = ["minecraft:glow_lichen", "minecraft:forest_flowers", "minecraft:trees_birch_and_oak", "minecraft:flower_default", "minecraft:patch_grass_forest", "minecraft:brown_mushroom_normal", "minecraft:red_mushroom_normal", "minecraft:patch_sugar_cane", "minecraft:patch_pumpkin"]
BASE_FEATURES["desert"] = [l[:] for l in BASE_FEATURES["plains"]]; BASE_FEATURES["desert"][8] = ["minecraft:glow_lichen", "minecraft:patch_dead_bush_2", "minecraft:patch_cactus_desert", "minecraft:patch_sugar_cane_desert", "minecraft:patch_pumpkin"]; BASE_FEATURES["desert"][2] = ["minecraft:amethyst_geode", "minecraft:fossil_upper", "minecraft:fossil_lower"]
BASE_FEATURES["taiga"] = [l[:] for l in BASE_FEATURES["plains"]]; BASE_FEATURES["taiga"][8] = ["minecraft:glow_lichen", "minecraft:trees_taiga", "minecraft:flower_default", "minecraft:patch_grass_taiga", "minecraft:brown_mushroom_taiga", "minecraft:red_mushroom_taiga", "minecraft:patch_sugar_cane", "minecraft:patch_pumpkin", "minecraft:patch_berry_common"]
BASE_FEATURES["snowy_plains"] = [l[:] for l in BASE_FEATURES["plains"]]; BASE_FEATURES["snowy_plains"][8] = ["minecraft:glow_lichen", "minecraft:patch_tall_grass_2", "minecraft:brown_mushroom_normal", "minecraft:red_mushroom_normal", "minecraft:patch_sugar_cane", "minecraft:patch_pumpkin"]
BASE_FEATURES["swamp"] = [l[:] for l in BASE_FEATURES["plains"]]; BASE_FEATURES["swamp"][8] = ["minecraft:glow_lichen", "minecraft:trees_swamp", "minecraft:flower_swamp", "minecraft:patch_grass_normal", "minecraft:patch_dead_bush", "minecraft:patch_waterlily", "minecraft:brown_mushroom_swamp", "minecraft:red_mushroom_swamp", "minecraft:patch_sugar_cane_swamp", "minecraft:patch_pumpkin"]
BASE_SURFACE = {"plains": "minecraft:grass_block", "forest": "minecraft:grass_block", "desert": "minecraft:sand", "taiga": "minecraft:grass_block", "snowy_plains": "minecraft:snow_block", "swamp": "minecraft:grass_block"}


def _hex(c: str) -> int:
    return int(c.lstrip("#"), 16)


def _biome_tag_values(spec: Spec, biomes: tuple) -> list:
    out = []
    for b in biomes:
        if b == "overworld": out.append("#minecraft:is_overworld")
        elif b == "nether": out.append("#minecraft:is_nether")
        elif b == "end": out.append("#minecraft:is_end")
        else: out.append(b)
    return out


# ---- structures ----
def structure_blocks(spec: Spec, st: Structure) -> tuple[list, tuple]:
    blocks = []
    for y, layer in enumerate(st.layers):
        for z, row in enumerate(layer):
            for x, ch in enumerate(row):
                if ch in (".", " "): continue
                state = st.legend[ch]
                if ":" not in state.split("[")[0]:
                    state = f"{spec.mod_id}:{state}"
                blocks.append((x, y, z, state))
    size = (len(st.layers[0][0]), len(st.layers), len(st.layers[0]))
    return blocks, size


def structure_files(spec: Spec) -> dict[str, object]:
    """Relative paths under src/main/resources -> bytes (nbt) or JSON objects."""
    mod = spec.mod_id; out: dict[str, object] = {}
    for st in spec.structures:
        blocks, size = structure_blocks(spec, st)
        out[f"data/{mod}/structure/{st.identifier}.nbt"] = structure_template(blocks, size)
        out[f"data/{mod}/worldgen/template_pool/{st.identifier}.json"] = {"fallback": "minecraft:empty", "elements": [
            {"weight": 1, "element": {"element_type": "minecraft:single_pool_element", "location": f"{mod}:{st.identifier}", "processors": "minecraft:empty", "projection": "rigid"}}]}
        out[f"data/{mod}/worldgen/structure/{st.identifier}.json"] = {"type": "minecraft:jigsaw", "biomes": f"#{mod}:has_structure/{st.identifier}", "step": st.step,
            "spawn_overrides": {}, "terrain_adaptation": "beard_thin" if st.step == "surface_structures" else "none",
            "start_pool": f"{mod}:{st.identifier}", "size": 1, "max_distance_from_center": 80, "use_expansion_hack": False,
            **({"start_height": {"type": "minecraft:uniform", "min_inclusive": {"absolute": -40}, "max_inclusive": {"absolute": 20}}} if st.step == "underground_structures" else {"start_height": {"absolute": 0}, "project_start_to_heightmap": "WORLD_SURFACE_WG"})}
        salt = st.salt or int(hashlib.sha256(f"{mod}:{st.identifier}".encode()).hexdigest()[:8], 16) % 2_000_000_000
        out[f"data/{mod}/worldgen/structure_set/{st.identifier}.json"] = {"structures": [{"structure": f"{mod}:{st.identifier}", "weight": 1}],
            "placement": {"type": "minecraft:random_spread", "spacing": int(st.spacing), "separation": int(st.separation), "salt": salt}}
        out[f"data/{mod}/tags/worldgen/biome/has_structure/{st.identifier}.json"] = {"replace": False, "values": _biome_tag_values(spec, st.biomes)}
    return out


# ---- biomes ----
def biome_json(spec: Spec, b: Biome) -> dict:
    spawners = {"monster": [], "creature": [], "ambient": [], "water_creature": [], "underground_water_creature": [], "water_ambient": [], "misc": [], "axolotls": []}
    cat_of = {m.identifier: m.behavior for m in spec.mobs}
    for mid in b.mobs:
        cat = "monster" if cat_of.get(mid) == "hostile" else "creature"
        spawners[cat].append({"type": f"{spec.mod_id}:{mid}", "weight": 10, "minCount": 1, "maxCount": 3})
    if b.base != "desert":
        spawners["creature"] += [{"type": "minecraft:sheep", "weight": 12, "minCount": 4, "maxCount": 4}, {"type": "minecraft:cow", "weight": 8, "minCount": 4, "maxCount": 4}]
    spawners["monster"] += [{"type": "minecraft:zombie", "weight": 95, "minCount": 4, "maxCount": 4}, {"type": "minecraft:skeleton", "weight": 100, "minCount": 4, "maxCount": 4}, {"type": "minecraft:creeper", "weight": 100, "minCount": 4, "maxCount": 4}]
    effects = {"sky_color": _hex(b.sky_color), "fog_color": _hex(b.fog_color), "water_color": _hex(b.water_color), "water_fog_color": 329011, "mood_sound": {"sound": "minecraft:ambient.cave", "tick_delay": 6000, "block_search_extent": 8, "offset": 2.0}}
    if b.grass_color: effects["grass_color"] = _hex(b.grass_color)
    if b.foliage_color: effects["foliage_color"] = _hex(b.foliage_color)
    return {"temperature": float(b.temperature), "downfall": float(b.downfall), "has_precipitation": bool(b.precipitation), "effects": effects,
            "carvers": {"air": ["minecraft:cave", "minecraft:cave_extra_underground", "minecraft:canyon"]},
            "features": BASE_FEATURES[b.base], "spawners": spawners, "spawn_costs": {}}


# ---- dimensions ----
def dimension_files(spec: Spec) -> dict[str, object]:
    mod = spec.mod_id; out: dict[str, object] = {}
    for d in spec.dimensions:
        sky = {"overworld": {"has_skylight": True, "has_ceiling": False, "ambient_light": 0.0, "effects": "minecraft:overworld", "natural": True, "bed_works": True},
               "nether": {"has_skylight": False, "has_ceiling": True, "ambient_light": 0.1, "effects": "minecraft:the_nether", "natural": False, "bed_works": False},
               "end": {"has_skylight": False, "has_ceiling": False, "ambient_light": 0.0, "effects": "minecraft:the_end", "natural": False, "bed_works": False}}[d.sky]
        dt = {"ultrawarm": False, "coordinate_scale": 1.0, "piglin_safe": False, "respawn_anchor_works": False, "has_raids": True,
              "min_y": -64, "height": 384, "logical_height": 384, "infiniburn": "#minecraft:infiniburn_overworld",
              "monster_spawn_light_level": {"type": "minecraft:uniform", "min_inclusive": 0, "max_inclusive": 7}, "monster_spawn_block_light_limit": 0, **sky}
        if d.fixed_time >= 0: dt["fixed_time"] = int(d.fixed_time)
        out[f"data/{mod}/dimension_type/{d.identifier}.json"] = dt
        biomes = [f"{mod}:{b}" for b in d.biomes] or ["minecraft:plains"]
        if len(biomes) == 1:
            source = {"type": "minecraft:fixed", "biome": biomes[0]}
        else:
            params = []
            for i, b in enumerate(biomes):   # spread biomes across temperature so multi-noise picks them in regions
                t = -1.0 + 2.0 * i / max(1, len(biomes) - 1)
                params.append({"biome": b, "parameters": {"temperature": t, "humidity": 0.0, "continentalness": 0.0, "erosion": 0.0, "weirdness": 0.0, "depth": 0.0, "offset": 0.0}})
            source = {"type": "minecraft:multi_noise", "biomes": params}
        out[f"data/{mod}/dimension/{d.identifier}.json"] = {"type": f"{mod}:{d.identifier}", "generator": {"type": "minecraft:noise", "settings": d.noise, "biome_source": source}}
    return out


def dimension_key_java(spec: Spec, d: Dimension) -> str:
    cls = "".join(p.capitalize() for p in d.identifier.split("_")) + "KeyItem"
    return "\n".join([
        f"package {spec.package};", "",
        "import net.minecraft.core.registries.Registries;", "import net.minecraft.resources.ResourceKey;", "import net.minecraft.resources.ResourceLocation;",
        "import net.minecraft.server.level.ServerLevel;", "import net.minecraft.server.level.ServerPlayer;", "import net.minecraft.world.InteractionHand;",
        "import net.minecraft.world.InteractionResultHolder;", "import net.minecraft.world.entity.player.Player;", "import net.minecraft.world.item.Item;",
        "import net.minecraft.world.item.ItemStack;", "import net.minecraft.world.level.Level;", "import net.minecraft.world.level.levelgen.Heightmap;", "",
        f"/** Right-click: travel to {d.identifier} (and back to the overworld from there). */",
        f"public class {cls} extends Item {{",
        f'    public static final ResourceKey<Level> DIMENSION = ResourceKey.create(Registries.DIMENSION, ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "{d.identifier}"));',
        f"    public {cls}(Properties properties) {{ super(properties.stacksTo(1)); }}", "",
        "    @Override",
        "    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {",
        "        ItemStack stack = player.getItemInHand(hand);",
        "        if (player instanceof ServerPlayer sp && !level.isClientSide) {",
        "            ResourceKey<Level> targetKey = level.dimension().equals(DIMENSION) ? Level.OVERWORLD : DIMENSION;",
        "            ServerLevel target = sp.server.getLevel(targetKey);",
        "            if (target == null) return InteractionResultHolder.fail(stack);",
        "            int x = sp.getBlockX(), z = sp.getBlockZ();",
        "            int y = target.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x, z);",
        "            sp.teleportTo(target, x + 0.5, Math.max(y, target.getMinBuildHeight() + 2), z + 0.5, sp.getYRot(), sp.getXRot());",
        "            player.getCooldowns().addCooldown(this, 40);",
        "        }",
        "        return InteractionResultHolder.sidedSuccess(stack, level.isClientSide);",
        "    }", "}", ""])


def dimension_registrations(spec: Spec) -> tuple[list[str], list[str]]:
    fields, init = [], []
    for d in spec.dimensions:
        key = d.key_item or f"{d.identifier}_key"
        cls = "".join(p.capitalize() for p in d.identifier.split("_")) + "KeyItem"
        fields.append(f'    public static final Item {key.upper()} = Registry.register(BuiltInRegistries.ITEM, id("{key}"), new {cls}(new Item.Properties()));')
        init.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.TOOLS_AND_UTILITIES).register(entries -> entries.accept({key.upper()}));")
    return fields, init
