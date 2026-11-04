---
name: events
description: Fabric API event hooks on 1.21.1 (Mojang mappings) — react to item use, block break, attacks, entity death, server/world ticks, player join. Use for any "when X happens, do Y" mechanic.
---

# Fabric events (1.21.1, Mojmap)

Events are static `Event<T>` fields you `register` a callback on, in `onInitialize()` (server + client logic) or
`onInitializeClient()` (client only). Return values decide whether vanilla continues. Compiled reference:
`examples/kitchen_sink/src/main/java/com/example/kitchensink/EventsExample.java`.

| Need | Event | Callback shape |
|---|---|---|
| right-click with an item | `UseItemCallback.EVENT` | `(player, level, hand) -> InteractionResultHolder<ItemStack>`; `pass(stack)` to let vanilla continue |
| right-click a block | `UseBlockCallback.EVENT` | `(player, level, hand, hitResult) -> InteractionResult` |
| attack an entity | `AttackEntityCallback.EVENT` | `(player, level, hand, entity, hitResult) -> InteractionResult` |
| block broken (before/after) | `PlayerBlockBreakEvents.BEFORE` / `.AFTER` | BEFORE returns `boolean` (false cancels) |
| entity dies | `ServerLivingEntityEvents.AFTER_DEATH` | `(entity, damageSource) -> void` |
| entity damaged | `ServerLivingEntityEvents.ALLOW_DAMAGE` | returns `boolean` |
| every server tick | `ServerTickEvents.END_SERVER_TICK` | `(MinecraftServer) -> void` — keep it cheap; count ticks (`server.getTickCount() % 20 == 0`) |
| every world tick | `ServerTickEvents.END_WORLD_TICK` | `(ServerLevel) -> void` |
| player joins / leaves | `ServerPlayConnectionEvents.JOIN` / `DISCONNECT` | `(handler, sender, server)` → `handler.getPlayer()` |
| player sleeps / wakes | `EntitySleepEvents.*` | — |
| item tooltip | `ItemTooltipCallback.EVENT` (client) | `(stack, context, tooltipType, lines) -> void` |

Packages: `net.fabricmc.fabric.api.event.player.*` (Use*/Attack*/PlayerBlockBreakEvents), `net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents`,
`net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents`, `net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents`,
`net.fabricmc.fabric.api.client.item.v1.ItemTooltipCallback`.

```java
UseItemCallback.EVENT.register((player, level, hand) -> {
    ItemStack stack = player.getItemInHand(hand);
    if (stack.is(ModMain.SKY_CRYSTAL) && !level.isClientSide) {
        player.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SPEED, 200, 0));
        stack.shrink(1);
        return InteractionResultHolder.success(stack);
    }
    return InteractionResultHolder.pass(stack);
});
PlayerBlockBreakEvents.AFTER.register((level, player, pos, state, blockEntity) -> {
    if (state.is(ModMain.CRYSTAL_ORE)) level.playSound(null, pos, SoundEvents.AMETHYST_BLOCK_CHIME, SoundSource.BLOCKS, 1f, 1f);
});
ServerLivingEntityEvents.AFTER_DEATH.register((entity, source) -> {
    if (entity instanceof Zombie && source.getEntity() instanceof ServerPlayer p) p.giveExperiencePoints(5);
});
```
Rules: check `level.isClientSide` before changing the world; never block a tick; events registered once (in an initializer), not per use.
Effects by registry id when unsure of the constant name: `BuiltInRegistries.MOB_EFFECT.getHolder(ResourceLocation.parse("minecraft:speed")).orElseThrow()`.
