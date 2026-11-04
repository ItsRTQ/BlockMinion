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
        self.assertEqual(mj["entrypoints"]["client"], ["com.x.c.client.ModClient"]); self.assertEqual(mj["depends"]["geckolib"], ">=4.7")

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
        self.assertEqual(set(anim["animations"]), {"animation.sky_critter.idle", "animation.sky_critter.walk"})
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

    def test_project_without_mobs_has_no_geckolib(self):
        workflow.new_project(self.store, name="P", mod_id="p_mod", package="com.x.p", idea="items: gem")
        workflow.plan_project(self.store, "p_mod"); workflow.approve_spec(self.store, "p_mod"); workflow.generate_project(self.store, "p_mod")
        root = Path(self.store.project("p_mod")["root"])
        self.assertNotIn("geckolib", (root / "build.gradle").read_text().lower())
        self.assertNotIn("client", json.loads((root / "src/main/resources/fabric.mod.json").read_text())["entrypoints"])


if __name__ == "__main__":
    unittest.main()
