package com.example.kitchensink.gear;

import com.example.kitchensink.ModMain;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.BlockTags;
import net.minecraft.tags.TagKey;
import net.minecraft.world.item.Tier;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.level.block.Block;

/** Generated tier for material 'crystal' (Crystal). */
public final class CrystalTier implements Tier {
    public static final CrystalTier INSTANCE = new CrystalTier();

    @Override public int getUses() { return 500; }
    @Override public float getSpeed() { return 6.0F; }
    @Override public float getAttackDamageBonus() { return 2.0F; }
    @Override public TagKey<Block> getIncorrectBlocksForDrops() { return BlockTags.INCORRECT_FOR_IRON_TOOL; }
    @Override public int getEnchantmentValue() { return 14; }
    @Override public Ingredient getRepairIngredient() { return Ingredient.of(ModMain.SKY_CRYSTAL); }
}
