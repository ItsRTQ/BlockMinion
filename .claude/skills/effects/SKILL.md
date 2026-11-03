---
name: effects
description: Custom status effects (MobEffect), potions and brewing, and data-driven enchantments on Fabric 1.21.1 (Mojang mappings). Use when a feature grants a buff/debuff, a drinkable potion, or an enchantment.
---

# Status effects, potions, enchantments (1.21.1 Mojmap). Compiled reference: `examples/kitchen_sink/.../EffectsExample.java`

## Custom status effect
```java
public class CrystalSightEffect extends MobEffect {
    public CrystalSightEffect() { super(MobEffectCategory.BENEFICIAL, 0x4FD1FF); }   // category colours the HUD icon; int = particle colour
    @Override public boolean shouldApplyEffectTickThisTick(int duration, int amplifier) { return duration % 40 == 0; }  // every 2 s
    @Override public boolean applyEffectTick(LivingEntity entity, int amplifier) { entity.heal(1 + amplifier); return true; }  // return true = keep going
}
public static final Holder<MobEffect> CRYSTAL_SIGHT = Registry.registerForHolder(BuiltInRegistries.MOB_EFFECT, id("crystal_sight"), new CrystalSightEffect());
// give: entity.addEffect(new MobEffectInstance(CRYSTAL_SIGHT, 200, 0));   // 200 ticks = 10 s, amplifier 0 = level I
```
`net.minecraft.world.effect.MobEffect` / `MobEffectCategory` / `MobEffectInstance`, `net.minecraft.core.Holder`. Lang: `effect.<mod>.crystal_sight`.
Icon: `assets/<mod>/textures/mob_effect/crystal_sight.png` (18×18). Attribute modifiers (speed, max health): `.addAttributeModifier(Attributes.MOVEMENT_SPEED, id("crystal_sight_speed"), 0.2, AttributeModifier.Operation.ADD_MULTIPLIED_TOTAL)` on the effect.

## Potion + brewing
```java
public static final Holder<Potion> CRYSTAL_SIGHT_POTION = Registry.registerForHolder(BuiltInRegistries.POTION, id("crystal_sight"), new Potion("crystal_sight", new MobEffectInstance(CRYSTAL_SIGHT, 3600)));
FabricBrewingRecipeRegistryBuilder.BUILD.register(builder -> builder.addMix(Potions.AWKWARD, ModMain.SKY_CRYSTAL, CRYSTAL_SIGHT_POTION));  // awkward + ingredient = potion
```
`net.minecraft.world.item.alchemy.Potion` / `Potions`, `net.fabricmc.fabric.api.registry.FabricBrewingRecipeRegistryBuilder`. Lang: `item.minecraft.potion.effect.crystal_sight` (+ `splash_potion`, `lingering_potion`, `tipped_arrow`).
A drinkable item: `new Item(new Item.Properties().food(new FoodProperties.Builder().nutrition(0).saturationModifier(0).alwaysEdible().effect(new MobEffectInstance(CRYSTAL_SIGHT, 600), 1.0f).build()))` or `PotionContents` on a custom item.

## Enchantments are JSON in 1.21 (no Java)
`data/<mod>/enchantment/<id>.json` — the generator writes them from `craftctl add-enchantment` / the UI. Shape:
```json
{"description": {"translate": "enchantment.<mod>.gem_edge"}, "supported_items": "#minecraft:enchantable/weapon", "weight": 5, "max_level": 3,
 "min_cost": {"base": 5, "per_level_above_first": 8}, "max_cost": {"base": 25, "per_level_above_first": 8}, "anvil_cost": 2, "slots": ["mainhand"],
 "effects": {"minecraft:damage": [{"effect": {"type": "minecraft:add", "value": {"type": "minecraft:linear", "base": 1.0, "per_level_above_first": 0.5}}}]}}
```
Effect components: `minecraft:damage`, `minecraft:damage_protection`, `minecraft:post_attack` (e.g. `minecraft:ignite`), `minecraft:attributes`, `minecraft:item_damage`,
`minecraft:block_experience`, `minecraft:tick`. Read values in code: `EnchantmentHelper.getItemEnchantmentLevel(holder, stack)` with the holder from `registries.lookupOrThrow(Registries.ENCHANTMENT).getOrThrow(key)`.
To make it appear in the enchanting table add the id to `data/minecraft/tags/enchantment/in_enchanting_table.json` (the generator does); `treasure` = `treasure.json` tag instead.
