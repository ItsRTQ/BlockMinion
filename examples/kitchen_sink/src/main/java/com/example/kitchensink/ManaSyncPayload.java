package com.example.kitchensink;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

/** Server → client: the player's current mana (client-ui skill, payload with data). */
public record ManaSyncPayload(int mana) implements CustomPacketPayload {
    public static final CustomPacketPayload.Type<ManaSyncPayload> TYPE = new CustomPacketPayload.Type<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "mana_sync"));
    public static final StreamCodec<RegistryFriendlyByteBuf, ManaSyncPayload> CODEC = StreamCodec.composite(ByteBufCodecs.VAR_INT, ManaSyncPayload::mana, ManaSyncPayload::new);

    @Override
    public Type<? extends CustomPacketPayload> type() {
        return TYPE;
    }
}
