package com.example.kitchensink;

import net.minecraft.core.NonNullList;
import net.minecraft.core.component.DataComponents;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.SimpleContainer;
import net.minecraft.world.SimpleMenuProvider;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ChestMenu;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.component.ItemContainerContents;
import net.minecraft.world.level.Level;

/** Compiled reference for the `gui` skill, pattern 1: a backpack reusing the vanilla chest menu. */
public class BackpackItem extends Item {
    public static final int ROWS = 3;

    public BackpackItem(Properties properties) {
        super(properties.stacksTo(1));
    }

    @Override
    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (!level.isClientSide) {
            SimpleContainer container = new SimpleContainer(9 * ROWS) {
                @Override
                public void setChanged() {
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
