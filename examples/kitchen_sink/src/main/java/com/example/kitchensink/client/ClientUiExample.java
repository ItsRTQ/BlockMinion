package com.example.kitchensink.client;

import com.example.kitchensink.ManaSyncPayload;
import com.example.kitchensink.ModMain;
import com.example.kitchensink.OpenPayload;
import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.MenuScreens;
import org.lwjgl.glfw.GLFW;

/** Compiled reference for the `client-ui` skill: keybind → packet, HUD overlay, screen registration. */
public final class ClientUiExample {
    public static final KeyMapping OPEN_KEY = KeyBindingHelper.registerKeyBinding(new KeyMapping("key." + ModMain.MOD_ID + ".open", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_B, "category." + ModMain.MOD_ID));
    private ClientUiExample() {}

    public static void register() {
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            while (OPEN_KEY.consumeClick()) ClientPlayNetworking.send(new OpenPayload());
        });
        HudRenderCallback.EVENT.register((g, delta) -> {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.options.hideGui) return;
            int w = mc.getWindow().getGuiScaledWidth();
            float ratio = Math.min(1f, ClientState.mana / 100f);
            g.fill(w - 110, 10, w - 10, 20, 0xAA000000);
            g.fill(w - 109, 11, w - 109 + (int) (98 * ratio), 19, 0xFF4FD1FF);
            g.drawString(mc.font, "Mana " + ClientState.mana, w - 108, 0, 0xFFFFFF);
        });
        MenuScreens.register(ModMain.STATION_MENU, StationScreen::new);
        ClientPlayNetworking.registerGlobalReceiver(ManaSyncPayload.TYPE, (payload, context) -> context.client().execute(() -> ClientState.mana = payload.mana()));
    }
}
