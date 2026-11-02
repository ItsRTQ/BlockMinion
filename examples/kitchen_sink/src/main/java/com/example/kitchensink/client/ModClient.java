package com.example.kitchensink.client;

import com.example.kitchensink.ModMain;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.rendering.v1.EntityRendererRegistry;

public class ModClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        ClientUiExample.register();
        EntityRendererRegistry.register(ModMain.SKY_CRITTER, SkyCritterRenderer::new);
    }
}
