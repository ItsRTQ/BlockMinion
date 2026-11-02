package com.example.crystalexample;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.minecraft.world.item.SpawnEggItem;
import net.fabricmc.fabric.api.object.builder.v1.entity.FabricDefaultAttributeRegistry;
import com.example.crystalexample.entity.CrystalCritterEntity;
import net.minecraft.world.item.SwordItem;
import net.minecraft.world.item.PickaxeItem;
import net.minecraft.world.item.AxeItem;
import net.minecraft.world.item.ShovelItem;
import net.minecraft.world.item.HoeItem;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.Util;
import net.minecraft.tags.TagKey;
import java.util.EnumMap;
import java.util.List;
import net.minecraft.world.food.FoodProperties;
import net.minecraft.world.effect.MobEffectInstance;
import com.example.crystalexample.gear.CrystalTier;
import net.fabricmc.fabric.api.itemgroup.v1.FabricItemGroup;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.ItemStack;

public class ModMain implements ModInitializer {
    public static final String MOD_ID = "crystal_example";

    private static ResourceLocation id(String path) {
        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);
    }

    public static final Item SKY_CRYSTAL = Registry.register(BuiltInRegistries.ITEM, id("sky_crystal"), new Item(new Item.Properties()));
    public static final Item LUNAR_GEM = Registry.register(BuiltInRegistries.ITEM, id("lunar_gem"), new Item(new Item.Properties()));
    public static final Block CRYSTAL_STONE = Registry.register(BuiltInRegistries.BLOCK, id("crystal_stone"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));
    public static final Item CRYSTAL_STONE_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_stone"), new BlockItem(CRYSTAL_STONE, new Item.Properties()));
    public static final Block CRYSTAL_ORE = Registry.register(BuiltInRegistries.BLOCK, id("crystal_ore"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));
    public static final Item CRYSTAL_ORE_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_ore"), new BlockItem(CRYSTAL_ORE, new Item.Properties()));
    public static final EntityType<CrystalCritterEntity> CRYSTAL_CRITTER = Registry.register(BuiltInRegistries.ENTITY_TYPE, id("crystal_critter"),
        EntityType.Builder.of(CrystalCritterEntity::new, MobCategory.CREATURE).sized(0.8F, 0.9F).build("crystal_critter"));
    public static final Item CRYSTAL_CRITTER_SPAWN_EGG = Registry.register(BuiltInRegistries.ITEM, id("crystal_critter_spawn_egg"),
        new SpawnEggItem(CRYSTAL_CRITTER, 0x8A6DD1, 0xE6D8FF, new Item.Properties()));

    // Tools, armor and food (generated from materials/foods in the spec)
    public static final Holder<ArmorMaterial> CRYSTAL_ARMOR_MATERIAL = Registry.registerForHolder(BuiltInRegistries.ARMOR_MATERIAL, id("crystal"),
        new ArmorMaterial(Util.make(new EnumMap<>(ArmorItem.Type.class), map -> {
            map.put(ArmorItem.Type.HELMET, 3); map.put(ArmorItem.Type.CHESTPLATE, 8); map.put(ArmorItem.Type.LEGGINGS, 6); map.put(ArmorItem.Type.BOOTS, 3);
        }), 14, SoundEvents.ARMOR_EQUIP_IRON, () -> Ingredient.of(ModMain.SKY_CRYSTAL),
        List.of(new ArmorMaterial.Layer(id("crystal"))), 2.0F, 0.0F));
    public static final Item CRYSTAL_SWORD = Registry.register(BuiltInRegistries.ITEM, id("crystal_sword"),
        new SwordItem(CrystalTier.INSTANCE, new Item.Properties().attributes(SwordItem.createAttributes(CrystalTier.INSTANCE, 3, -2.4F))));
    public static final Item CRYSTAL_PICKAXE = Registry.register(BuiltInRegistries.ITEM, id("crystal_pickaxe"),
        new PickaxeItem(CrystalTier.INSTANCE, new Item.Properties().attributes(PickaxeItem.createAttributes(CrystalTier.INSTANCE, 1.0F, -2.8F))));
    public static final Item CRYSTAL_AXE = Registry.register(BuiltInRegistries.ITEM, id("crystal_axe"),
        new AxeItem(CrystalTier.INSTANCE, new Item.Properties().attributes(AxeItem.createAttributes(CrystalTier.INSTANCE, 6.0F, -3.1F))));
    public static final Item CRYSTAL_SHOVEL = Registry.register(BuiltInRegistries.ITEM, id("crystal_shovel"),
        new ShovelItem(CrystalTier.INSTANCE, new Item.Properties().attributes(ShovelItem.createAttributes(CrystalTier.INSTANCE, 1.5F, -3.0F))));
    public static final Item CRYSTAL_HOE = Registry.register(BuiltInRegistries.ITEM, id("crystal_hoe"),
        new HoeItem(CrystalTier.INSTANCE, new Item.Properties().attributes(HoeItem.createAttributes(CrystalTier.INSTANCE, -2.0F, -1.0F))));
    public static final Item CRYSTAL_HELMET = Registry.register(BuiltInRegistries.ITEM, id("crystal_helmet"),
        new ArmorItem(CRYSTAL_ARMOR_MATERIAL, ArmorItem.Type.HELMET, new Item.Properties().durability(ArmorItem.Type.HELMET.getDurability(30))));
    public static final Item CRYSTAL_CHESTPLATE = Registry.register(BuiltInRegistries.ITEM, id("crystal_chestplate"),
        new ArmorItem(CRYSTAL_ARMOR_MATERIAL, ArmorItem.Type.CHESTPLATE, new Item.Properties().durability(ArmorItem.Type.CHESTPLATE.getDurability(30))));
    public static final Item CRYSTAL_LEGGINGS = Registry.register(BuiltInRegistries.ITEM, id("crystal_leggings"),
        new ArmorItem(CRYSTAL_ARMOR_MATERIAL, ArmorItem.Type.LEGGINGS, new Item.Properties().durability(ArmorItem.Type.LEGGINGS.getDurability(30))));
    public static final Item CRYSTAL_BOOTS = Registry.register(BuiltInRegistries.ITEM, id("crystal_boots"),
        new ArmorItem(CRYSTAL_ARMOR_MATERIAL, ArmorItem.Type.BOOTS, new Item.Properties().durability(ArmorItem.Type.BOOTS.getDurability(30))));
    public static final Item CRYSTAL_BERRY = Registry.register(BuiltInRegistries.ITEM, id("crystal_berry"), new Item(new Item.Properties().food(new FoodProperties.Builder().nutrition(4).saturationModifier(0.6F).effect(new MobEffectInstance(BuiltInRegistries.MOB_EFFECT.getHolder(ResourceLocation.fromNamespaceAndPath("minecraft", "night_vision")).orElseThrow(), 400, 0), 1.0F).build())));

    public static final ResourceKey<CreativeModeTab> TAB_KEY = ResourceKey.create(Registries.CREATIVE_MODE_TAB, id("crystal_example_tab"));
    public static final CreativeModeTab TAB = FabricItemGroup.builder()
        .icon(() -> new ItemStack(SKY_CRYSTAL))
        .title(Component.translatable("itemGroup.crystal_example.crystal_example_tab"))
        .displayItems((params, output) -> {
            output.accept(SKY_CRYSTAL);
            output.accept(LUNAR_GEM);
            output.accept(CRYSTAL_STONE_ITEM);
            output.accept(CRYSTAL_ORE_ITEM);
            output.accept(CRYSTAL_CRITTER_SPAWN_EGG);
            output.accept(CRYSTAL_SWORD);
            output.accept(CRYSTAL_PICKAXE);
            output.accept(CRYSTAL_AXE);
            output.accept(CRYSTAL_SHOVEL);
            output.accept(CRYSTAL_HOE);
            output.accept(CRYSTAL_HELMET);
            output.accept(CRYSTAL_CHESTPLATE);
            output.accept(CRYSTAL_LEGGINGS);
            output.accept(CRYSTAL_BOOTS);
            output.accept(CRYSTAL_BERRY);
        })
        .build();

    @Override
    public void onInitialize() {
        Registry.register(BuiltInRegistries.CREATIVE_MODE_TAB, TAB_KEY, TAB);
        FabricDefaultAttributeRegistry.register(CRYSTAL_CRITTER, CrystalCritterEntity.createAttributes());
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.SPAWN_EGGS).register(entries -> entries.accept(CRYSTAL_CRITTER_SPAWN_EGG));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_SWORD));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.TOOLS_AND_UTILITIES).register(entries -> entries.accept(CRYSTAL_PICKAXE));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.TOOLS_AND_UTILITIES).register(entries -> entries.accept(CRYSTAL_AXE));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.TOOLS_AND_UTILITIES).register(entries -> entries.accept(CRYSTAL_SHOVEL));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.TOOLS_AND_UTILITIES).register(entries -> entries.accept(CRYSTAL_HOE));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_HELMET));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_CHESTPLATE));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_LEGGINGS));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_BOOTS));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.FOOD_AND_DRINKS).register(entries -> entries.accept(CRYSTAL_BERRY));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept(SKY_CRYSTAL));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept(LUNAR_GEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_STONE_ITEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_ORE_ITEM));
    }
}
