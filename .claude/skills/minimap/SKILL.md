---
name: minimap
description: A real top-down minimap HUD on Fabric 1.21.1 (Mojang mappings): sampling nearby blocks/biomes into a texture, drawing it with GuiGraphics, caching, player marker, zoom keybind. Builds on the client-ui skill.
---

# Minimap (client-side, no server data needed)

A minimap is a HUD overlay that samples the loaded chunks around the player into a small image every N ticks and blits it.
Everything runs on the client: `HudRenderCallback` draws, `ClientTickEvents` refreshes. Compiled reference:
`examples/kitchen_sink/.../client/MinimapExample.java` (64×64 blocks, refreshed every 10 ticks).

## Core loop
```java
public final class MinimapExample {
    private static final int SIZE = 64;                   // blocks per side
    private static final int SCALE = 2;                   // screen pixels per block
    private static final DynamicTexture TEXTURE = new DynamicTexture(SIZE, SIZE, false);
    private static final ResourceLocation TEXTURE_ID = ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "minimap");
    private static int tick;

    public static void register() {
        Minecraft.getInstance().getTextureManager().register(TEXTURE_ID, TEXTURE);
        ClientTickEvents.END_CLIENT_TICK.register(client -> { if (client.level != null && client.player != null && ++tick % 10 == 0) sample(client); });
        HudRenderCallback.EVENT.register((g, delta) -> {
            Minecraft mc = Minecraft.getInstance(); if (mc.player == null || mc.options.hideGui) return;
            int x = mc.getWindow().getGuiScaledWidth() - SIZE * SCALE - 8, y = 8;
            g.fill(x - 2, y - 2, x + SIZE * SCALE + 2, y + SIZE * SCALE + 2, 0xAA000000);
            g.blit(TEXTURE_ID, x, y, 0, 0, SIZE * SCALE, SIZE * SCALE, SIZE, SIZE);   // draw the whole texture scaled... see blit overloads
            int cx = x + SIZE * SCALE / 2, cy = y + SIZE * SCALE / 2;
            g.fill(cx - 1, cy - 1, cx + 2, cy + 2, 0xFFFFFFFF);                           // player marker
        });
    }

    private static void sample(Minecraft mc) {
        NativeImage img = TEXTURE.getPixels(); if (img == null) return;
        BlockPos center = mc.player.blockPosition();
        for (int dz = 0; dz < SIZE; dz++) for (int dx = 0; dx < SIZE; dx++) {
            int wx = center.getX() - SIZE / 2 + dx, wz = center.getZ() - SIZE / 2 + dz;
            int top = mc.level.getHeight(Heightmap.Types.MOTION_BLOCKING, wx, wz) - 1;
            BlockPos p = new BlockPos(wx, top, wz);
            int colour = mc.level.getBlockState(p).getMapColor(mc.level, p).col;          // MapColor: same palette as vanilla maps
            int shade = Math.max(0, Math.min(255, 160 + (top - center.getY()) * 3));       // lighter when higher than the player
            int r = (colour >> 16 & 255) * shade / 255, gch = (colour >> 8 & 255) * shade / 255, b = (colour & 255) * shade / 255;
            img.setPixelRGBA(dx, dz, 0xFF000000 | (b << 16) | (gch << 8) | r);           // NativeImage is ABGR
        }
        TEXTURE.upload();
    }
}
```
`com.mojang.blaze3d.platform.NativeImage`, `net.minecraft.client.renderer.texture.DynamicTexture`, `net.minecraft.world.level.levelgen.Heightmap`.
`getHeight` only works for loaded chunks: check `mc.level.hasChunk(wx >> 4, wz >> 4)` first (unloaded → leave black).

## Making it good
- **Cost**: 64×64 = 4096 samples every 10 ticks is cheap; 256×256 every tick is not. Sample in rings or only rows that changed when the player moves.
- **Rotation**: rotate the blit by the player's yaw with `g.pose().pushPose(); g.pose().rotateAround(...)` or keep north-up (simpler, what most players expect).
- **Zoom**: a keybind (`client-ui` skill) that cycles SIZE 32/64/128 and recreates the DynamicTexture.
- **Markers**: other players (`mc.level.players()`), your mobs (`mc.level.getEntitiesOfClass(...)` within range), a waypoint list saved in the config (`polish` skill).
- **Biome tint**: `mc.level.getBiome(p).value().getFoliageColor()` for a biome-coloured variant.
- Never block the render thread with world queries outside loaded chunks; never touch the server.
