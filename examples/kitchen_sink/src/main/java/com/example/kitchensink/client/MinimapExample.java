package com.example.kitchensink.client;

import com.example.kitchensink.ModMain;
import com.mojang.blaze3d.platform.NativeImage;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.texture.DynamicTexture;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.levelgen.Heightmap;

/** Compiled reference for the `minimap` skill: samples the loaded world around the player into a texture and draws it. */
public final class MinimapExample {
    private static final int SIZE = 64;
    private static final int SCALE = 2;
    private static final ResourceLocation TEXTURE_ID = ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "minimap");
    private static DynamicTexture texture;
    private static int tick;

    private MinimapExample() {}

    public static void register() {
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            if (client.level == null || client.player == null) return;
            if (texture == null) {
                texture = new DynamicTexture(SIZE, SIZE, false);
                client.getTextureManager().register(TEXTURE_ID, texture);
            }
            if (++tick % 10 == 0) sample(client);
        });
        HudRenderCallback.EVENT.register((g, delta) -> {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.options.hideGui || texture == null) return;
            int w = SIZE * SCALE, x = mc.getWindow().getGuiScaledWidth() - w - 8, y = 40;
            g.fill(x - 2, y - 2, x + w + 2, y + w + 2, 0xAA000000);
            g.blit(TEXTURE_ID, x, y, w, w, 0.0F, 0.0F, SIZE, SIZE, SIZE, SIZE);
            int cx = x + w / 2, cy = y + w / 2;
            g.fill(cx - 1, cy - 1, cx + 2, cy + 2, 0xFFFFFFFF);
        });
    }

    private static void sample(Minecraft mc) {
        NativeImage img = texture.getPixels();
        if (img == null) return;
        BlockPos center = mc.player.blockPosition();
        for (int dz = 0; dz < SIZE; dz++) {
            for (int dx = 0; dx < SIZE; dx++) {
                int wx = center.getX() - SIZE / 2 + dx, wz = center.getZ() - SIZE / 2 + dz;
                if (!mc.level.hasChunk(wx >> 4, wz >> 4)) { img.setPixelRGBA(dx, dz, 0xFF000000); continue; }
                int top = mc.level.getHeight(Heightmap.Types.MOTION_BLOCKING, wx, wz) - 1;
                BlockPos p = new BlockPos(wx, top, wz);
                int colour = mc.level.getBlockState(p).getMapColor(mc.level, p).col;
                int shade = Math.max(60, Math.min(255, 160 + (top - center.getY()) * 3));
                int r = (colour >> 16 & 255) * shade / 255, gch = (colour >> 8 & 255) * shade / 255, b = (colour & 255) * shade / 255;
                img.setPixelRGBA(dx, dz, 0xFF000000 | (b << 16) | (gch << 8) | r);
            }
        }
        texture.upload();
    }
}
