package com.example.kitchensink.client;

import com.example.kitchensink.ModMain;
import com.example.kitchensink.entity.SkyCritterEntity;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.resources.ResourceLocation;
import software.bernie.geckolib.model.DefaultedEntityGeoModel;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

public class SkyCritterRenderer extends GeoEntityRenderer<SkyCritterEntity> {
    public SkyCritterRenderer(EntityRendererProvider.Context context) {
        super(context, new DefaultedEntityGeoModel<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "sky_critter")));
    }
}
