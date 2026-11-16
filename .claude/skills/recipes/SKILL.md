---
name: recipes
description: Author Minecraft 1.21.1 recipes, block drops and a creative tab for a craftctl spec or directly as datapack JSON. Use when a task mentions crafting, smelting, recipes, drops, loot or a creative tab.
---

# Recipes, drops and creative tab (Fabric 1.21.1, Mojang mappings)

## Where things live (1.21 datapack folders are singular)
- Recipes: `src/main/resources/data/<mod_id>/recipe/<name>.json`
- Unlock advancement (so the recipe shows in the recipe book): `data/<mod_id>/advancement/recipes/<name>.json`
- Block loot: `data/<mod_id>/loot_table/blocks/<block>.json`
- Lang: `assets/<mod_id>/lang/en_us.json` (`item.<mod>.<id>`, `block.<mod>.<id>`, `itemGroup.<mod>.<tab_id>`)

## Preferred path: fill the craftctl spec, let the generator render
Before generation the user adds recipes, drops and the tab to the spec in the tool; the generator writes correct JSON and Java.
As an agent you do not edit the spec: when it lacks one, say in plain words under `needs_user` which recipe, drop or tab it
needs (never a command). After generation, write the JSON files yourself following the formats below and report them in `changed_files`.

## Ingredient and result ids
- Local content: `ruby`, `ruby_ore` (must exist in the mod). Namespaced: `minecraft:stick`. Tag: `#minecraft:planks`.
- Ingredient JSON: `{"item": "ns:id"}` or `{"tag": "ns:id"}`. Result JSON (1.20.5+): `{"id": "ns:id", "count": N}`.

## Shaped (position matters)
```json
{"type": "minecraft:crafting_shaped", "category": "misc",
 "pattern": ["RRR", " S ", " S "],
 "key": {"R": {"item": "<mod>:ruby"}, "S": {"item": "minecraft:stick"}},
 "result": {"id": "<mod>:ruby_pickaxe", "count": 1}}
```
Pattern: 1–3 rows, same width, 1–3 chars, space = empty. Standard patterns:
- block of 9: `["XXX","XXX","XXX"]` · pickaxe `["XXX"," S "," S "]` · sword `[" X "," X "," S "]` · axe `["XX","XS"," S"]`
- shovel `["X","S","S"]` · hoe `["XX"," S"," S"]` · helmet `["XXX","X X"]` · chestplate `["X X","XXX","XXX"]`
- leggings `["XXX","X X","X X"]` · boots `["X X","X X"]` · stairs `["X  ","XX ","XXX"]` · slab (count 6) `["XXX"]`

## Shapeless (any position, 1–9 ingredients)
```json
{"type": "minecraft:crafting_shapeless", "category": "misc",
 "ingredients": [{"item": "<mod>:ruby_block"}], "result": {"id": "<mod>:ruby", "count": 9}}
```

## Cooking (smelting / blasting / smoking / campfire_cooking; exactly one ingredient)
```json
{"type": "minecraft:smelting", "category": "misc", "ingredient": {"item": "<mod>:ruby_ore"},
 "result": {"id": "<mod>:ruby"}, "experience": 0.7, "cookingtime": 200}
```
cookingtime: smelting 200, blasting 100, smoking 100, campfire 600. Ores: experience 0.7–1.0.

## Unlock advancement (one per recipe)
```json
{"parent": "minecraft:recipes/root",
 "criteria": {"has_the_recipe": {"trigger": "minecraft:recipe_unlocked", "conditions": {"recipe": "<mod>:<name>"}},
              "has_input": {"trigger": "minecraft:inventory_changed", "conditions": {"items": [{"items": ["<mod>:ruby"]}]}}},
 "requirements": [["has_the_recipe", "has_input"]], "rewards": {"recipes": ["<mod>:<name>"]}}
```

## Ore-style block drop (silk touch -> block, else item with Fortune)
```json
{"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:alternatives", "children": [
  {"type": "minecraft:item", "name": "<mod>:ruby_ore", "conditions": [{"condition": "minecraft:match_tool",
     "predicate": {"predicates": {"minecraft:enchantments": [{"enchantments": "minecraft:silk_touch", "levels": {"min": 1}}]}}}]},
  {"type": "minecraft:item", "name": "<mod>:ruby", "functions": [
     {"function": "minecraft:set_count", "count": {"type": "minecraft:uniform", "min": 1, "max": 2}},
     {"function": "minecraft:apply_bonus", "enchantment": "minecraft:fortune", "formula": "minecraft:ore_drops"},
     {"function": "minecraft:explosion_decay"}]}]}]}]}
```

## Creative tab (Java, Mojang mappings)
```java
public static final ResourceKey<CreativeModeTab> TAB_KEY = ResourceKey.create(Registries.CREATIVE_MODE_TAB, id("<mod>_tab"));
public static final CreativeModeTab TAB = FabricItemGroup.builder()
    .icon(() -> new ItemStack(RUBY)).title(Component.translatable("itemGroup.<mod>.<mod>_tab"))
    .displayItems((params, output) -> { output.accept(RUBY); output.accept(RUBY_ORE_ITEM); }).build();
// in onInitialize():  Registry.register(BuiltInRegistries.CREATIVE_MODE_TAB, TAB_KEY, TAB);
```
Imports: `net.fabricmc.fabric.api.itemgroup.v1.FabricItemGroup`, `net.minecraft.core.registries.Registries`,
`net.minecraft.network.chat.Component`, `net.minecraft.resources.ResourceKey`, `net.minecraft.world.item.CreativeModeTab`, `net.minecraft.world.item.ItemStack`.

## Verify
`./gradlew build` catches Java only. Recipe/loot JSON errors show in the dedicated server log at datapack load
(`Couldn't parse element minecraft:recipe/...`) — the user runs `craftctl request-smoke`/`server-smoke`. Recipe-book
visibility and actual crafting are client checks the user performs; never claim them.
