---
name: items
description: Items with behaviour on Fabric 1.21.1 (Mojang mappings) — right-click actions with cooldowns, thrown projectiles with a renderer, tooltips, fuel, durability. Use for wands, grenades, charms, tools with special powers.
---

# Items with behaviour (1.21.1 Mojmap). Compiled reference: `examples/kitchen_sink/.../CrystalWandItem.java`, `CrystalBoltEntity.java`

## Right-click action with cooldown + tooltip
```java
public class CrystalWandItem extends Item {
    public CrystalWandItem(Properties p) { super(p.durability(64)); }
    @Override public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (!level.isClientSide) {
            CrystalBoltEntity bolt = new CrystalBoltEntity(level, player);
            bolt.setItem(new ItemStack(ModMain.SKY_CRYSTAL));
            bolt.shootFromRotation(player, player.getXRot(), player.getYRot(), 0.0F, 1.5F, 1.0F);
            level.addFreshEntity(bolt);
            stack.hurtAndBreak(1, player, LivingEntity.getSlotForHand(hand));    // durability
            player.getCooldowns().addCooldown(this, 20);                          // 1 s cooldown (greys the item)
        }
        player.playSound(SoundEvents.ENDER_PEARL_THROW, 0.5F, 1.2F);
        return InteractionResultHolder.sidedSuccess(stack, level.isClientSide);
    }
    @Override public void appendHoverText(ItemStack stack, TooltipContext ctx, List<Component> tooltip, TooltipFlag flag) {
        tooltip.add(Component.translatable("item.<mod>.crystal_wand.tooltip").withStyle(ChatFormatting.AQUA));
    }
}
```
`net.minecraft.world.item.Item` / `TooltipFlag`, `net.minecraft.ChatFormatting`. `useOn(UseOnContext)` for right-clicking a block; `hurtEnemy`/`mineBlock` hooks exist on Item too.

## Thrown projectile (entity + renderer)
```java
public class CrystalBoltEntity extends ThrowableItemProjectile {
    public CrystalBoltEntity(EntityType<? extends CrystalBoltEntity> type, Level level) { super(type, level); }
    public CrystalBoltEntity(Level level, LivingEntity shooter) { super(ModMain.CRYSTAL_BOLT, shooter, level); }
    @Override protected Item getDefaultItem() { return ModMain.SKY_CRYSTAL; }
    @Override protected void onHitEntity(EntityHitResult hit) { super.onHitEntity(hit); hit.getEntity().hurt(damageSources().thrown(this, getOwner()), 4.0F); }
    @Override protected void onHit(HitResult result) { super.onHit(result); if (!level().isClientSide) { level().broadcastEntityEvent(this, (byte) 3); discard(); } }
}
// ModMain: public static final EntityType<CrystalBoltEntity> CRYSTAL_BOLT = Registry.register(BuiltInRegistries.ENTITY_TYPE, id("crystal_bolt"),
//     EntityType.Builder.<CrystalBoltEntity>of(CrystalBoltEntity::new, MobCategory.MISC).sized(0.25F, 0.25F).clientTrackingRange(4).updateInterval(10).build("crystal_bolt"));
// ModClient: EntityRendererRegistry.register(ModMain.CRYSTAL_BOLT, ThrownItemRenderer::new);   // draws the item sprite flying
```
`net.minecraft.world.entity.projectile.ThrowableItemProjectile`, `net.minecraft.world.phys.EntityHitResult` / `HitResult`, `net.minecraft.client.renderer.entity.ThrownItemRenderer`.
Arrow-like projectiles extend `AbstractArrow`; fireballs `Fireball`.

## Fuel, repair, misc
Fuel: `FuelRegistry.INSTANCE.add(ModMain.SKY_CRYSTAL, 1600);` (`net.fabricmc.fabric.api.registry.FuelRegistry`; 1600 ticks = 8 items, coal).
Glint: `new Item.Properties().component(DataComponents.ENCHANTMENT_GLINT_OVERRIDE, true)`. Fire-proof: `.fireResistant()`. Rarity (name colour): `.rarity(Rarity.EPIC)`.
Compost: `CompostingChanceRegistry.INSTANCE.add(ITEM, 0.5f)`.
