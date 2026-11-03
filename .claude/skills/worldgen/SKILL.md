---
name: worldgen
description: World generation on Fabric 1.21.1 — what the generator already produces (ores, structures from text layers, biomes, dimensions with a key item) and how to extend it by hand: structure NBT, jigsaw pools, biome JSON, dimension/noise JSON, BiomeModifications in Java. Use for any "appears in the world" request beyond the forms.
---

# World generation (datapack JSON + a little Java)

Everything here is data under `src/main/resources/data/<mod>/…` and is loaded by the server; a malformed file fails world load
loudly in the server log and in `craftctl gametest` (`worldgenIsRegistered`). Reload without restarting: `/reload` only for
non-worldgen data; worldgen needs a new world.

## What the generator already makes (edit the spec, don't hand-write these)
- **Ores**: `worldgen/configured_feature/<block>.json` + `placed_feature/<block>.json` + `BiomeModifications.addFeature(...)` in ModMain (craftctl add-ore / Items tab).
- **Structures from text layers**: `structure/<id>.nbt` (written by the controller's NBT writer), `worldgen/template_pool/<id>.json`,
  `worldgen/structure/<id>.json` (jigsaw, size 1), `worldgen/structure_set/<id>.json` (random_spread spacing/separation/salt),
  `tags/worldgen/biome/has_structure/<id>.json` (where). craftctl add-structure / World-Gen tab.
- **Biomes**: `worldgen/biome/<id>.json` with features/carvers copied from a vanilla base (plains/forest/desert/taiga/snowy_plains/swamp), colours, spawners.
- **Dimensions**: `dimension_type/<id>.json` + `dimension/<id>.json` (noise generator with `minecraft:overworld|floating_islands|caves|amplified` settings and a fixed or multi-noise biome source) + `<Id>KeyItem` (right-click teleports with `ServerPlayer.teleportTo(ServerLevel, x, y, z, yaw, pitch)`).

## Extending by hand
- **Bigger structures / multi-piece**: more template pools with several elements and `size` > 1 in the jigsaw structure; connect pieces with jigsaw blocks inside the NBT (`minecraft:jigsaw` block entity with `name`/`target`/`pool`). Author the NBT in-game with a structure block and copy the `.nbt` from `saves/<world>/generated/<mod>/structures/`.
- **Loot in structures**: put a chest in the NBT with a `LootTable` tag, or use a processor list (`worldgen/processor_list`) with `minecraft:rule` processors to swap blocks.
- **Where a structure spawns**: edit the `has_structure/<id>.json` tag (biome ids or tags like `#minecraft:is_mountain`); spacing/separation in the structure set.
- **Biome placement inside a dimension**: multi-noise parameters in `dimension/<id>.json` (`temperature`, `humidity`, `continentalness`, `erosion`, `weirdness`, `depth`, `offset`); the generator spreads your biomes across temperature; tune to taste.
- **Custom noise**: `worldgen/noise_settings/<id>.json` (copy vanilla's from the client jar `data/minecraft/worldgen/noise_settings/overworld.json` and edit `sea_level`, `default_block`, `surface_rule`).
- **Adding features to vanilla biomes**: Java, in ModMain: `BiomeModifications.addFeature(BiomeSelectors.tag(BiomeTags.IS_FOREST), GenerationStep.Decoration.VEGETAL_DECORATION, ResourceKey.create(Registries.PLACED_FEATURE, id("my_flower_patch")))` with your own configured/placed feature JSON (`minecraft:random_patch`, `minecraft:tree`, `minecraft:ore`, `minecraft:simple_block`, `minecraft:lake`).
- **Custom overworld biomes**: not possible with Fabric API alone (the overworld biome source is a fixed preset); use a dimension, or ask the user before adding TerraBlender.
- **Portals**: the key item is the simplest reliable travel; a nether-style portal frame needs a custom `Block` + `PortalProcessor`/teleport logic — treat as a separate feature with its own acceptance criteria.

## Checking
`craftctl gametest` runs `worldgenIsRegistered` (structure, structure set, biome and dimension registries). To see a structure quickly: `/locate structure <mod>:<id>` then `/tp`. Dimension: right-click the key; `/execute in <mod>:<id> run tp @s 0 100 0`.
