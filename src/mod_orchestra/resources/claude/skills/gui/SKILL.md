---
name: gui
description: Screens and inventories (screen handlers / menus) for Fabric 1.21.1 with Mojang mappings — backpacks, blocks with a GUI, custom crafting stations. Use whenever a feature opens a window, has slots, or shows synced numbers.
---

# GUIs on Fabric 1.21.1 (Mojang mappings)

Minecraft splits every GUI in two: the **menu** (`AbstractContainerMenu`, server + client, owns the slots and synced
ints) and the **screen** (`AbstractContainerScreen`, client only, draws it). Yarn calls them ScreenHandler/HandledScreen;
in Mojmap: `net.minecraft.world.inventory.AbstractContainerMenu`, `MenuType`, `Slot`, `SimpleContainer`,
`ContainerData`, `net.minecraft.client.gui.screens.inventory.AbstractContainerScreen`, `MenuScreens`.
Fabric API adds `net.fabricmc.fabric.api.screenhandler.v1.ExtendedScreenHandlerType` / `ExtendedScreenHandlerFactory` to
send opening data (a BlockPos, a hand) to the client.

## Pattern 1 — the 60-line backpack (reuse vanilla's chest menu, no screen class at all)
Any 9×N inventory can open as a vanilla chest UI. The item keeps its contents in the `CONTAINER` data component.

```java
public class BackpackItem extends Item {
    public static final int ROWS = 3;                      // 27 slots
    public BackpackItem(Properties p) { super(p.stacksTo(1)); }

    @Override
    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (!level.isClientSide) {
            SimpleContainer container = new SimpleContainer(9 * ROWS) {
                @Override public void setChanged() {       // write back to the item every time a slot changes
                    super.setChanged();
                    stack.set(DataComponents.CONTAINER, ItemContainerContents.fromItems(this.getItems()));
                }
            };
            ItemContainerContents contents = stack.getOrDefault(DataComponents.CONTAINER, ItemContainerContents.EMPTY);
            NonNullList<ItemStack> items = NonNullList.withSize(9 * ROWS, ItemStack.EMPTY);
            contents.copyInto(items);
            for (int i = 0; i < items.size(); i++) container.setItem(i, items.get(i));
            player.openMenu(new SimpleMenuProvider((syncId, inv, p) -> ChestMenu.threeRows(syncId, inv, container), stack.getHoverName()));
        }
        return InteractionResultHolder.sidedSuccess(stack, level.isClientSide);
    }
}
```
Imports: `net.minecraft.core.NonNullList`, `net.minecraft.core.component.DataComponents`, `net.minecraft.world.*` (`InteractionHand`,
`InteractionResultHolder`, `SimpleContainer`, `SimpleMenuProvider`), `net.minecraft.world.inventory.ChestMenu`,
`net.minecraft.world.item.component.ItemContainerContents`. `ChestMenu.sixRows` for 54. Register the item like any other.
Guard against putting a backpack inside itself if that matters (check `stack.getItem() instanceof BackpackItem` in a custom menu's slot `mayPlace`).

## Pattern 2 — a block with a GUI (block entity + menu + screen)
1. **Block entity** holding the inventory and implementing `MenuProvider`:
```java
public class StationBlockEntity extends BlockEntity implements MenuProvider {
    private final NonNullList<ItemStack> items = NonNullList.withSize(SIZE, ItemStack.EMPTY);
    public StationBlockEntity(BlockPos pos, BlockState state) { super(ModMain.STATION_BE, pos, state); }
    @Override public Component getDisplayName() { return Component.translatable("container.<mod>.station"); }
    @Override public AbstractContainerMenu createMenu(int syncId, Inventory inv, Player player) { return new StationMenu(syncId, inv, this); }
    @Override protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) { super.saveAdditional(tag, registries); ContainerHelper.saveAllItems(tag, items, registries); }
    @Override protected void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) { super.loadAdditional(tag, registries); ContainerHelper.loadAllItems(tag, items, registries); }
    public NonNullList<ItemStack> getItems() { return items; }
}
```
   Register: `BlockEntityType<StationBlockEntity> STATION_BE = Registry.register(BuiltInRegistries.BLOCK_ENTITY_TYPE, id("station"), BlockEntityType.Builder.of(StationBlockEntity::new, STATION_BLOCK).build());`
   The block extends `BaseEntityBlock` (override `newBlockEntity`, `getRenderShape` → `RenderShape.MODEL`, `codec()` via `simpleCodec(StationBlock::new)`) and opens the menu in
   `useWithoutItem(BlockState, Level, BlockPos, Player, BlockHitResult)`: `if (!level.isClientSide && level.getBlockEntity(pos) instanceof StationBlockEntity be) player.openMenu(be); return InteractionResult.sidedSuccess(level.isClientSide);`
2. **Menu** (server + client). The client constructor gets no block entity, so it builds a `SimpleContainer` of the same size:
```java
public class StationMenu extends AbstractContainerMenu {
    private final Container container;
    public StationMenu(int syncId, Inventory inv) { this(syncId, inv, new SimpleContainer(SIZE)); }               // client
    public StationMenu(int syncId, Inventory inv, Container container) {                                          // server
        super(ModMain.STATION_MENU, syncId);
        this.container = container;
        this.addSlot(new Slot(container, 0, 56, 35));                        // your slots: (container, index, x, y)
        for (int r = 0; r < 3; r++) for (int c = 0; c < 9; c++) this.addSlot(new Slot(inv, c + r * 9 + 9, 8 + c * 18, 84 + r * 18));   // player inventory
        for (int c = 0; c < 9; c++) this.addSlot(new Slot(inv, c, 8 + c * 18, 142));                                                    // hotbar
    }
    @Override public boolean stillValid(Player player) { return container.stillValid(player); }
    @Override public ItemStack quickMoveStack(Player player, int index) { /* shift-click: moveItemStackTo between your slots and the player's; return ItemStack.EMPTY when nothing moved */ }
}
```
   The block-entity version passes a `Container` view of `items` (implement `Container` on the block entity or wrap with `SimpleContainer`).
   Register: `MenuType<StationMenu> STATION_MENU = Registry.register(BuiltInRegistries.MENU, id("station"), new MenuType<>(StationMenu::new, FeatureFlags.VANILLA_SET));`
   To send extra data (the BlockPos) use Fabric: `new ExtendedScreenHandlerType<>((syncId, inv, pos) -> new StationMenu(syncId, inv, pos), BlockPos.STREAM_CODEC)`
   and make the block entity implement `ExtendedScreenHandlerFactory<BlockPos>` (`getScreenOpeningData(ServerPlayer)` returns the pos).
3. **Screen** (client only) + registration in `ModClient.onInitializeClient()`: `MenuScreens.register(ModMain.STATION_MENU, StationScreen::new);`
```java
public class StationScreen extends AbstractContainerScreen<StationMenu> {
    private static final ResourceLocation BG = ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "textures/gui/station.png"); // 256x256 png, UI area 176x166
    public StationScreen(StationMenu menu, Inventory inv, Component title) { super(menu, inv, title); }
    @Override protected void renderBg(GuiGraphics g, float delta, int mouseX, int mouseY) { g.blit(BG, leftPos, topPos, 0, 0, imageWidth, imageHeight); }
    @Override public void render(GuiGraphics g, int mouseX, int mouseY, float delta) { super.render(g, mouseX, mouseY, delta); renderTooltip(g, mouseX, mouseY); }
}
```
   A quick background: copy the layout of `minecraft:textures/gui/container/dispenser.png`-style UIs (176×166 with the player inventory at y=84); draw your own PNG, do not ship Mojang's.

## Pattern 3 — synced numbers (progress bars, energy)
`ContainerData` (a `SimpleContainerData(n)` or a lambda-backed one on the block entity) + `this.addDataSlots(data)` in the menu. The screen reads `menu.getData().get(i)`; the server ticks the block entity (`BlockEntityTicker` via `getTicker` on the block) and writes the ints. Crafting stations: on tick, match a recipe (`level.getRecipeManager().getRecipeFor(...)`) and move progress; output slot `mayPlace` → false.

## Checklist before reporting
- Menu registered in `BuiltInRegistries.MENU`; screen registered client-side only (`ModClient`), never in `ModMain`.
- `stillValid` and `quickMoveStack` implemented (shift-click must not crash).
- Lang entry for `container.<mod>.<name>`; GUI texture (your own) at `assets/<mod>/textures/gui/`.
- `./gradlew build` exits 0. Report in `card.files` every class you added and in `card.description` how the GUI opens and what it does.
