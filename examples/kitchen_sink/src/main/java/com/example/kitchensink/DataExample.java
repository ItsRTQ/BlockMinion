package com.example.kitchensink;

import com.mojang.serialization.Codec;
import net.fabricmc.fabric.api.attachment.v1.AttachmentRegistry;
import net.fabricmc.fabric.api.attachment.v1.AttachmentType;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.core.Registry;
import net.minecraft.core.component.DataComponentType;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;

/** Compiled reference for the `data` skill: a mana system (player attachment, item component, world data) synced to the HUD. */
public final class DataExample {
    public static final AttachmentType<Integer> MANA = AttachmentRegistry.<Integer>builder()
        .persistent(Codec.INT)
        .copyOnDeath()
        .initializer(() -> 0)
        .buildAndRegister(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "mana"));

    public static final DataComponentType<Integer> CHARGE = Registry.register(BuiltInRegistries.DATA_COMPONENT_TYPE, ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "charge"),
        DataComponentType.<Integer>builder().persistent(Codec.INT).networkSynchronized(ByteBufCodecs.VAR_INT).build());

    private DataExample() {}

    public static int getCharge(ItemStack stack) {
        return stack.getOrDefault(CHARGE, 0);
    }

    public static void register() {
        PayloadTypeRegistry.playS2C().register(ManaSyncPayload.TYPE, ManaSyncPayload.CODEC);
        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> sync(handler.getPlayer()));
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (server.getTickCount() % 40 != 0) return;                 // regenerate 1 mana every 2 s
            for (ServerPlayer p : server.getPlayerList().getPlayers()) {
                int mana = p.getAttachedOrCreate(MANA);
                if (mana < ModMain.CONFIG.manaMax) {
                    p.setAttached(MANA, mana + 1);
                    sync(p);
                }
            }
        });
    }

    public static boolean spend(ServerPlayer p, int amount) {
        int mana = p.getAttachedOrCreate(MANA);
        if (mana < amount) return false;
        p.setAttached(MANA, mana - amount);
        sync(p);
        ModSaveData data = ModSaveData.get(p.server);
        data.bossesSlain++;                                              // example of world data mutation
        data.setDirty();
        return true;
    }

    private static void sync(ServerPlayer p) {
        ServerPlayNetworking.send(p, new ManaSyncPayload(p.getAttachedOrCreate(MANA)));
    }
}
