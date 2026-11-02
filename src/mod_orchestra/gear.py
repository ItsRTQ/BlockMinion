"""Tool/armor sets (materials) and foods — Mojang mappings, Minecraft 1.21.1.

Per material: a Tier class, Sword/Pickaxe/Axe/Shovel/Hoe items with vanilla attribute formulas,
an ArmorMaterial registered as a Holder with two armor layer textures, ArmorItems per piece,
item models (handheld for tools), placeholder textures, lang, and the standard crafting recipes.
Per food: an Item with FoodProperties (nutrition, saturation, effects).
"""
from __future__ import annotations
from .spec import Spec, Material, Food, Recipe, resolve_ingredient, TOOL_KINDS, ARMOR_KINDS

# vanilla attack/speed pairs (damage bonus added to tier bonus; speed is negative = slower)
TOOL_ATTRS = {"sword": ("SwordItem", 3, -2.4), "pickaxe": ("PickaxeItem", 1, -2.8), "axe": ("AxeItem", 6, -3.1), "shovel": ("ShovelItem", 1.5, -3.0), "hoe": ("HoeItem", -2, -1.0)}
ARMOR_TYPE = {"helmet": "HELMET", "chestplate": "CHESTPLATE", "leggings": "LEGGINGS", "boots": "BOOTS"}
INCORRECT_TAG = {"wood": "INCORRECT_FOR_WOODEN_TOOL", "stone": "INCORRECT_FOR_STONE_TOOL", "iron": "INCORRECT_FOR_IRON_TOOL",
                 "diamond": "INCORRECT_FOR_DIAMOND_TOOL", "netherite": "INCORRECT_FOR_NETHERITE_TOOL"}
PATTERNS = {"sword": (["X", "X", "S"], {"X": None, "S": "minecraft:stick"}), "pickaxe": (["XXX", " S ", " S "], {"X": None, "S": "minecraft:stick"}),
            "axe": (["XX", "XS", " S"], {"X": None, "S": "minecraft:stick"}), "shovel": (["X", "S", "S"], {"X": None, "S": "minecraft:stick"}),
            "hoe": (["XX", " S", " S"], {"X": None, "S": "minecraft:stick"}), "helmet": (["XXX", "X X"], {"X": None}),
            "chestplate": (["X X", "XXX", "XXX"], {"X": None}), "leggings": (["XXX", "X X", "X X"], {"X": None}), "boots": (["X X", "X X"], {"X": None})}


def cls(ident: str) -> str:
    return "".join(p.capitalize() for p in ident.split("_"))


def ingredient_java(spec: Spec, value: str) -> str:
    obj = resolve_ingredient(spec.local_ids(), spec.mod_id, value)
    if "tag" in obj:
        ns, path = obj["tag"].split(":", 1)
        return f'Ingredient.of(TagKey.create(Registries.ITEM, ResourceLocation.fromNamespaceAndPath("{ns}", "{path}")))'
    item = obj["item"]
    if item.startswith(spec.mod_id + ":"):
        return f"Ingredient.of(ModMain.{item.split(':', 1)[1].upper()})"
    ns, path = item.split(":", 1)
    return f'Ingredient.of(BuiltInRegistries.ITEM.get(ResourceLocation.fromNamespaceAndPath("{ns}", "{path}")))'


def tier_java(spec: Spec, m: Material) -> str:
    return "\n".join([
        f"package {spec.package}.gear;", "",
        f"import {spec.package}.ModMain;",
        "import net.minecraft.core.registries.BuiltInRegistries;", "import net.minecraft.core.registries.Registries;",
        "import net.minecraft.resources.ResourceLocation;", "import net.minecraft.tags.BlockTags;", "import net.minecraft.tags.TagKey;",
        "import net.minecraft.world.item.Tier;", "import net.minecraft.world.item.crafting.Ingredient;", "import net.minecraft.world.level.block.Block;", "",
        f"/** Generated tier for material '{m.identifier}' ({m.label}). */",
        f"public final class {cls(m.identifier)}Tier implements Tier {{",
        f"    public static final {cls(m.identifier)}Tier INSTANCE = new {cls(m.identifier)}Tier();", "",
        f"    @Override public int getUses() {{ return {int(m.durability)}; }}",
        f"    @Override public float getSpeed() {{ return {float(m.mining_speed)}F; }}",
        f"    @Override public float getAttackDamageBonus() {{ return {float(m.attack_damage_bonus)}F; }}",
        f"    @Override public TagKey<Block> getIncorrectBlocksForDrops() {{ return BlockTags.{INCORRECT_TAG[m.mining_level]}; }}",
        f"    @Override public int getEnchantmentValue() {{ return {int(m.enchantability)}; }}",
        f"    @Override public Ingredient getRepairIngredient() {{ return {ingredient_java(spec, m.ingredient)}; }}",
        "}", ""])


def gear_registrations(spec: Spec) -> tuple[list[str], list[str], list[str]]:
    """(imports, ModMain static fields, onInitialize lines) for all materials and foods."""
    if not spec.materials and not spec.foods:
        return [], [], []
    imports = ["net.minecraft.world.item.SwordItem", "net.minecraft.world.item.PickaxeItem", "net.minecraft.world.item.AxeItem",
               "net.minecraft.world.item.ShovelItem", "net.minecraft.world.item.HoeItem", "net.minecraft.world.item.ArmorItem",
               "net.minecraft.world.item.ArmorMaterial", "net.minecraft.world.item.crafting.Ingredient", "net.minecraft.core.Holder",
               "net.minecraft.core.registries.Registries", "net.minecraft.resources.ResourceLocation", "net.minecraft.sounds.SoundEvents",
               "net.minecraft.Util", "net.minecraft.tags.TagKey", "java.util.EnumMap", "java.util.List",
               "net.minecraft.world.food.FoodProperties", "net.minecraft.world.effect.MobEffectInstance"]
    imports += [f"{spec.package}.gear.{cls(m.identifier)}Tier" for m in spec.materials]
    fields, init = [], []
    for m in spec.materials:
        tier = f"{cls(m.identifier)}Tier.INSTANCE"
        if m.armor:
            d = [int(x) for x in m.armor_defense]
            fields.append(f'    public static final Holder<ArmorMaterial> {m.identifier.upper()}_ARMOR_MATERIAL = Registry.registerForHolder(BuiltInRegistries.ARMOR_MATERIAL, id("{m.identifier}"),')
            fields.append(f"        new ArmorMaterial(Util.make(new EnumMap<>(ArmorItem.Type.class), map -> {{")
            fields.append(f"            map.put(ArmorItem.Type.HELMET, {d[0]}); map.put(ArmorItem.Type.CHESTPLATE, {d[1]}); map.put(ArmorItem.Type.LEGGINGS, {d[2]}); map.put(ArmorItem.Type.BOOTS, {d[3]});")
            fields.append(f"        }}), {int(m.enchantability)}, SoundEvents.ARMOR_EQUIP_IRON, () -> {ingredient_java(spec, m.ingredient)},")
            fields.append(f'        List.of(new ArmorMaterial.Layer(id("{m.identifier}"))), {float(m.toughness)}F, {float(m.knockback_resistance)}F));')
        for kind in m.tools:
            klass, dmg, speed = TOOL_ATTRS[kind]
            const = f"{m.identifier}_{kind}".upper()
            # SwordItem.createAttributes(Tier, int, float); DiggerItem subclasses take (Tier, float, float)
            dmg_lit = f"{int(dmg)}" if kind == "sword" else f"{float(dmg)}F"
            fields.append(f'    public static final Item {const} = Registry.register(BuiltInRegistries.ITEM, id("{m.identifier}_{kind}"),')
            fields.append(f"        new {klass}({tier}, new Item.Properties().attributes({klass}.createAttributes({tier}, {dmg_lit}, {float(speed)}F))));")
            init.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.{'COMBAT' if kind == 'sword' else 'TOOLS_AND_UTILITIES'}).register(entries -> entries.accept({const}));")
        for kind in m.armor:
            const = f"{m.identifier}_{kind}".upper()
            fields.append(f'    public static final Item {const} = Registry.register(BuiltInRegistries.ITEM, id("{m.identifier}_{kind}"),')
            fields.append(f"        new ArmorItem({m.identifier.upper()}_ARMOR_MATERIAL, ArmorItem.Type.{ARMOR_TYPE[kind]}, new Item.Properties().durability(ArmorItem.Type.{ARMOR_TYPE[kind]}.getDurability({int(m.armor_durability)}))));")
            init.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept({const}));")
    for f in spec.foods:
        const = f.identifier.upper()
        builder = f"new FoodProperties.Builder().nutrition({int(f.nutrition)}).saturationModifier({float(f.saturation)}F)"
        for e in f.effects:
            ns, path = e["effect"].split(":", 1)
            # Resolve by registry id: Mojmap constant names differ from ids (speed -> MOVEMENT_SPEED, haste -> DIG_SPEED, ...)
            holder = f'BuiltInRegistries.MOB_EFFECT.getHolder(ResourceLocation.fromNamespaceAndPath("{ns}", "{path}")).orElseThrow()'
            builder += f".effect(new MobEffectInstance({holder}, {int(e.get('duration', 100))}, {int(e.get('amplifier', 0))}), {float(e.get('chance', 1.0))}F)"
        if f.always_edible: builder += ".alwaysEdible()"
        if f.fast: builder += ".fast()"
        fields.append(f'    public static final Item {const} = Registry.register(BuiltInRegistries.ITEM, id("{f.identifier}"), new Item(new Item.Properties().food({builder}.build())));')
        init.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.FOOD_AND_DRINKS).register(entries -> entries.accept({const}));")
    return imports, fields, init


def gear_item_ids(spec: Spec) -> list[str]:
    return [i for m in spec.materials for i in m.item_ids()] + [f.identifier for f in spec.foods]


def gear_recipes(spec: Spec) -> list[Recipe]:
    out = []
    for m in spec.materials:
        if not m.recipes:
            continue
        for kind in list(m.tools) + list(m.armor):
            pattern, key = PATTERNS[kind]
            out.append(Recipe(id=f"{m.identifier}_{kind}", kind="shaped", result=f"{m.identifier}_{kind}", pattern=tuple(pattern),
                              key={k: (m.ingredient if v is None else v) for k, v in key.items()}))
    return out
