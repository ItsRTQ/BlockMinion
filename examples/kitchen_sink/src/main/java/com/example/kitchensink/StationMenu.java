package com.example.kitchensink;

import net.minecraft.world.Container;
import net.minecraft.world.SimpleContainer;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;

/** Compiled reference for the `gui` skill, pattern 2: a menu with one input slot plus the player inventory. */
public class StationMenu extends AbstractContainerMenu {
    public static final int SIZE = 1;
    private final Container container;

    public StationMenu(int syncId, Inventory inv) {                 // client side
        this(syncId, inv, new SimpleContainer(SIZE));
    }

    public StationMenu(int syncId, Inventory inv, Container container) {   // server side
        super(ModMain.STATION_MENU, syncId);
        this.container = container;
        this.addSlot(new Slot(container, 0, 80, 35));
        for (int r = 0; r < 3; r++) for (int c = 0; c < 9; c++) this.addSlot(new Slot(inv, c + r * 9 + 9, 8 + c * 18, 84 + r * 18));
        for (int c = 0; c < 9; c++) this.addSlot(new Slot(inv, c, 8 + c * 18, 142));
    }

    @Override
    public boolean stillValid(Player player) {
        return container.stillValid(player);
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        ItemStack result = ItemStack.EMPTY;
        Slot slot = this.slots.get(index);
        if (slot.hasItem()) {
            ItemStack stack = slot.getItem();
            result = stack.copy();
            if (index < SIZE) {
                if (!this.moveItemStackTo(stack, SIZE, this.slots.size(), true)) return ItemStack.EMPTY;
            } else if (!this.moveItemStackTo(stack, 0, SIZE, false)) {
                return ItemStack.EMPTY;
            }
            if (stack.isEmpty()) slot.setByPlayer(ItemStack.EMPTY); else slot.setChanged();
        }
        return result;
    }
}
