package com.example.kitchensink;

import com.mojang.brigadier.arguments.IntegerArgumentType;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;

/** Compiled reference for the `commands` skill. */
public final class CommandsExample {
    private CommandsExample() {}

    public static void register() {
        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) ->
            dispatcher.register(Commands.literal("sky")
                .requires(src -> src.hasPermission(2))
                .then(Commands.literal("give")
                    .then(Commands.argument("count", IntegerArgumentType.integer(1, 64))
                        .executes(ctx -> {
                            ServerPlayer p = ctx.getSource().getPlayerOrException();
                            int n = IntegerArgumentType.getInteger(ctx, "count");
                            p.getInventory().placeItemBackInInventory(new ItemStack(ModMain.SKY_CRYSTAL, n));
                            ctx.getSource().sendSuccess(() -> Component.literal("Gave " + n + " sky crystals"), true);
                            return n;
                        })))
                .then(Commands.literal("here").executes(ctx -> {
                    ctx.getSource().sendSuccess(() -> Component.literal("You are at " + ctx.getSource().getPosition()), false);
                    return 1;
                }))));
    }
}
