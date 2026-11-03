"""Generated Fabric GameTests: one test per kind of generated content, run headless by `craftctl gametest`
(`gradlew runGametest`). Custom features add their own methods to the same class (coder `gametest` skill)."""
from __future__ import annotations
from .spec import Spec
from .gear import gear_item_ids


def gametests_java(spec: Spec) -> str:
    mod = spec.mod_id
    items = [f.identifier for f in spec.features if f.kind == "item"] + gear_item_ids(spec)
    blocks = [f.identifier for f in spec.features if f.kind == "block"]
    for f in spec.features:
        blocks += [f"{f.identifier}_{v}" for v in f.variants]
    L = [f"package {spec.package}.gametest;", "",
         f"import {spec.package}.ModMain;",
         "import net.fabricmc.fabric.api.gametest.v1.FabricGameTest;",
         "import net.minecraft.core.BlockPos;", "import net.minecraft.core.registries.BuiltInRegistries;",
         "import net.minecraft.gametest.framework.GameTest;", "import net.minecraft.gametest.framework.GameTestHelper;",
         "import net.minecraft.resources.ResourceLocation;", "import net.minecraft.world.item.ItemStack;",
         "import net.minecraft.world.level.block.Block;", "",
         "/**", " * Generated GameTests. Run: craftctl gametest <project> (or ./gradlew runGametest). Add one test per acceptance", " * criterion of custom features here (see the gametest skill). Keep @GameTest methods public and fast.", " */",
         "public class ModGameTests implements FabricGameTest {",
         f'    private static ResourceLocation id(String path) {{ return ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, path); }}', ""]
    if items:
        L += ["    @GameTest(template = EMPTY_STRUCTURE)", "    public void itemsAreRegistered(GameTestHelper helper) {"]
        for i in items:
            L.append(f'        helper.assertTrue(BuiltInRegistries.ITEM.containsKey(id("{i}")), "item {i} is registered");')
        L += ["        helper.succeed();", "    }", ""]
    if blocks:
        L += ["    @GameTest(template = EMPTY_STRUCTURE)", "    public void blocksPlaceAndStay(GameTestHelper helper) {", "        int i = 0;"]
        for b in blocks:
            L += [f'        Block b{b} = BuiltInRegistries.BLOCK.get(id("{b}"));',
                  f'        helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id("{b}")), "block {b} is registered");',
                  f"        helper.setBlock(new BlockPos(1 + (i % 6), 1, 1 + (i / 6)), b{b}); helper.assertBlockPresent(b{b}, new BlockPos(1 + (i % 6), 1, 1 + (i / 6))); i++;"]
        L += ["        helper.succeed();", "    }", ""]
    if spec.recipes:
        L += ["    @GameTest(template = EMPTY_STRUCTURE)", "    public void recipesExist(GameTestHelper helper) {"]
        for r in spec.recipes:
            L.append(f'        helper.assertTrue(helper.getLevel().getRecipeManager().byKey(id("{r.id}")).isPresent(), "recipe {r.id} loads");')
        L += ["        helper.succeed();", "    }", ""]
    if spec.mobs:
        L += ["    @GameTest(template = EMPTY_STRUCTURE)", "    public void mobsSpawn(GameTestHelper helper) {"]
        for m in spec.mobs:
            L += [f"        helper.spawn(ModMain.{m.identifier.upper()}, new BlockPos(2, 2, 2));", f"        helper.assertEntityPresent(ModMain.{m.identifier.upper()});"]
        L += ["        helper.succeed();", "    }", ""]
    if spec.foods:
        L += ["    @GameTest(template = EMPTY_STRUCTURE)", "    public void foodsAreEdible(GameTestHelper helper) {"]
        for f in spec.foods:
            L.append(f'        helper.assertTrue(new ItemStack(ModMain.{f.identifier.upper()}).has(net.minecraft.core.component.DataComponents.FOOD), "{f.identifier} has food properties");')
        L += ["        helper.succeed();", "    }", ""]
    if spec.structures or spec.biomes or spec.dimensions:
        L += ["    @GameTest(template = EMPTY_STRUCTURE)", "    public void worldgenIsRegistered(GameTestHelper helper) {",
              "        var registries = helper.getLevel().registryAccess();"]
        for st in spec.structures:
            L.append(f'        helper.assertTrue(registries.registryOrThrow(net.minecraft.core.registries.Registries.STRUCTURE).containsKey(id("{st.identifier}")), "structure {st.identifier} loaded");')
            L.append(f'        helper.assertTrue(registries.registryOrThrow(net.minecraft.core.registries.Registries.STRUCTURE_SET).containsKey(id("{st.identifier}")), "structure set {st.identifier} loaded");')
        for b in spec.biomes:
            L.append(f'        helper.assertTrue(registries.registryOrThrow(net.minecraft.core.registries.Registries.BIOME).containsKey(id("{b.identifier}")), "biome {b.identifier} loaded");')
        for d in spec.dimensions:
            L.append(f'        helper.assertTrue(helper.getLevel().getServer().getLevel(net.minecraft.resources.ResourceKey.create(net.minecraft.core.registries.Registries.DIMENSION, id("{d.identifier}"))) != null, "dimension {d.identifier} exists");')
        L += ["        helper.succeed();", "    }", ""]
    L += ["    @GameTest(template = EMPTY_STRUCTURE)", "    public void modIsLoaded(GameTestHelper helper) {",
          '        helper.assertTrue(net.fabricmc.loader.api.FabricLoader.getInstance().isModLoaded(ModMain.MOD_ID), "mod is loaded");', "        helper.succeed();", "    }", "}", ""]
    return "\n".join(L)
