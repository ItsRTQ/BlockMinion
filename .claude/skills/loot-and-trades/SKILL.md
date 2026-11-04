---
name: loot-and-trades
description: Inject items into vanilla loot (chests, mobs, blocks) and add villager / wandering trader trades on Fabric 1.21.1 (Mojang mappings). Use when mod items should appear in dungeon chests, drop from vanilla mobs, or be sold by villagers.
---

# Loot injection and trades (1.21.1 Mojmap)

## Add a pool to a vanilla loot table
```java
private static final ResourceKey<LootTable> SIMPLE_DUNGEON = ResourceKey.create(Registries.LOOT_TABLE, ResourceLocation.withDefaultNamespace("chests/simple_dungeon"));
LootTableEvents.MODIFY.register((key, tableBuilder, source, registries) -> {
    if (source.isBuiltin() && key.equals(SIMPLE_DUNGEON)) {
        tableBuilder.withPool(LootPool.lootPool()
            .setRolls(ConstantValue.exactly(1))
            .when(LootItemRandomChanceCondition.randomChance(0.35f))
            .add(LootItem.lootTableItem(ModMain.SKY_CRYSTAL).apply(SetItemCountFunction.setCount(UniformGenerator.between(1, 3)))));
    }
});
```
Other keys: `chests/village/village_toolsmith`, `chests/abandoned_mineshaft`, `chests/stronghold_library`, `entities/zombie`, `blocks/grass_block`.
Packages: `net.fabricmc.fabric.api.loot.v3.LootTableEvents`, `net.minecraft.world.level.storage.loot.*` (`LootPool`, `LootTable`, `entries.LootItem`,
`functions.SetItemCountFunction`, `predicates.LootItemRandomChanceCondition`, `providers.number.ConstantValue`/`UniformGenerator`).
Only `source.isBuiltin()` tables should be modified (data packs can override).

## Villager trades
```java
TradeOfferHelper.registerVillagerOffers(VillagerProfession.TOOLSMITH, 2, factories ->
    factories.add((entity, random) -> new MerchantOffer(new ItemCost(Items.EMERALD, 5), new ItemStack(ModMain.SKY_CRYSTAL, 2), 8, 10, 0.05f)));
TradeOfferHelper.registerWanderingTraderOffers(1, factories ->
    factories.add((entity, random) -> new MerchantOffer(new ItemCost(Items.EMERALD, 3), new ItemStack(ModMain.SKY_CRYSTAL), 4, 5, 0.05f)));
```
`net.fabricmc.fabric.api.object.builder.v1.trade.TradeOfferHelper`, `net.minecraft.world.item.trading.MerchantOffer` / `ItemCost`, `net.minecraft.world.entity.npc.VillagerProfession`.
Level 1–5 for villagers (unlocks with profession level). Compiled reference: `examples/kitchen_sink/.../LootAndTradesExample.java`.
