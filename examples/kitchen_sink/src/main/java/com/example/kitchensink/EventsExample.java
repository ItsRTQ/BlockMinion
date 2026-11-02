package com.example.kitchensink;

import net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.event.player.PlayerBlockBreakEvents;
import net.fabricmc.fabric.api.event.player.UseItemCallback;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.monster.Zombie;
import net.minecraft.world.item.ItemStack;

/** Compiled reference for the `events` skill. */
public final class EventsExample {
    private EventsExample() {}

    public static void register() {
        UseItemCallback.EVENT.register((player, level, hand) -> {
            ItemStack stack = player.getItemInHand(hand);
            if (stack.is(ModMain.SKY_CRYSTAL) && !level.isClientSide) {
                player.addEffect(new MobEffectInstance(BuiltInRegistries.MOB_EFFECT.getHolder(ResourceLocation.parse("minecraft:speed")).orElseThrow(), 200, 0));
                stack.shrink(1);
                return InteractionResultHolder.success(stack);
            }
            return InteractionResultHolder.pass(stack);
        });
        PlayerBlockBreakEvents.AFTER.register((level, player, pos, state, blockEntity) -> {
            if (state.is(ModMain.CRYSTAL_ORE)) level.playSound(null, pos, ModMain.CRYSTAL_CHIME_SOUND, SoundSource.BLOCKS, 1f, 1f);
        });
        PlayerBlockBreakEvents.BEFORE.register((level, player, pos, state, blockEntity) -> !state.is(ModMain.CRYSTAL_STATION) || player.isCreative());
        ServerLivingEntityEvents.AFTER_DEATH.register((entity, source) -> {
            if (entity instanceof Zombie && source.getEntity() instanceof ServerPlayer p) p.giveExperiencePoints(5);
        });
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (server.getTickCount() % 1200 == 0) ModMain.LOGGER.debug("kitchen_sink: one minute of server ticks");
        });
        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) ->
            handler.getPlayer().sendSystemMessage(Component.literal("Kitchen Sink loaded — press B to open the example menu.")));
    }
}
