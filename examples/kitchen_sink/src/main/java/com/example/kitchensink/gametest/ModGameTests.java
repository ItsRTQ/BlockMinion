package com.example.kitchensink.gametest;

import com.example.kitchensink.ModMain;
import net.fabricmc.fabric.api.gametest.v1.FabricGameTest;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;

/**
 * Generated GameTests. Run: craftctl gametest <project> (or ./gradlew runGametest). Add one test per acceptance
 * criterion of custom features here (see the gametest skill). Keep @GameTest methods public and fast.
 */
public class ModGameTests implements FabricGameTest {
    private static ResourceLocation id(String path) { return ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, path); }

    @GameTest(template = EMPTY_STRUCTURE)
    public void itemsAreRegistered(GameTestHelper helper) {
        helper.assertTrue(BuiltInRegistries.ITEM.containsKey(id("sky_crystal")), "item sky_crystal is registered");
        helper.assertTrue(BuiltInRegistries.ITEM.containsKey(id("crystal_sword")), "item crystal_sword is registered");
        helper.assertTrue(BuiltInRegistries.ITEM.containsKey(id("crystal_helmet")), "item crystal_helmet is registered");
        helper.assertTrue(BuiltInRegistries.ITEM.containsKey(id("crystal_chestplate")), "item crystal_chestplate is registered");
        helper.assertTrue(BuiltInRegistries.ITEM.containsKey(id("crystal_leggings")), "item crystal_leggings is registered");
        helper.assertTrue(BuiltInRegistries.ITEM.containsKey(id("crystal_boots")), "item crystal_boots is registered");
        helper.succeed();
    }

    @GameTest(template = EMPTY_STRUCTURE)
    public void blocksPlaceAndStay(GameTestHelper helper) {
        int i = 0;
        Block bcrystal_ore = BuiltInRegistries.BLOCK.get(id("crystal_ore"));
        helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id("crystal_ore")), "block crystal_ore is registered");
        helper.setBlock(new BlockPos(1 + (i % 6), 1, 1 + (i / 6)), bcrystal_ore); helper.assertBlockPresent(bcrystal_ore, new BlockPos(1 + (i % 6), 1, 1 + (i / 6))); i++;
        Block bcrystal_station = BuiltInRegistries.BLOCK.get(id("crystal_station"));
        helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id("crystal_station")), "block crystal_station is registered");
        helper.setBlock(new BlockPos(1 + (i % 6), 1, 1 + (i / 6)), bcrystal_station); helper.assertBlockPresent(bcrystal_station, new BlockPos(1 + (i % 6), 1, 1 + (i / 6))); i++;
        Block bcrystal_bricks = BuiltInRegistries.BLOCK.get(id("crystal_bricks"));
        helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id("crystal_bricks")), "block crystal_bricks is registered");
        helper.setBlock(new BlockPos(1 + (i % 6), 1, 1 + (i / 6)), bcrystal_bricks); helper.assertBlockPresent(bcrystal_bricks, new BlockPos(1 + (i % 6), 1, 1 + (i / 6))); i++;
        Block bcrystal_bricks_stairs = BuiltInRegistries.BLOCK.get(id("crystal_bricks_stairs"));
        helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id("crystal_bricks_stairs")), "block crystal_bricks_stairs is registered");
        helper.setBlock(new BlockPos(1 + (i % 6), 1, 1 + (i / 6)), bcrystal_bricks_stairs); helper.assertBlockPresent(bcrystal_bricks_stairs, new BlockPos(1 + (i % 6), 1, 1 + (i / 6))); i++;
        Block bcrystal_bricks_slab = BuiltInRegistries.BLOCK.get(id("crystal_bricks_slab"));
        helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id("crystal_bricks_slab")), "block crystal_bricks_slab is registered");
        helper.setBlock(new BlockPos(1 + (i % 6), 1, 1 + (i / 6)), bcrystal_bricks_slab); helper.assertBlockPresent(bcrystal_bricks_slab, new BlockPos(1 + (i % 6), 1, 1 + (i / 6))); i++;
        Block bcrystal_bricks_fence = BuiltInRegistries.BLOCK.get(id("crystal_bricks_fence"));
        helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id("crystal_bricks_fence")), "block crystal_bricks_fence is registered");
        helper.setBlock(new BlockPos(1 + (i % 6), 1, 1 + (i / 6)), bcrystal_bricks_fence); helper.assertBlockPresent(bcrystal_bricks_fence, new BlockPos(1 + (i % 6), 1, 1 + (i / 6))); i++;
        Block bcrystal_bricks_wall = BuiltInRegistries.BLOCK.get(id("crystal_bricks_wall"));
        helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id("crystal_bricks_wall")), "block crystal_bricks_wall is registered");
        helper.setBlock(new BlockPos(1 + (i % 6), 1, 1 + (i / 6)), bcrystal_bricks_wall); helper.assertBlockPresent(bcrystal_bricks_wall, new BlockPos(1 + (i % 6), 1, 1 + (i / 6))); i++;
        helper.succeed();
    }

    @GameTest(template = EMPTY_STRUCTURE)
    public void mobsSpawn(GameTestHelper helper) {
        helper.spawn(ModMain.SKY_CRITTER, new BlockPos(2, 2, 2));
        helper.assertEntityPresent(ModMain.SKY_CRITTER);
        helper.succeed();
    }

    @GameTest(template = EMPTY_STRUCTURE)
    public void worldgenIsRegistered(GameTestHelper helper) {
        var registries = helper.getLevel().registryAccess();
        helper.assertTrue(registries.registryOrThrow(net.minecraft.core.registries.Registries.STRUCTURE).containsKey(id("crystal_shrine")), "structure crystal_shrine loaded");
        helper.assertTrue(registries.registryOrThrow(net.minecraft.core.registries.Registries.STRUCTURE_SET).containsKey(id("crystal_shrine")), "structure set crystal_shrine loaded");
        helper.assertTrue(registries.registryOrThrow(net.minecraft.core.registries.Registries.BIOME).containsKey(id("crystal_fields")), "biome crystal_fields loaded");
        helper.assertTrue(registries.registryOrThrow(net.minecraft.core.registries.Registries.DIMENSION_TYPE).containsKey(id("crystal_realm")), "dimension type crystal_realm loaded");
        helper.succeed();
    }

    @GameTest(template = EMPTY_STRUCTURE)
    public void modIsLoaded(GameTestHelper helper) {
        helper.assertTrue(net.fabricmc.loader.api.FabricLoader.getInstance().isModLoaded(ModMain.MOD_ID), "mod is loaded");
        helper.succeed();
    }
}
