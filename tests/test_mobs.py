"""v1 criterion 6 scaffold: mobs in the spec and the GeckoLib generator output."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.config import SUPPORTED_PROFILE
from mod_orchestra.spec import Mob, default_egg_colors, interpret, read_spec
from mod_orchestra.specedit import add_mob, remove_mob
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError

IDEA = "items: sky crystal; blocks: crystal ore; mobs: sky critter; hostile mobs: shadow stalker; tab: Critters"


class SpecMobs(unittest.TestCase):
    def test_grammar_and_defaults(self):
        s = interpret(name="C", mod_id="c_mod", package="com.x.c", idea=IDEA, profile=SUPPORTED_PROFILE)
        self.assertEqual({(m.identifier, m.behavior) for m in s.mobs}, {("sky_critter", "passive"), ("shadow_stalker", "hostile")})
        self.assertEqual(s.questions, [])

    def test_egg_colors_are_distinct_per_mob_and_deterministic(self):
        s = interpret(name="C", mod_id="c_mod", package="com.x.c", idea=IDEA, profile=SUPPORTED_PROFILE)
        colors = {m.identifier: m.egg_colors for m in s.mobs}
        self.assertNotEqual(colors["sky_critter"], colors["shadow_stalker"])
        self.assertEqual(colors["sky_critter"], default_egg_colors("sky_critter", "passive"))
        self.assertTrue(all(0 <= c <= 0xFFFFFF for pair in colors.values() for c in pair))
        # explicit colours in a stored spec are kept; a missing field falls back to the derived pair
        raw = s.to_dict(); raw["mobs"][0]["egg_colors"] = [1, 2]; del raw["mobs"][1]["egg_colors"]
        back = read_spec(raw)
        self.assertEqual(back.mobs[0].egg_colors, (1, 2))
        self.assertEqual(back.mobs[1].egg_colors, default_egg_colors(back.mobs[1].identifier, back.mobs[1].behavior))

    def test_mob_only_idea_has_no_blocking_question(self):
        s = interpret(name="C", mod_id="c_mod", package="com.x.c", idea="mobs: glow slime", profile=SUPPORTED_PROFILE)
        self.assertEqual(s.questions, []); self.assertEqual(s.mobs[0].identifier, "glow_slime")

    def test_validation(self):
        base = interpret(name="C", mod_id="c_mod", package="com.x.c", idea="items: gem", profile=SUPPORTED_PROFILE).to_dict()
        for bad, msg in [
            ({"identifier": "gem", "label": "Gem"}, "collides"),
            ({"identifier": "x", "label": "X"}, "snake_case"),
            ({"identifier": "ok_mob", "label": "Ok", "behavior": "boss"}, "behavior"),
            ({"identifier": "ok_mob", "label": "Ok", "health": 0}, "health"),
            ({"identifier": "ok_mob", "label": "Ok", "drops": ["emerald"]}, "Unknown result"),
        ]:
            with self.assertRaisesRegex(InputError, msg):
                read_spec(base | {"mobs": [bad]})
        ok = read_spec(base | {"mobs": [{"identifier": "ok_mob", "label": "Ok", "drops": ["gem", "minecraft:bone"], "egg_colors": [1, 2]}]})
        self.assertEqual([d.item for d in ok.mobs[0].drops], ["gem", "minecraft:bone"])


class Generated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="C", mod_id="c_mod", package="com.x.c", idea=IDEA)
        add_mob(self.store, "c_mod", identifier="sky_critter", label="Sky Critter", drops=["sky_crystal"], health=8)
        workflow.plan_project(self.store, "c_mod"); workflow.approve_spec(self.store, "c_mod"); workflow.generate_project(self.store, "c_mod")
        self.root = Path(proj["root"]); self.java = self.root / "src/main/java/com/x/c"; self.res = self.root / "src/main/resources"

    def test_gradle_and_mod_json_declare_geckolib(self):
        g = (self.root / "build.gradle").read_text()
        self.assertIn("dl.cloudsmith.io/public/geckolib3/geckolib/maven", g); self.assertIn("geckolib-fabric-${project.minecraft_version}:${project.geckolib_version}", g)
        self.assertIn("geckolib_version=4.7.3", (self.root / "gradle.properties").read_text())
        mj = json.loads((self.res / "fabric.mod.json").read_text())
        self.assertEqual(mj["entrypoints"]["client"][0], "com.x.c.client.ModClient"); self.assertEqual(mj["depends"]["geckolib"], ">=4.7")

    def test_java_files_and_registrations(self):
        main = (self.java / "ModMain.java").read_text()
        for needle in ('EntityType.Builder.of(SkyCritterEntity::new, MobCategory.CREATURE).sized(0.8F, 0.9F).build("sky_critter")',
                       "MobCategory.MONSTER", "new SpawnEggItem(SKY_CRITTER,", "FabricDefaultAttributeRegistry.register(SKY_CRITTER, SkyCritterEntity.createAttributes())",
                       "CreativeModeTabs.SPAWN_EGGS", "output.accept(SKY_CRITTER_SPAWN_EGG)"):
            self.assertIn(needle, main)
        passive = (self.java / "entity/SkyCritterEntity.java").read_text()
        self.assertIn("extends PathfinderMob implements GeoEntity", passive); self.assertIn("MAX_HEALTH, 8.0", passive); self.assertNotIn("MeleeAttackGoal", passive)
        hostile = (self.java / "entity/ShadowStalkerEntity.java").read_text()
        self.assertIn("extends Monster implements GeoEntity", hostile); self.assertIn("NearestAttackableTargetGoal<>(this, Player.class, true)", hostile)
        self.assertIn("ATTACK_DAMAGE, 3.0", hostile)
        self.assertIn('thenPlay("animation.shadow_stalker.attack")', hostile); self.assertIn('.triggerableAnim("attack", ATTACK)', hostile)
        self.assertIn("public boolean doHurtTarget(Entity target)", hostile); self.assertIn('triggerAnim("main", "attack")', hostile)
        self.assertNotIn("ATTACK", passive); self.assertNotIn("doHurtTarget", passive)
        for cls in ("SkyCritter", "ShadowStalker"):
            r = (self.java / f"client/{cls}Renderer.java").read_text()
            self.assertIn(f"extends GeoEntityRenderer<{cls}Entity>", r); self.assertIn("DefaultedEntityGeoModel<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID,", r)
        client = (self.java / "client/ModClient.java").read_text()
        self.assertIn("EntityRendererRegistry.register(ModMain.SKY_CRITTER, SkyCritterRenderer::new)", client)

    def test_assets_follow_defaulted_geo_model_layout(self):
        a = self.res / "assets/c_mod"
        geo = json.loads((a / "geo/entity/sky_critter.geo.json").read_text())
        self.assertEqual(geo["minecraft:geometry"][0]["description"]["identifier"], "geometry.sky_critter")
        from mod_orchestra.rigs import recipe
        self.assertEqual([b["name"] for b in geo["minecraft:geometry"][0]["bones"]], [b["name"] for b in recipe("quadruped")["bones"]])  # default body plan
        anim = json.loads((a / "animations/entity/sky_critter.animation.json").read_text())
        self.assertEqual(set(anim["animations"]), {"animation.sky_critter.idle", "animation.sky_critter.walk", "animation.sky_critter.attack"})
        png = (a / "textures/entity/sky_critter.png").read_bytes()
        self.assertTrue(png.startswith(b"\x89PNG")); self.assertEqual(int.from_bytes(png[16:20], "big"), 64); self.assertEqual(int.from_bytes(png[20:24], "big"), 64)
        loot = json.loads((self.res / "data/c_mod/loot_table/entities/sky_critter.json").read_text())
        self.assertEqual(loot["pools"][0]["entries"][0]["name"], "c_mod:sky_crystal")
        functions = {f["function"] for f in loot["pools"][0]["entries"][0]["functions"]}
        self.assertIn("minecraft:enchanted_count_increase", functions)  # 1.21 name; looting_enchant no longer parses
        self.assertNotIn("minecraft:looting_enchant", functions)
        for mob in ("sky_critter", "shadow_stalker"):  # without an item model the egg renders as the missing-texture cube
            self.assertEqual(json.loads((a / f"models/item/{mob}_spawn_egg.json").read_text()), {"parent": "minecraft:item/template_spawn_egg"})
        legs = [b["cubes"][0]["uv"] for b in geo["minecraft:geometry"][0]["bones"] if b["name"].startswith("leg")]
        self.assertTrue(all(uv[1] >= 18 for uv in legs), legs)  # legs sit beside the head, below the body's UV island
        lang = json.loads((a / "lang/en_us.json").read_text())
        self.assertEqual(lang["entity.c_mod.sky_critter"], "Sky Critter"); self.assertEqual(lang["item.c_mod.sky_critter_spawn_egg"], "Sky Critter Spawn Egg")

    def test_project_without_mobs_still_carries_geckolib_and_the_3d_support_but_no_mob_client(self):
        workflow.new_project(self.store, name="P", mod_id="p_mod", package="com.x.p", idea="items: gem")
        workflow.plan_project(self.store, "p_mod"); workflow.approve_spec(self.store, "p_mod"); workflow.generate_project(self.store, "p_mod")
        root = Path(self.store.project("p_mod")["root"])
        self.assertIn("geckolib", (root / "build.gradle").read_text().lower(), "3D items and the animation contract need it from day one")
        eps = json.loads((root / "src/main/resources/fabric.mod.json").read_text())["entrypoints"]
        self.assertNotIn("com.x.p.client.ModClient", eps["client"]); self.assertIn("com.x.p.client.Model3DClient", eps["client"])
        self.assertTrue((root / "src/main/java/com/x/p/model3d/Item3DBase.java").is_file())


if __name__ == "__main__":
    unittest.main()


class TestContentWithoutItemsOrBlocks(unittest.TestCase):
    """A spec made only of mobs and/or a material set (no free items or blocks) is a real mod: the generator and the
    interpreter must agree on it. Regression: 'At least one deterministic item/block feature required'."""

    def spec(self, **over):
        from mod_orchestra.spec import read_spec
        raw = {"schema_version": 2, "name": "Grokos", "mod_id": "grokos", "package": "com.example.grokos", "idea": "orks", "profile": "fabric-1.21.1-candidate",
               "features": [], "questions": [], "assumptions": [], "tab": None, "tab_icon": None, "recipes": [], "drops": [],
               "mobs": [{"identifier": "small_groko", "label": "Small Groko", "behavior": "hostile", "health": 14, "speed": 0.32, "width": 0.6, "height": 1.3,
                         "attack_damage": 3, "drops": [{"item": "groko_tribe_axe", "count_min": 1, "count_max": 1, "chance": 0.25}], "egg_colors": [4876842, 8943932], "spawn": None}],
               "materials": [{"identifier": "groko_tribe", "label": "Groko Tribe", "ingredient": "minecraft:iron_ingot", "tools": ["sword", "axe"], "armor": ["helmet", "boots"],
                              "durability": 350, "mining_speed": 6.5, "attack_damage_bonus": 2.5, "mining_level": "iron", "enchantability": 12, "armor_defense": [2, 6, 5, 2],
                              "armor_durability": 18, "toughness": 1.0, "knockback_resistance": 0.0, "recipes": False, "armor_style": "textured"}],
               "foods": [], "sounds": [], "enchantments": [], "structures": [], "biomes": [], "dimensions": [], "ores": [], "theme": "tribal"}
        raw.update(over)
        if not raw["materials"]:   # without the gear set, its drops would point at items that do not exist
            for m in raw["mobs"]:
                m["drops"] = [{"item": "minecraft:bone", "count_min": 1, "count_max": 1, "chance": 0.5}]
        return read_spec(raw)

    def generate(self, spec):
        import tempfile
        from mod_orchestra import fabric
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        fabric._generate_into(spec, Path(tmp.name) / "out")
        return Path(tmp.name) / "out"

    def test_has_content(self):
        from mod_orchestra.spec import has_content
        self.assertTrue(has_content(self.spec()))                                   # mobs + material
        self.assertTrue(has_content(self.spec(materials=[])))                       # mobs only
        self.assertTrue(has_content(self.spec(mobs=[])))                            # gear only
        self.assertFalse(has_content(self.spec(mobs=[], materials=[])))             # nothing at all

    def test_mobs_and_gear_without_items_or_blocks_generate(self):
        root = self.generate(self.spec())
        main = (root / "src/main/java/com/example/grokos/ModMain.java").read_text()
        for needle in ("SMALL_GROKO_SPAWN_EGG", "GROKO_TRIBE_SWORD", "GROKO_TRIBE_AXE", "GROKO_TRIBE_HELMET", "GROKO_TRIBE_BOOTS", "CreativeModeTabs.SPAWN_EGGS", "CreativeModeTabs.COMBAT"):
            self.assertIn(needle, main)
        self.assertNotIn("_TAB", main)   # no creative tab was asked for, none invented
        for rel in ("assets/grokos/lang/en_us.json", "assets/grokos/geo/entity/small_groko.geo.json", "data/grokos/loot_table/entities/small_groko.json"):
            self.assertTrue((root / "src/main/resources" / rel).is_file(), rel)

    def test_mobs_only_and_gear_only_generate(self):
        self.generate(self.spec(materials=[]))
        self.generate(self.spec(mobs=[]))

    def test_empty_spec_is_still_rejected_with_a_useful_message(self):
        from mod_orchestra.validation import InputError
        with self.assertRaisesRegex(InputError, "Nothing to generate"):
            self.generate(self.spec(mobs=[], materials=[]))



class TestHeldWeapon(unittest.TestCase):
    """A biped carries the best weapon of its drop table in its right hand and the renderer draws it on the model's held_item bone."""

    DROPS = [{"item": "groko_tribe_helmet", "count_min": 1, "count_max": 1, "chance": 0.2}, {"item": "groko_tribe_pickaxe", "count_min": 1, "count_max": 1, "chance": 0.25},
             {"item": "groko_tribe_sword", "count_min": 1, "count_max": 1, "chance": 0.25}]

    def spec(self, drops=None, **over):
        from mod_orchestra.spec import read_spec
        mob = {"identifier": "tall_groko", "label": "Tall Groko", "behavior": "hostile", "health": 24, "speed": 0.28, "width": 0.7, "height": 2.4, "attack_damage": 5,
               "drops": self.DROPS if drops is None else drops, "egg_colors": [1, 2], "spawn": None, "body_plan": "biped"}
        mob.update(over)
        raw = {"schema_version": 2, "name": "Grokos", "mod_id": "grokos", "package": "com.example.grokos", "idea": "orks", "profile": "fabric-1.21.1-candidate", "features": [],
               "questions": [], "assumptions": [], "tab": None, "tab_icon": None, "recipes": [], "drops": [], "mobs": [mob],
               "materials": [{"identifier": "groko_tribe", "label": "Groko Tribe", "ingredient": "minecraft:iron_ingot", "tools": ["sword", "pickaxe", "axe"], "armor": ["helmet"],
                              "durability": 350, "mining_speed": 6.5, "attack_damage_bonus": 2.5, "mining_level": "iron", "enchantability": 12, "armor_defense": [2, 6, 5, 2],
                              "armor_durability": 18, "toughness": 1.0, "knockback_resistance": 0.0, "recipes": False, "armor_style": "textured"}],
               "foods": [], "sounds": [], "enchantments": [], "structures": [], "biomes": [], "dimensions": [], "ores": [], "theme": "tribal"}
        return read_spec(raw)

    def held(self, spec):
        from mod_orchestra.geckolib import held_item_for
        return held_item_for(spec, spec.mobs[0])

    def test_picks_the_best_weapon_among_the_drops(self):
        self.assertEqual(self.held(self.spec()), "grokos:groko_tribe_sword")                                   # sword before pickaxe before helmet
        self.assertEqual(self.held(self.spec(drops=self.DROPS[:2])), "grokos:groko_tribe_pickaxe")
        self.assertIsNone(self.held(self.spec(drops=self.DROPS[:1])))                                          # armor alone is nothing to hold
        self.assertEqual(self.held(self.spec(drops=[{"item": "minecraft:iron_axe"}, {"item": "minecraft:bone"}])), "minecraft:iron_axe")

    def test_only_bipeds_derive_one_but_any_mob_can_be_told(self):
        self.assertIsNone(self.held(self.spec(body_plan="quadruped")))
        self.assertEqual(self.held(self.spec(body_plan="quadruped", held_item="groko_tribe_axe")), "grokos:groko_tribe_axe")
        self.assertIsNone(self.held(self.spec(held_item="none")))
        self.assertEqual(self.held(self.spec(held_item="minecraft:stick")), "minecraft:stick")
        from mod_orchestra.validation import InputError
        with self.assertRaises(InputError):
            self.spec(held_item="not_an_item")

    def test_entity_equips_it_at_spawn_without_a_second_drop(self):
        from mod_orchestra.geckolib import entity_java
        spec = self.spec(); java = entity_java(spec, spec.mobs[0])
        for needle in ("public SpawnGroupData finalizeSpawn(ServerLevelAccessor level, DifficultyInstance difficulty, MobSpawnType spawnType, SpawnGroupData spawnGroupData)",
                       "super.finalizeSpawn(level, difficulty, spawnType, spawnGroupData)", 'ResourceLocation.parse("grokos:groko_tribe_sword")',
                       "this.setItemSlot(EquipmentSlot.MAINHAND", "this.setDropChance(EquipmentSlot.MAINHAND, 0.0F)", "this.setLeftHanded(false)",
                       "import net.minecraft.world.entity.MobSpawnType;", "import net.minecraft.world.level.ServerLevelAccessor;"):
            self.assertIn(needle, java)
        empty = self.spec(held_item="none"); self.assertNotIn("finalizeSpawn", entity_java(empty, empty.mobs[0]))

    def test_renderer_draws_it_on_the_held_item_bone(self):
        from mod_orchestra.geckolib import renderer_java
        spec = self.spec(); java = renderer_java(spec, spec.mobs[0])
        for needle in ("addRenderLayer(new BlockAndItemGeoLayer<>(this) {", 'protected ItemStack getStackForBone(GeoBone bone, TallGrokoEntity animatable)',
                       '"held_item".equals(bone.getName())', "ItemDisplayContext.THIRD_PERSON_RIGHT_HAND", "Axis.XP.rotationDegrees(-90.0F)",
                       "import software.bernie.geckolib.renderer.layer.BlockAndItemGeoLayer;"):
            self.assertIn(needle, java)
        none = self.spec(held_item="none"); self.assertNotIn("BlockAndItemGeoLayer", renderer_java(none, none.mobs[0]))

    def test_the_whole_project_carries_it(self):
        import tempfile
        from mod_orchestra import fabric
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        fabric._generate_into(self.spec(), Path(tmp.name) / "out")
        java = Path(tmp.name) / "out/src/main/java/com/example/grokos"
        self.assertIn("setItemSlot", (java / "entity/TallGrokoEntity.java").read_text()); self.assertIn("BlockAndItemGeoLayer", (java / "client/TallGrokoRenderer.java").read_text())
        geo = json.loads((Path(tmp.name) / "out/src/main/resources/assets/grokos/geo/entity/tall_groko.geo.json").read_text())
        self.assertIn("held_item", [b["name"] for b in geo["minecraft:geometry"][0]["bones"]])   # the placeholder already has the bone it draws on
