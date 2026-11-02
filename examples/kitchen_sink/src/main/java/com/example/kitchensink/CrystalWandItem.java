package com.example.kitchensink;

import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.level.Level;

import java.util.List;

/** Compiled reference for the `items` skill: right-click action, cooldown, durability, tooltip; spends mana from the `data` example. */
public class CrystalWandItem extends Item {
    public CrystalWandItem(Properties properties) {
        super(properties.durability(64));
    }

    @Override
    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (!level.isClientSide) {
            if (player instanceof ServerPlayer sp && !DataExample.spend(sp, 5)) {
                sp.displayClientMessage(Component.literal("Not enough mana").withStyle(ChatFormatting.RED), true);
                return InteractionResultHolder.fail(stack);
            }
            CrystalBoltEntity bolt = new CrystalBoltEntity(level, player);
            bolt.setItem(new ItemStack(ModMain.SKY_CRYSTAL));
            bolt.shootFromRotation(player, player.getXRot(), player.getYRot(), 0.0F, 1.5F, 1.0F);
            level.addFreshEntity(bolt);
            stack.hurtAndBreak(1, player, LivingEntity.getSlotForHand(hand));
            player.getCooldowns().addCooldown(this, 20);
        }
        player.playSound(SoundEvents.ENDER_PEARL_THROW, 0.5F, 1.2F);
        return InteractionResultHolder.sidedSuccess(stack, level.isClientSide);
    }

    @Override
    public void appendHoverText(ItemStack stack, TooltipContext context, List<Component> tooltip, TooltipFlag flag) {
        tooltip.add(Component.translatable("item.kitchen_sink.crystal_wand.tooltip").withStyle(ChatFormatting.AQUA));
    }
}
