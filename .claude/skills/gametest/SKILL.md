---
name: gametest
description: Write Fabric GameTests (1.21.1, Mojang mappings) for the features you implement — one @GameTest per acceptance criterion in the project's gametest/ModGameTests class. Required for every FEATURE/CHANGE task where the behaviour can be exercised server-side.
---

# GameTests (Fabric API gametest v1, 1.21.1 Mojmap)

The project already has `src/main/java/<pkg>/gametest/ModGameTests.java` (generated; registered as the `fabric-gametest`
entrypoint) and a Loom run `runGametest` that boots a headless test server and runs every `@GameTest` method, writing
`build/gametest/junit.xml`. The controller runs it with `craftctl gametest` (approval-gated); failures open a repair task
with the failing test names. **Add your tests to that class** (or a new class in the same package, also listed in
`fabric.mod.json` under `"fabric-gametest"`).

```java
@GameTest(template = EMPTY_STRUCTURE)                       // 8x8x8 empty box; the helper's coordinates are relative to it
public void backpackOpensAndKeepsItems(GameTestHelper helper) {
    ServerPlayer player = helper.makeMockServerPlayerInLevel();       // a fake player standing in the test box
    ItemStack backpack = new ItemStack(ModMain.BACKPACK);
    player.setItemInHand(InteractionHand.MAIN_HAND, backpack);
    ModMain.BACKPACK.use(helper.getLevel(), player, InteractionHand.MAIN_HAND);
    helper.assertTrue(player.containerMenu instanceof ChestMenu, "right-click opened a chest-style menu");
    player.containerMenu.getSlot(0).set(new ItemStack(Items.DIAMOND));
    player.closeContainer();
    ItemContainerContents saved = backpack.getOrDefault(DataComponents.CONTAINER, ItemContainerContents.EMPTY);
    helper.assertTrue(saved.copyOne().is(Items.DIAMOND), "diamond persisted on the item");
    helper.succeed();
}

@GameTest(template = EMPTY_STRUCTURE, timeoutTicks = 200)   // for things that take ticks: use helper.runAfterDelay / succeedWhen
public void oreDropsRawWithIronPickaxe(GameTestHelper helper) {
    BlockPos pos = new BlockPos(2, 2, 2);
    helper.setBlock(pos, ModMain.CRYSTAL_ORE);
    ServerPlayer player = helper.makeMockServerPlayerInLevel();
    player.setItemInHand(InteractionHand.MAIN_HAND, new ItemStack(Items.IRON_PICKAXE));
    helper.getLevel().destroyBlock(helper.absolutePos(pos), true, player);
    helper.succeedWhen(() -> helper.assertItemEntityPresent(ModMain.SKY_CRYSTAL, pos, 2.0));
}
```
Helper API: `setBlock`, `assertBlockPresent`, `assertBlock(pos, predicate, msg)`, `spawn(EntityType, BlockPos)`, `assertEntityPresent`, `assertEntityData`,
`assertItemEntityPresent(item, pos, radius)`, `makeMockServerPlayerInLevel()`, `pressButton`, `pullLever`, `getLevel()`, `absolutePos`, `runAfterDelay(ticks, Runnable)`,
`succeedWhen(Runnable)`, `succeedIf`, `fail(msg)`, `succeed()`. Imports: `net.minecraft.gametest.framework.*`, `net.fabricmc.fabric.api.gametest.v1.FabricGameTest`.
Rules: every test ends with `succeed()`/`succeedWhen`; no client classes (the test server is headless); keep tests deterministic (no random drops without seeds — assert "at least one" instead of counts); one test per acceptance criterion, named after it.
Run locally: `./gradlew runGametest` (3–5 min; the first run downloads the server). Report the test names in `card.acceptance` mapping if you can.
