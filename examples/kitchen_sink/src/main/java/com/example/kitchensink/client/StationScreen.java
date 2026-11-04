package com.example.kitchensink.client;

import com.example.kitchensink.StationMenu;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.player.Inventory;

/** Compiled reference for the `gui` skill, pattern 2: the client screen. */
public class StationScreen extends AbstractContainerScreen<StationMenu> {
    private static final ResourceLocation BG = ResourceLocation.withDefaultNamespace("textures/gui/container/dispenser.png");

    public StationScreen(StationMenu menu, Inventory inv, Component title) {
        super(menu, inv, title);
    }

    @Override
    protected void renderBg(GuiGraphics g, float delta, int mouseX, int mouseY) {
        g.blit(BG, leftPos, topPos, 0, 0, imageWidth, imageHeight);
    }

    @Override
    public void render(GuiGraphics g, int mouseX, int mouseY, float delta) {
        super.render(g, mouseX, mouseY, delta);
        renderTooltip(g, mouseX, mouseY);
    }
}
