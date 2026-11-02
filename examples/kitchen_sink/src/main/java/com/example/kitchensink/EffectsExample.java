package com.example.kitchensink;

import net.fabricmc.fabric.api.registry.FabricBrewingRecipeRegistryBuilder;
import net.fabricmc.fabric.api.registry.FuelRegistry;
import net.minecraft.core.Holder;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffectCategory;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.alchemy.Potion;
import net.minecraft.world.item.alchemy.Potions;

/** Compiled reference for the `effects` skill: custom status effect, potion + brewing; plus fuel from `items`. */
public final class EffectsExample {
    public static class CrystalSightEffect extends MobEffect {
        public CrystalSightEffect() {
            super(MobEffectCategory.BENEFICIAL, 0x4FD1FF);
        }

        @Override
        public boolean shouldApplyEffectTickThisTick(int duration, int amplifier) {
            return duration % 40 == 0;
        }

        @Override
        public boolean applyEffectTick(LivingEntity entity, int amplifier) {
            entity.heal(1 + amplifier);
            return true;
        }
    }

    public static final Holder<MobEffect> CRYSTAL_SIGHT = Registry.registerForHolder(BuiltInRegistries.MOB_EFFECT, ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "crystal_sight"), new CrystalSightEffect());
    public static final Holder<Potion> CRYSTAL_SIGHT_POTION = Registry.registerForHolder(BuiltInRegistries.POTION, ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "crystal_sight"),
        new Potion("crystal_sight", new MobEffectInstance(CRYSTAL_SIGHT, 3600)));

    private EffectsExample() {}

    public static void register() {
        FabricBrewingRecipeRegistryBuilder.BUILD.register(builder -> builder.addMix(Potions.AWKWARD, ModMain.SKY_CRYSTAL, CRYSTAL_SIGHT_POTION));
        FuelRegistry.INSTANCE.add(ModMain.SKY_CRYSTAL, 1600);
    }
}
