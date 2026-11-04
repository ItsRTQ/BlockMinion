---
name: client-ui
description: Keybinds, HUD overlays and client→server actions on Fabric 1.21.1 (Mojang mappings), including the networking they need. Use for hotkeys, bars/overlays, minimaps (basic), and "press key → do something on the server".
---

# Keybinds, HUD, and client→server networking (1.21.1, Mojmap)

All of this is CLIENT code: it lives in the `client` package and is registered from `ModClient.onInitializeClient()`.
Anything that changes the world must be sent to the server as a packet. Compiled reference:
`examples/kitchen_sink/src/main/java/com/example/kitchensink/client/ClientUiExample.java` and `.../BackpackKeyPayload.java`.

## Keybind
```java
public static final KeyMapping OPEN_KEY = KeyBindingHelper.registerKeyBinding(new KeyMapping("key.<mod>.open", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_B, "category.<mod>"));
ClientTickEvents.END_CLIENT_TICK.register(client -> { while (OPEN_KEY.consumeClick()) ClientPlayNetworking.send(new OpenPayload()); });
```
Lang: `key.<mod>.open`, `category.<mod>`. Imports: `net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper`, `com.mojang.blaze3d.platform.InputConstants`, `org.lwjgl.glfw.GLFW`, `net.minecraft.client.KeyMapping`.

## Client → server packet (1.20.5+ payload API)
```java
public record OpenPayload() implements CustomPacketPayload {
    public static final CustomPacketPayload.Type<OpenPayload> TYPE = new CustomPacketPayload.Type<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "open"));
    public static final StreamCodec<RegistryFriendlyByteBuf, OpenPayload> CODEC = StreamCodec.unit(new OpenPayload());
    @Override public Type<? extends CustomPacketPayload> type() { return TYPE; }
}
// common init (ModMain): PayloadTypeRegistry.playC2S().register(OpenPayload.TYPE, OpenPayload.CODEC);
// server handler (ModMain): ServerPlayNetworking.registerGlobalReceiver(OpenPayload.TYPE, (payload, context) -> { ServerPlayer p = context.player(); context.server().execute(() -> { /* open menu, give item… */ }); });
```
Payload with data: `StreamCodec.composite(ByteBufCodecs.VAR_INT, OpenPayload::slot, OpenPayload::new)`. Server → client: `PayloadTypeRegistry.playS2C()`, `ServerPlayNetworking.send(player, payload)`, `ClientPlayNetworking.registerGlobalReceiver` in the client init.
Packages: `net.minecraft.network.protocol.common.custom.CustomPacketPayload`, `net.minecraft.network.codec.StreamCodec`, `net.minecraft.network.RegistryFriendlyByteBuf`, `net.fabricmc.fabric.api.networking.v1.*`.

## Server → client with data (sync a value to the HUD)
```java
public record ManaSyncPayload(int mana) implements CustomPacketPayload {
    public static final Type<ManaSyncPayload> TYPE = new Type<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "mana_sync"));
    public static final StreamCodec<RegistryFriendlyByteBuf, ManaSyncPayload> CODEC = StreamCodec.composite(ByteBufCodecs.VAR_INT, ManaSyncPayload::mana, ManaSyncPayload::new);
    @Override public Type<? extends CustomPacketPayload> type() { return TYPE; }
}
// ModMain: PayloadTypeRegistry.playS2C().register(ManaSyncPayload.TYPE, ManaSyncPayload.CODEC);
// server, when the value changes: ServerPlayNetworking.send(serverPlayer, new ManaSyncPayload(mana));
// ModClient: ClientPlayNetworking.registerGlobalReceiver(ManaSyncPayload.TYPE, (payload, context) -> context.client().execute(() -> ClientState.mana = payload.mana()));
```
`ClientState` is a plain class with static fields in the client package; the HUD reads it. Send on join and on every change (not every tick).

## HUD overlay
```java
HudRenderCallback.EVENT.register((GuiGraphics g, DeltaTracker delta) -> {
    Minecraft mc = Minecraft.getInstance(); if (mc.player == null || mc.options.hideGui) return;
    int w = mc.getWindow().getGuiScaledWidth();
    g.fill(w - 110, 10, w - 10, 20, 0xAA000000);                       // background
    g.fill(w - 109, 11, w - 109 + (int) (98 * ratio), 19, 0xFF4FD1FF); // bar
    g.drawString(mc.font, "Mana", w - 108, 0, 0xFFFFFF);
});
```
`net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback`, `net.minecraft.client.gui.GuiGraphics`, `net.minecraft.client.DeltaTracker`. Textures: `g.blit(ResourceLocation, x, y, u, v, w, h)`.
A real minimap (reading chunks, rendering a top-down map) is a large feature: start with a HUD that shows coordinates / biome name and grow from there.

## Rules
- Client classes (`Minecraft`, `GuiGraphics`, `KeyMapping`) only in `client/`; referencing them from `ModMain` crashes dedicated servers.
- Validate on the server everything a packet asks for (distance, ownership); never trust the client.
- `context.server().execute(...)` to touch the world from a packet handler.
