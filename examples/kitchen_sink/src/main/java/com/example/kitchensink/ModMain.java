package com.example.kitchensink;

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
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.world.SimpleMenuProvider;
import net.minecraft.world.flag.FeatureFlags;
import net.minecraft.world.inventory.MenuType;
import net.minecraft.network.chat.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.minecraft.world.item.SpawnEggItem;
import net.fabricmc.fabric.api.object.builder.v1.entity.FabricDefaultAttributeRegistry;
import com.example.kitchensink.entity.SkyCritterEntity;
import net.fabricmc.fabric.api.biome.v1.BiomeModifications;
import net.fabricmc.fabric.api.biome.v1.BiomeSelectors;
import net.minecraft.world.entity.SpawnPlacementTypes;
import net.minecraft.world.entity.SpawnPlacements;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.tags.TagKey;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.FenceBlock;
import net.minecraft.world.level.block.SlabBlock;
import net.minecraft.world.level.block.StairBlock;
import net.minecraft.world.level.block.WallBlock;
import net.minecraft.world.item.SwordItem;
import net.minecraft.world.item.PickaxeItem;
import net.minecraft.world.item.AxeItem;
import net.minecraft.world.item.ShovelItem;
import net.minecraft.world.item.HoeItem;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.core.Holder;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.Util;
import java.util.EnumMap;
import java.util.List;
import net.minecraft.world.food.FoodProperties;
import net.minecraft.world.effect.MobEffectInstance;
import com.example.kitchensink.gear.CrystalTier;
import com.example.kitchensink.gear.CrystalArmorItem;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.level.levelgen.GenerationStep;
import net.fabricmc.fabric.api.itemgroup.v1.FabricItemGroup;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.ItemStack;

public class ModMain implements ModInitializer {
    public static final String MOD_ID = "kitchen_sink";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);
    public static ModConfig CONFIG;
    public static final MenuType<StationMenu> STATION_MENU = Registry.register(BuiltInRegistries.MENU, id("station"), new MenuType<>(StationMenu::new, FeatureFlags.VANILLA_SET));
    public static final Item BACKPACK = Registry.register(BuiltInRegistries.ITEM, id("backpack"), new BackpackItem(new Item.Properties()));
    public static final Item CRYSTAL_WAND = Registry.register(BuiltInRegistries.ITEM, id("crystal_wand"), new CrystalWandItem(new Item.Properties()));
    public static final EntityType<CrystalBoltEntity> CRYSTAL_BOLT = Registry.register(BuiltInRegistries.ENTITY_TYPE, id("crystal_bolt"),
        EntityType.Builder.<CrystalBoltEntity>of(CrystalBoltEntity::new, MobCategory.MISC).sized(0.25F, 0.25F).clientTrackingRange(4).updateInterval(10).build("crystal_bolt"));

    private static ResourceLocation id(String path) {
        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);
    }

    public static final Item SKY_CRYSTAL = Registry.register(BuiltInRegistries.ITEM, id("sky_crystal"), new Item(new Item.Properties()));
    public static final Block CRYSTAL_ORE = Registry.register(BuiltInRegistries.BLOCK, id("crystal_ore"), new Block(BlockBehaviour.Properties.of().strength(3.0F).requiresCorrectToolForDrops()));
    public static final Item CRYSTAL_ORE_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_ore"), new BlockItem(CRYSTAL_ORE, new Item.Properties()));
    public static final Block CRYSTAL_STATION = Registry.register(BuiltInRegistries.BLOCK, id("crystal_station"), new Block(BlockBehaviour.Properties.of().strength(3.0F).requiresCorrectToolForDrops()));
    public static final Item CRYSTAL_STATION_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_station"), new BlockItem(CRYSTAL_STATION, new Item.Properties()));
    public static final Block CRYSTAL_BRICKS = Registry.register(BuiltInRegistries.BLOCK, id("crystal_bricks"), new Block(BlockBehaviour.Properties.of().strength(3.0F).requiresCorrectToolForDrops()));
    public static final Item CRYSTAL_BRICKS_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_bricks"), new BlockItem(CRYSTAL_BRICKS, new Item.Properties()));

    // Block variants (stairs/slab/fence/wall) of the blocks above
    public static final Block CRYSTAL_BRICKS_STAIRS = Registry.register(BuiltInRegistries.BLOCK, id("crystal_bricks_stairs"), new StairBlock(CRYSTAL_BRICKS.defaultBlockState(), BlockBehaviour.Properties.ofFullCopy(CRYSTAL_BRICKS)));
    public static final Item CRYSTAL_BRICKS_STAIRS_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_bricks_stairs"), new BlockItem(CRYSTAL_BRICKS_STAIRS, new Item.Properties()));
    public static final Block CRYSTAL_BRICKS_SLAB = Registry.register(BuiltInRegistries.BLOCK, id("crystal_bricks_slab"), new SlabBlock(BlockBehaviour.Properties.ofFullCopy(CRYSTAL_BRICKS)));
    public static final Item CRYSTAL_BRICKS_SLAB_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_bricks_slab"), new BlockItem(CRYSTAL_BRICKS_SLAB, new Item.Properties()));
    public static final Block CRYSTAL_BRICKS_FENCE = Registry.register(BuiltInRegistries.BLOCK, id("crystal_bricks_fence"), new FenceBlock(BlockBehaviour.Properties.ofFullCopy(CRYSTAL_BRICKS)));
    public static final Item CRYSTAL_BRICKS_FENCE_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_bricks_fence"), new BlockItem(CRYSTAL_BRICKS_FENCE, new Item.Properties()));
    public static final Block CRYSTAL_BRICKS_WALL = Registry.register(BuiltInRegistries.BLOCK, id("crystal_bricks_wall"), new WallBlock(BlockBehaviour.Properties.ofFullCopy(CRYSTAL_BRICKS)));
    public static final Item CRYSTAL_BRICKS_WALL_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_bricks_wall"), new BlockItem(CRYSTAL_BRICKS_WALL, new Item.Properties()));
    public static final EntityType<SkyCritterEntity> SKY_CRITTER = Registry.register(BuiltInRegistries.ENTITY_TYPE, id("sky_critter"),
        EntityType.Builder.of(SkyCritterEntity::new, MobCategory.CREATURE).sized(0.8F, 0.9F).build("sky_critter"));
    public static final Item SKY_CRITTER_SPAWN_EGG = Registry.register(BuiltInRegistries.ITEM, id("sky_critter_spawn_egg"),
        new SpawnEggItem(SKY_CRITTER, 0x99A47D, 0xDFE3D3, new Item.Properties()));

    // Tools, armor and food (generated from materials/foods in the spec)
    public static final Holder<ArmorMaterial> CRYSTAL_ARMOR_MATERIAL = Registry.registerForHolder(BuiltInRegistries.ARMOR_MATERIAL, id("crystal"),
        new ArmorMaterial(Util.make(new EnumMap<>(ArmorItem.Type.class), map -> {
            map.put(ArmorItem.Type.HELMET, 2); map.put(ArmorItem.Type.CHESTPLATE, 6); map.put(ArmorItem.Type.LEGGINGS, 5); map.put(ArmorItem.Type.BOOTS, 2);
        }), 14, SoundEvents.ARMOR_EQUIP_IRON, () -> Ingredient.of(ModMain.SKY_CRYSTAL),
        List.of(new ArmorMaterial.Layer(id("crystal"))), 0.0F, 0.0F));
    public static final Item CRYSTAL_SWORD = Registry.register(BuiltInRegistries.ITEM, id("crystal_sword"),
        new SwordItem(CrystalTier.INSTANCE, new Item.Properties().attributes(SwordItem.createAttributes(CrystalTier.INSTANCE, 3, -2.4F))));
    public static final Item CRYSTAL_HELMET = Registry.register(BuiltInRegistries.ITEM, id("crystal_helmet"),
        new CrystalArmorItem(CRYSTAL_ARMOR_MATERIAL, ArmorItem.Type.HELMET, new Item.Properties().durability(ArmorItem.Type.HELMET.getDurability(15))));
    public static final Item CRYSTAL_CHESTPLATE = Registry.register(BuiltInRegistries.ITEM, id("crystal_chestplate"),
        new CrystalArmorItem(CRYSTAL_ARMOR_MATERIAL, ArmorItem.Type.CHESTPLATE, new Item.Properties().durability(ArmorItem.Type.CHESTPLATE.getDurability(15))));
    public static final Item CRYSTAL_LEGGINGS = Registry.register(BuiltInRegistries.ITEM, id("crystal_leggings"),
        new CrystalArmorItem(CRYSTAL_ARMOR_MATERIAL, ArmorItem.Type.LEGGINGS, new Item.Properties().durability(ArmorItem.Type.LEGGINGS.getDurability(15))));
    public static final Item CRYSTAL_BOOTS = Registry.register(BuiltInRegistries.ITEM, id("crystal_boots"),
        new CrystalArmorItem(CRYSTAL_ARMOR_MATERIAL, ArmorItem.Type.BOOTS, new Item.Properties().durability(ArmorItem.Type.BOOTS.getDurability(15))));

    // Dimension keys (right-click to travel)
    public static final Item CRYSTAL_REALM_KEY = Registry.register(BuiltInRegistries.ITEM, id("crystal_realm_key"), new CrystalRealmKeyItem(new Item.Properties()));

    // Sounds: assets/<mod>/sounds/<id>.ogg (upload your .ogg; play with level.playSound(null, pos, X_SOUND, SoundSource.NEUTRAL, 1f, 1f))
    public static final SoundEvent CRYSTAL_CHIME_SOUND = Registry.register(BuiltInRegistries.SOUND_EVENT, id("crystal_chime"), SoundEvent.createVariableRangeEvent(id("crystal_chime")));

    public static final ResourceKey<CreativeModeTab> TAB_KEY = ResourceKey.create(Registries.CREATIVE_MODE_TAB, id("kitchen_sink_tab"));
    public static final CreativeModeTab TAB = FabricItemGroup.builder()
        .icon(() -> new ItemStack(SKY_CRYSTAL))
        .title(Component.translatable("itemGroup.kitchen_sink.kitchen_sink_tab"))
        .displayItems((params, output) -> {
            output.accept(SKY_CRYSTAL);
            output.accept(CRYSTAL_ORE_ITEM);
            output.accept(CRYSTAL_STATION_ITEM);
            output.accept(CRYSTAL_BRICKS_ITEM);
            output.accept(SKY_CRITTER_SPAWN_EGG);
            output.accept(BACKPACK);
            output.accept(CRYSTAL_WAND);
            output.accept(CRYSTAL_SWORD);
            output.accept(CRYSTAL_HELMET);
            output.accept(CRYSTAL_CHESTPLATE);
            output.accept(CRYSTAL_LEGGINGS);
            output.accept(CRYSTAL_BOOTS);
            output.accept(CRYSTAL_BRICKS_STAIRS_ITEM);
            output.accept(CRYSTAL_BRICKS_SLAB_ITEM);
            output.accept(CRYSTAL_BRICKS_FENCE_ITEM);
            output.accept(CRYSTAL_BRICKS_WALL_ITEM);
            output.accept(CRYSTAL_REALM_KEY);
        })
        .build();

    @Override
    public void onInitialize() {
        CONFIG = ModConfig.load();
        PayloadTypeRegistry.playC2S().register(OpenPayload.TYPE, OpenPayload.CODEC);
        ServerPlayNetworking.registerGlobalReceiver(OpenPayload.TYPE, (payload, context) ->
            context.server().execute(() -> context.player().openMenu(new SimpleMenuProvider((syncId, inv, p) -> new StationMenu(syncId, inv), Component.literal("Crystal Station")))));
        DataExample.register();
        EventsExample.register();
        CommandsExample.register();
        LootAndTradesExample.register();
        EffectsExample.register();
        Registry.register(BuiltInRegistries.CREATIVE_MODE_TAB, TAB_KEY, TAB);
        FabricDefaultAttributeRegistry.register(SKY_CRITTER, SkyCritterEntity.createAttributes());
        SpawnPlacements.register(SKY_CRITTER, SpawnPlacementTypes.ON_GROUND, Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, Mob::checkMobSpawnRules);
        BiomeModifications.addSpawn(BiomeSelectors.foundInOverworld(), MobCategory.CREATURE, SKY_CRITTER, 8, 2, 4);
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.SPAWN_EGGS).register(entries -> entries.accept(SKY_CRITTER_SPAWN_EGG));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_BRICKS_STAIRS_ITEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_BRICKS_SLAB_ITEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_BRICKS_FENCE_ITEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_BRICKS_WALL_ITEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_SWORD));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_HELMET));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_CHESTPLATE));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_LEGGINGS));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> entries.accept(CRYSTAL_BOOTS));
        BiomeModifications.addFeature(BiomeSelectors.foundInOverworld(), GenerationStep.Decoration.UNDERGROUND_ORES, ResourceKey.create(Registries.PLACED_FEATURE, id("crystal_ore")));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.TOOLS_AND_UTILITIES).register(entries -> entries.accept(CRYSTAL_REALM_KEY));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept(SKY_CRYSTAL));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_ORE_ITEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_STATION_ITEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_BRICKS_ITEM));
    }
}
