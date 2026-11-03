package com.example.kitchensink;

import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.levelgen.Heightmap;

/** Right-click: travel to crystal_realm (and back to the overworld from there). */
public class CrystalRealmKeyItem extends Item {
    public static final ResourceKey<Level> DIMENSION = ResourceKey.create(Registries.DIMENSION, ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "crystal_realm"));
    public CrystalRealmKeyItem(Properties properties) { super(properties.stacksTo(1)); }

    @Override
    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (player instanceof ServerPlayer sp && !level.isClientSide) {
            ResourceKey<Level> targetKey = level.dimension().equals(DIMENSION) ? Level.OVERWORLD : DIMENSION;
            ServerLevel target = sp.server.getLevel(targetKey);
            if (target == null) return InteractionResultHolder.fail(stack);
            int x = sp.getBlockX(), z = sp.getBlockZ();
            int y = target.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x, z);
            sp.teleportTo(target, x + 0.5, Math.max(y, target.getMinBuildHeight() + 2), z + 0.5, sp.getYRot(), sp.getXRot());
            player.getCooldowns().addCooldown(this, 40);
        }
        return InteractionResultHolder.sidedSuccess(stack, level.isClientSide);
    }
}
