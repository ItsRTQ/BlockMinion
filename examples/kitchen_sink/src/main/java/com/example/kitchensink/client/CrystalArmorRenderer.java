package com.example.kitchensink.client;

import com.example.kitchensink.ModMain;
import com.example.kitchensink.gear.CrystalArmorItem;
import net.minecraft.resources.ResourceLocation;
import software.bernie.geckolib.model.DefaultedItemGeoModel;
import software.bernie.geckolib.renderer.GeoArmorRenderer;

public class CrystalArmorRenderer extends GeoArmorRenderer<CrystalArmorItem> {
    public CrystalArmorRenderer() {
        super(new DefaultedItemGeoModel<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "armor/crystal")));
    }
}
