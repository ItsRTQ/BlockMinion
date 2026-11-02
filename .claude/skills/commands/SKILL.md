---
name: commands
description: Brigadier commands on Fabric 1.21.1 (Mojang mappings) — register /commands with arguments, permissions and feedback. Use for admin/debug utilities and gameplay actions triggered by text.
---

# Commands (Brigadier, 1.21.1 Mojmap)

```java
CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) ->
    dispatcher.register(Commands.literal("sky")
        .requires(src -> src.hasPermission(2))                                   // op level; omit for everyone
        .then(Commands.literal("give")
            .then(Commands.argument("count", IntegerArgumentType.integer(1, 64))
                .executes(ctx -> {
                    ServerPlayer p = ctx.getSource().getPlayerOrException();
                    int n = IntegerArgumentType.getInteger(ctx, "count");
                    p.getInventory().placeItemBackInInventory(new ItemStack(ModMain.SKY_CRYSTAL, n));
                    ctx.getSource().sendSuccess(() -> Component.literal("Gave " + n + " sky crystals"), true);
                    return n;                                                        // return value = success count
                })))
        .then(Commands.literal("here").executes(ctx -> { ctx.getSource().sendSuccess(() -> Component.literal("You are at " + ctx.getSource().getPosition()), false); return 1; }))));
```
Imports: `net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback`, `net.minecraft.commands.Commands`, `com.mojang.brigadier.arguments.*`
(`IntegerArgumentType`, `StringArgumentType`, `BoolArgumentType`), `net.minecraft.commands.arguments.EntityArgument` (players: `EntityArgument.player("target")`,
`EntityArgument.getPlayer(ctx, "target")`), `net.minecraft.commands.arguments.coordinates.BlockPosArgument`, `net.minecraft.commands.arguments.item.ItemArgument`.
Errors: `ctx.getSource().sendFailure(Component.literal("…"))` and return 0. Client-only commands: `ClientCommandRegistrationCallback` in `net.fabricmc.fabric.api.client.command.v2`.
Compiled reference: `examples/kitchen_sink/src/main/java/com/example/kitchensink/CommandsExample.java`.
