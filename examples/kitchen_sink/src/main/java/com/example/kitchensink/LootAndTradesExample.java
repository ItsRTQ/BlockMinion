package com.example.kitchensink;

import net.fabricmc.fabric.api.loot.v3.LootTableEvents;
import net.fabricmc.fabric.api.object.builder.v1.trade.TradeOfferHelper;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.npc.VillagerProfession;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.trading.ItemCost;
import net.minecraft.world.item.trading.MerchantOffer;
import net.minecraft.world.level.storage.loot.LootPool;
import net.minecraft.world.level.storage.loot.LootTable;
import net.minecraft.world.level.storage.loot.entries.LootItem;
import net.minecraft.world.level.storage.loot.functions.SetItemCountFunction;
import net.minecraft.world.level.storage.loot.predicates.LootItemRandomChanceCondition;
import net.minecraft.world.level.storage.loot.providers.number.ConstantValue;
import net.minecraft.world.level.storage.loot.providers.number.UniformGenerator;

/** Compiled reference for the `loot-and-trades` skill. */
public final class LootAndTradesExample {
    private static final ResourceKey<LootTable> SIMPLE_DUNGEON = ResourceKey.create(Registries.LOOT_TABLE, ResourceLocation.withDefaultNamespace("chests/simple_dungeon"));
    private LootAndTradesExample() {}

    public static void register() {
        LootTableEvents.MODIFY.register((key, tableBuilder, source, registries) -> {
            if (source.isBuiltin() && key.equals(SIMPLE_DUNGEON)) {
                tableBuilder.withPool(LootPool.lootPool()
                    .setRolls(ConstantValue.exactly(1))
                    .when(LootItemRandomChanceCondition.randomChance(0.35f))
                    .add(LootItem.lootTableItem(ModMain.SKY_CRYSTAL).apply(SetItemCountFunction.setCount(UniformGenerator.between(1, 3)))));
            }
        });
        TradeOfferHelper.registerVillagerOffers(VillagerProfession.TOOLSMITH, 2, factories ->
            factories.add((entity, random) -> new MerchantOffer(new ItemCost(Items.EMERALD, 5), new ItemStack(ModMain.SKY_CRYSTAL, 2), 8, 10, 0.05f)));
        TradeOfferHelper.registerWanderingTraderOffers(1, factories ->
            factories.add((entity, random) -> new MerchantOffer(new ItemCost(Items.EMERALD, 3), new ItemStack(ModMain.SKY_CRYSTAL), 4, 5, 0.05f)));
    }
}
