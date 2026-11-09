"""GeckoLib entity generation (Fabric 1.21.1, Mojang mappings, GeckoLib 4.7.x).

Produces, per mob: entity class (PathfinderMob or Monster) implementing GeoEntity with idle/walk
controllers, renderer + client entrypoint, EntityType + SpawnEggItem registration, attributes,
loot table, lang, and placeholder assets (geo, animation, texture at the body plan's resolution) that a designer worker
later replaces with a real Blockbench model. Asset layout follows DefaultedEntityGeoModel:
assets/<mod>/geo/entity/<id>.geo.json, animations/entity/<id>.animation.json, textures/entity/<id>.png.
"""
from __future__ import annotations
import json
from .spec import Spec, Mob, resolve_result, coerce_mob_drop, coerce_spawn

GECKOLIB_VERSION = "4.7.3"
GECKOLIB_MAVEN = "https://dl.cloudsmith.io/public/geckolib3/geckolib/maven/"


def class_name(m: Mob) -> str:
    return "".join(part.capitalize() for part in m.identifier.split("_"))


HELD_PRIORITY = ("sword", "axe", "pickaxe", "shovel", "hoe")   # which drop a biped carries when none is named
HELD_BONE = "held_item"                                        # the empty bone at the palm that the item is drawn on


def held_item_for(spec: Spec, m: Mob) -> str | None:
    """Resolved id (namespace:path) of what the mob carries in its main hand, or None. Explicit `held_item` wins ("none" disables);
    otherwise a biped carries the best weapon or tool of its drop table (sword, axe, pickaxe, shovel, hoe)."""
    if m.held_item == "none":
        return None
    if m.held_item:
        return resolve_result(spec.local_ids(), spec.mod_id, m.held_item)
    if m.body_plan != "biped":
        return None
    items = [coerce_mob_drop(d).item for d in m.drops]
    for kind in HELD_PRIORITY:
        for item in items:
            if item.rsplit(":", 1)[-1].endswith("_" + kind):
                return resolve_result(spec.local_ids(), spec.mod_id, item)
    return None


def scale_attribute_line(scale: float) -> str:
    """The one line that sizes a mob: vanilla scales the hitbox from it and GeckoLib's renderer draws the model with
    LivingEntity.getScale(), so nothing else (renderer, ModMain, geometry, texture) changes."""
    return f"            .add(Attributes.SCALE, {float(scale)})"


def entity_java(spec: Spec, m: Mob) -> str:
    cls = class_name(m) + "Entity"
    hostile = m.behavior == "hostile"
    neutral = m.behavior == "neutral"
    base = "Monster" if hostile else "PathfinderMob"
    attrs = ("Monster.createMonsterAttributes()" if hostile else "Mob.createMobAttributes()")
    attr_lines = [f"            .add(Attributes.MAX_HEALTH, {float(m.health)})", f"            .add(Attributes.MOVEMENT_SPEED, {float(m.speed)})"]
    if float(m.scale) != 1.0:   # right after the speed: the same place models.patch_scale puts it in a generated project
        attr_lines.append(scale_attribute_line(m.scale))
    if hostile or neutral:
        attr_lines.append(f"            .add(Attributes.ATTACK_DAMAGE, {float(m.attack_damage)})")
    goals = ["        this.goalSelector.addGoal(0, new FloatGoal(this));"]
    if hostile:
        goals += ["        this.goalSelector.addGoal(2, new MeleeAttackGoal(this, 1.2D, false));",
                  "        this.targetSelector.addGoal(1, new HurtByTargetGoal(this));",
                  "        this.targetSelector.addGoal(2, new NearestAttackableTargetGoal<>(this, Player.class, true));"]
    elif neutral:  # like a wolf or iron golem: minds its business, fights back when hurt
        goals += ["        this.goalSelector.addGoal(2, new MeleeAttackGoal(this, 1.2D, false));",
                  "        this.targetSelector.addGoal(1, new HurtByTargetGoal(this));"]
    goals += ["        this.goalSelector.addGoal(5, new WaterAvoidingRandomStrollGoal(this, 1.0D));",
              "        this.goalSelector.addGoal(6, new LookAtPlayerGoal(this, Player.class, 8.0F));",
              "        this.goalSelector.addGoal(7, new RandomLookAroundGoal(this));"]
    imports = [
        "net.minecraft.world.entity.EntityType", "net.minecraft.world.entity.Mob", "net.minecraft.world.entity.PathfinderMob",
        "net.minecraft.world.entity.ai.attributes.AttributeSupplier", "net.minecraft.world.entity.ai.attributes.Attributes",
        "net.minecraft.world.entity.ai.goal.FloatGoal", "net.minecraft.world.entity.ai.goal.LookAtPlayerGoal",
        "net.minecraft.world.entity.ai.goal.RandomLookAroundGoal", "net.minecraft.world.entity.ai.goal.WaterAvoidingRandomStrollGoal",
        "net.minecraft.world.entity.player.Player", "net.minecraft.world.level.Level",
        "software.bernie.geckolib.animatable.GeoEntity", "software.bernie.geckolib.animatable.instance.AnimatableInstanceCache",
        "software.bernie.geckolib.animation.AnimatableManager", "software.bernie.geckolib.animation.AnimationController",
        "software.bernie.geckolib.animation.PlayState", "software.bernie.geckolib.animation.RawAnimation",
        "software.bernie.geckolib.util.GeckoLibUtil",
    ]
    if hostile:
        imports += ["net.minecraft.world.entity.monster.Monster", "net.minecraft.world.entity.ai.goal.MeleeAttackGoal",
                    "net.minecraft.world.entity.ai.goal.target.HurtByTargetGoal", "net.minecraft.world.entity.ai.goal.target.NearestAttackableTargetGoal"]
    elif neutral:
        imports += ["net.minecraft.world.entity.ai.goal.MeleeAttackGoal", "net.minecraft.world.entity.ai.goal.target.HurtByTargetGoal"]
    fights = hostile or neutral
    if fights:
        imports.append("net.minecraft.world.entity.Entity")
    held = held_item_for(spec, m)
    held_lines: list[str] = []
    if held:
        imports += ["net.minecraft.core.registries.BuiltInRegistries", "net.minecraft.resources.ResourceLocation", "net.minecraft.world.DifficultyInstance",
                    "net.minecraft.world.entity.EquipmentSlot", "net.minecraft.world.entity.MobSpawnType", "net.minecraft.world.entity.SpawnGroupData",
                    "net.minecraft.world.item.ItemStack", "net.minecraft.world.level.ServerLevelAccessor"]
        held_lines = [
            "    @Override",
            "    public SpawnGroupData finalizeSpawn(ServerLevelAccessor level, DifficultyInstance difficulty, MobSpawnType spawnType, SpawnGroupData spawnGroupData) {",
            "        SpawnGroupData data = super.finalizeSpawn(level, difficulty, spawnType, spawnGroupData);",
            "        this.setLeftHanded(false);   // the model carries its item in the right hand",
            f'        this.setItemSlot(EquipmentSlot.MAINHAND, new ItemStack(BuiltInRegistries.ITEM.get(ResourceLocation.parse("{held}"))));',
            "        this.setDropChance(EquipmentSlot.MAINHAND, 0.0F);   // what it drops is decided by the loot table",
            "        return data;",
            "    }",
            ""]
    lines = [f"package {spec.package}.entity;", ""] + [f"import {i};" for i in sorted(set(imports))] + ["",
        f"/** Generated by Minecraft Mod Orchestra: {m.label} ({m.behavior}). Animations: idle, walk{', attack (one-shot, triggered on hit)' if fights else ''}. */",
        f"public class {cls} extends {base} implements GeoEntity {{",
        f'    private static final RawAnimation IDLE = RawAnimation.begin().thenLoop("animation.{m.identifier}.idle");',
        f'    private static final RawAnimation WALK = RawAnimation.begin().thenLoop("animation.{m.identifier}.walk");'] + ([
        f'    private static final RawAnimation ATTACK = RawAnimation.begin().thenPlay("animation.{m.identifier}.attack");'] if fights else []) + [
        "    private final AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this);",
        "",
        f"    public {cls}(EntityType<? extends {base}> type, Level level) {{",
        "        super(type, level);",
        "    }",
        "",
        "    public static AttributeSupplier.Builder createAttributes() {",
        f"        return {attrs}"] + [l if i < len(attr_lines) - 1 else l + ";" for i, l in enumerate(attr_lines)] + [
        "    }",
        "",
        "    @Override",
        "    protected void registerGoals() {"] + goals + [
        "    }",
        "",
        "    @Override",
        "    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {",
        '        controllers.add(new AnimationController<>(this, "main", 5, state -> {',
        "            if (state.isMoving()) {",
        "                return state.setAndContinue(WALK);",
        "            }",
        "            return state.setAndContinue(IDLE);",
        '        })' + ('.triggerableAnim("attack", ATTACK)' if fights else "") + ");",
        "    }",
        ""] + ([
        "    @Override",
        "    public boolean doHurtTarget(Entity target) {",
        "        boolean hit = super.doHurtTarget(target);",
        "        if (hit) {",
        '            triggerAnim("main", "attack");  // server side: GeckoLib syncs the one-shot to clients',
        "        }",
        "        return hit;",
        "    }",
        ""] if fights else []) + held_lines + [
        "    @Override",
        "    public AnimatableInstanceCache getAnimatableInstanceCache() {",
        "        return cache;",
        "    }",
        "}", ""]
    return "\n".join(lines)


def renderer_java(spec: Spec, m: Mob) -> str:
    cls = class_name(m)
    held = held_item_for(spec, m)
    imports = [f"{spec.package}.ModMain", f"{spec.package}.entity.{cls}Entity", "net.minecraft.client.renderer.entity.EntityRendererProvider",
               "net.minecraft.resources.ResourceLocation", "software.bernie.geckolib.model.DefaultedEntityGeoModel", "software.bernie.geckolib.renderer.GeoEntityRenderer"]
    layer: list[str] = []
    if held:
        imports += ["com.mojang.blaze3d.vertex.PoseStack", "com.mojang.math.Axis", "net.minecraft.client.renderer.MultiBufferSource", "net.minecraft.world.item.ItemDisplayContext",
                    "net.minecraft.world.item.ItemStack", "software.bernie.geckolib.cache.object.GeoBone", "software.bernie.geckolib.renderer.layer.BlockAndItemGeoLayer"]
        layer = [
            f"        // The main-hand item ({held}) is drawn on the model's \"{HELD_BONE}\" bone, at the palm of the right arm.",
            "        addRenderLayer(new BlockAndItemGeoLayer<>(this) {",
            "            @Override",
            f"            protected ItemStack getStackForBone(GeoBone bone, {cls}Entity animatable) {{",
            "                ItemStack stack = animatable.getMainHandItem();",
            f'                return "{HELD_BONE}".equals(bone.getName()) && !stack.isEmpty() ? stack : null;',
            "            }",
            "",
            "            @Override",
            f"            protected ItemDisplayContext getTransformTypeForStack(GeoBone bone, ItemStack stack, {cls}Entity animatable) {{",
            "                return ItemDisplayContext.THIRD_PERSON_RIGHT_HAND;",
            "            }",
            "",
            "            @Override",
            f"            protected void renderStackForBone(PoseStack poseStack, GeoBone bone, ItemStack stack, {cls}Entity animatable, MultiBufferSource bufferSource, float partialTick, int packedLight, int packedOverlay) {{",
            "                poseStack.mulPose(Axis.XP.rotationDegrees(-90.0F));",
            "                super.renderStackForBone(poseStack, bone, stack, animatable, bufferSource, partialTick, packedLight, packedOverlay);",
            "            }",
            "        });"]
    return "\n".join([f"package {spec.package}.client;", ""] + [f"import {i};" for i in sorted(set(imports))] + ["",
        f"public class {cls}Renderer extends GeoEntityRenderer<{cls}Entity> {{",
        f"    public {cls}Renderer(EntityRendererProvider.Context context) {{",
        f'        super(context, new DefaultedEntityGeoModel<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "{m.identifier}")));'] + layer + [
        "    }", "}", ""])


def client_init_java(spec: Spec) -> str:
    lines = [f"package {spec.package}.client;", "", f"import {spec.package}.ModMain;",
             "import net.fabricmc.api.ClientModInitializer;",
             "import net.fabricmc.fabric.api.client.rendering.v1.EntityRendererRegistry;", "",
             "public class ModClient implements ClientModInitializer {", "    @Override", "    public void onInitializeClient() {"]
    for m in spec.mobs:
        lines.append(f"        EntityRendererRegistry.register(ModMain.{m.identifier.upper()}, {class_name(m)}Renderer::new);")
    lines += ["    }", "}", ""]
    return "\n".join(lines)


def main_registrations(spec: Spec) -> tuple[list[str], list[str], list[str]]:
    """(imports, static field lines, onInitialize lines) for ModMain."""
    if not spec.mobs:
        return [], [], []
    imports = ["net.minecraft.world.entity.EntityType", "net.minecraft.world.entity.MobCategory", "net.minecraft.world.item.SpawnEggItem",
               "net.fabricmc.fabric.api.object.builder.v1.entity.FabricDefaultAttributeRegistry"] + [f"{spec.package}.entity.{class_name(m)}Entity" for m in spec.mobs]
    if any(coerce_spawn(m.spawn) for m in spec.mobs):
        imports += ["net.fabricmc.fabric.api.biome.v1.BiomeModifications", "net.fabricmc.fabric.api.biome.v1.BiomeSelectors",
                    "net.minecraft.world.entity.SpawnPlacementTypes", "net.minecraft.world.entity.SpawnPlacements", "net.minecraft.world.level.levelgen.Heightmap",
                    "net.minecraft.world.entity.Mob", "net.minecraft.world.entity.monster.Monster", "net.minecraft.core.registries.Registries",
                    "net.minecraft.resources.ResourceKey", "net.minecraft.resources.ResourceLocation", "net.minecraft.tags.TagKey", "net.minecraft.world.level.biome.Biome"]
    fields, init = [], []
    for m in spec.mobs:
        cls, const = class_name(m) + "Entity", m.identifier.upper()
        cat = "MobCategory.MONSTER" if m.behavior == "hostile" else "MobCategory.CREATURE"
        fields.append(f'    public static final EntityType<{cls}> {const} = Registry.register(BuiltInRegistries.ENTITY_TYPE, id("{m.identifier}"),')
        fields.append(f'        EntityType.Builder.of({cls}::new, {cat}).sized({float(m.width)}F, {float(m.height)}F).build("{m.identifier}"));')
        fields.append(f'    public static final Item {const}_SPAWN_EGG = Registry.register(BuiltInRegistries.ITEM, id("{m.identifier}_spawn_egg"),')
        fields.append(f"        new SpawnEggItem({const}, 0x{m.egg_colors[0]:06X}, 0x{m.egg_colors[1]:06X}, new Item.Properties()));")
        init.append(f"        FabricDefaultAttributeRegistry.register({const}, {cls}.createAttributes());")
        sp = coerce_spawn(m.spawn)
        if sp:
            rules = "Monster::checkMonsterSpawnRules" if m.behavior == "hostile" else "Mob::checkMobSpawnRules"
            init.append(f"        SpawnPlacements.register({const}, SpawnPlacementTypes.ON_GROUND, Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, {rules});")
            for b in sp.biomes:
                init.append(f"        BiomeModifications.addSpawn({biome_selector_java(b)}, {cat}, {const}, {int(sp.weight)}, {int(sp.min_group)}, {int(sp.max_group)});")
        init.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.SPAWN_EGGS).register(entries -> entries.accept({const}_SPAWN_EGG));")
    return imports, fields, init


def biome_selector_java(b: str) -> str:
    if b == "overworld": return "BiomeSelectors.foundInOverworld()"
    if b == "nether": return "BiomeSelectors.foundInTheNether()"
    if b == "end": return "BiomeSelectors.foundInTheEnd()"
    ns, path = b.lstrip("#").split(":", 1)
    if b.startswith("#"):
        return f'BiomeSelectors.tag(TagKey.create(Registries.BIOME, ResourceLocation.fromNamespaceAndPath("{ns}", "{path}")))'
    return f'BiomeSelectors.includeByKey(ResourceKey.create(Registries.BIOME, ResourceLocation.fromNamespaceAndPath("{ns}", "{path}")))'


def placeholder_geo(m: Mob) -> dict:
    """The base rig of the mob's body plan, renamed to the mob: the mod renders a correct silhouette before the designer runs."""
    from .rigs import rig_geo_for
    return rig_geo_for(m.body_plan, m.identifier)


def placeholder_animation(m: Mob) -> dict:
    from .rigs import rig_animation_for
    return rig_animation_for(m.body_plan, m.identifier)


def placeholder_texture_size(m: Mob) -> tuple[int, int]:
    from .rigs import rig_texture_size
    return rig_texture_size(m.body_plan)


def entity_loot(spec: Spec, m: Mob) -> dict:
    """One pool per drop so each entry carries its own chance and count range; Looting adds 0-1.
    (1.21 renamed looting_enchant -> enchanted_count_increase; the enchantment id is required.)"""
    pools = []
    for raw in m.drops:
        d = coerce_mob_drop(raw)
        entry = {"type": "minecraft:item", "name": resolve_result(spec.local_ids(), spec.mod_id, d.item),
                 "functions": [{"function": "minecraft:set_count", "count": {"type": "minecraft:uniform", "min": d.count_min, "max": d.count_max}},
                               {"function": "minecraft:enchanted_count_increase", "enchantment": "minecraft:looting",
                                "count": {"type": "minecraft:uniform", "min": 0, "max": 1}}]}
        pool = {"rolls": 1, "entries": [entry]}
        if d.chance < 1:
            pool["conditions"] = [{"condition": "minecraft:random_chance", "chance": round(d.chance, 4)}]
        pools.append(pool)
    return {"type": "minecraft:entity", "pools": pools}


def gradle_dependency_lines() -> tuple[str, str]:
    repo = """    maven {
        name = 'GeckoLib'
        url = '%s'
        content { includeGroup 'software.bernie.geckolib' }
    }""" % GECKOLIB_MAVEN
    dep = '    modImplementation "software.bernie.geckolib:geckolib-fabric-${project.minecraft_version}:${project.geckolib_version}"'
    return repo, dep
