"""P0 hotfixes: block tool tags, natural spawning."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.config import SUPPORTED_PROFILE
from mod_orchestra.spec import interpret, read_spec
from mod_orchestra.specedit import add_mob
from mod_orchestra.content import add_feature
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError


class ToolTags(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="T", mod_id="t_mod", package="com.x.t", idea="items: gem; blocks: gem ore, soft dirt, log pile")
        add_feature(self.store, "t_mod", kind="block", label="Deep Ore", tool="pickaxe", mining_level="diamond")
        add_feature(self.store, "t_mod", kind="block", label="Loose Sand", tool="none")
        self.root = Path(proj["root"])
        workflow.plan_project(self.store, "t_mod"); workflow.approve_spec(self.store, "t_mod"); workflow.generate_project(self.store, "t_mod")

    def test_tags_and_java(self):
        tags = self.root / "src/main/resources/data/minecraft/tags/block"
        mineable = json.loads((tags / "mineable/pickaxe.json").read_text())["values"]
        self.assertIn("t_mod:gem_ore", mineable); self.assertIn("t_mod:deep_ore", mineable); self.assertNotIn("t_mod:loose_sand", mineable)
        self.assertEqual(json.loads((tags / "needs_diamond_tool.json").read_text())["values"], ["t_mod:deep_ore"])
        main = (self.root / "src/main/java/com/x/t/ModMain.java").read_text()
        self.assertIn('id("gem_ore"), new Block(BlockBehaviour.Properties.of().strength(3.0F).requiresCorrectToolForDrops())', main)
        self.assertIn('id("loose_sand"), new Block(BlockBehaviour.Properties.of().strength(3.0F))', main)

    def test_validation(self):
        base = interpret(name="V", mod_id="v_mod", package="com.x.v", idea="blocks: ore", profile=SUPPORTED_PROFILE).to_dict()
        base["features"][0]["tool"] = "hammer"
        with self.assertRaisesRegex(InputError, "tool must be"):
            read_spec(base)


class NaturalSpawn(unittest.TestCase):
    def test_spawn_java_and_validation(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            proj = workflow.new_project(store, name="S", mod_id="s_mod", package="com.x.s", idea="items: gem")
            add_mob(store, "s_mod", identifier="forest_fox", label="Forest Fox", spawn={"biomes": ["#minecraft:is_forest", "minecraft:plains"], "weight": 12, "min_group": 2, "max_group": 4})
            add_mob(store, "s_mod", identifier="cave_stalker", label="Cave Stalker", behavior="hostile", spawn={"biomes": ["overworld"], "weight": 30})
            add_mob(store, "s_mod", identifier="egg_only", label="Egg Only")
            with self.assertRaisesRegex(InputError, "spawn.biomes"):
                add_mob(store, "s_mod", identifier="bad", label="Bad", spawn={"biomes": ["forest"]})
            workflow.plan_project(store, "s_mod"); workflow.approve_spec(store, "s_mod"); workflow.generate_project(store, "s_mod")
            main = (Path(proj["root"]) / "src/main/java/com/x/s/ModMain.java").read_text()
        self.assertIn("SpawnPlacements.register(FOREST_FOX, SpawnPlacementTypes.ON_GROUND, Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, Mob::checkMobSpawnRules)", main)
        self.assertIn('BiomeModifications.addSpawn(BiomeSelectors.tag(TagKey.create(Registries.BIOME, ResourceLocation.fromNamespaceAndPath("minecraft", "is_forest"))), MobCategory.CREATURE, FOREST_FOX, 12, 2, 4)', main)
        self.assertIn('BiomeSelectors.includeByKey(ResourceKey.create(Registries.BIOME, ResourceLocation.fromNamespaceAndPath("minecraft", "plains")))', main)
        self.assertIn("BiomeModifications.addSpawn(BiomeSelectors.foundInOverworld(), MobCategory.MONSTER, CAVE_STALKER, 30, 1, 3)", main)
        self.assertIn("Monster::checkMonsterSpawnRules", main)
        self.assertNotIn("EGG_ONLY, 10", main)


if __name__ == "__main__":
    unittest.main()


class Sounds(unittest.TestCase):
    def test_sound_event_and_sounds_json(self):
        from mod_orchestra.specedit import add_sound
        from mod_orchestra.content import set_sound_file
        import base64
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            proj = workflow.new_project(store, name="S", mod_id="snd", package="com.x.snd", idea="items: gem")
            add_sound(store, "snd", identifier="gem_chime", label="Gem chimes", category="block")
            with self.assertRaisesRegex(InputError, "category"):
                add_sound(store, "snd", identifier="bad", label="x", category="loud")
            workflow.plan_project(store, "snd"); workflow.approve_spec(store, "snd"); workflow.generate_project(store, "snd")
            root = Path(proj["root"])
            self.assertIn('SoundEvent GEM_CHIME_SOUND = Registry.register(BuiltInRegistries.SOUND_EVENT, id("gem_chime"), SoundEvent.createVariableRangeEvent(id("gem_chime")))', (root / "src/main/java/com/x/snd/ModMain.java").read_text())
            sj = json.loads((root / "src/main/resources/assets/snd/sounds.json").read_text())
            self.assertEqual(sj["gem_chime"], {"category": "block", "subtitle": "subtitles.snd.gem_chime", "sounds": ["snd:gem_chime"]})
            self.assertEqual(json.loads((root / "src/main/resources/assets/snd/lang/en_us.json").read_text())["subtitles.snd.gem_chime"], "Gem chimes")
            with self.assertRaisesRegex(InputError, "Not an Ogg"):
                set_sound_file(store, "snd", identifier="gem_chime", ogg_base64=base64.b64encode(b"RIFF....").decode())
            out = set_sound_file(store, "snd", identifier="gem_chime", ogg_base64=base64.b64encode(b"OggS" + b"\x00" * 40).decode())
            self.assertTrue(out["file"].endswith("sounds/gem_chime.ogg"))


class OreWorldgen(unittest.TestCase):
    def test_json_and_java(self):
        from mod_orchestra.specedit import add_ore
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            proj = workflow.new_project(store, name="O", mod_id="o_mod", package="com.x.o", idea="blocks: ruby ore, nether gem ore")
            add_ore(store, "o_mod", block="ruby_ore", vein_size=8, veins_per_chunk=7, min_y=-64, max_y=16, discard_on_air=0.7)
            add_ore(store, "o_mod", block="nether_gem_ore", vein_size=10, veins_per_chunk=5, min_y=10, max_y=100, biomes=["nether"])
            with self.assertRaisesRegex(InputError, "not a block"):
                add_ore(store, "o_mod", block="ruby")
            with self.assertRaisesRegex(InputError, "min_y < max_y"):
                add_ore(store, "o_mod", block="ruby_ore", min_y=50, max_y=10)
            workflow.plan_project(store, "o_mod"); workflow.approve_spec(store, "o_mod"); workflow.generate_project(store, "o_mod")
            root = Path(proj["root"]); wg = root / "src/main/resources/data/o_mod/worldgen"
            cf = json.loads((wg / "configured_feature/ruby_ore.json").read_text())
            self.assertEqual(cf["type"], "minecraft:ore"); self.assertEqual(cf["config"]["size"], 8); self.assertEqual(cf["config"]["discard_chance_on_air_exposure"], 0.7)
            self.assertEqual([t["target"]["tag"] for t in cf["config"]["targets"]], ["minecraft:stone_ore_replaceables", "minecraft:deepslate_ore_replaceables"])
            pf = json.loads((wg / "placed_feature/ruby_ore.json").read_text())
            self.assertEqual(pf["feature"], "o_mod:ruby_ore"); self.assertEqual(pf["placement"][0], {"type": "minecraft:count", "count": 7})
            self.assertEqual(pf["placement"][2]["height"]["max_inclusive"], {"absolute": 16})
            nf = json.loads((wg / "configured_feature/nether_gem_ore.json").read_text())
            self.assertEqual(nf["config"]["targets"][0]["target"]["tag"], "minecraft:base_stone_nether")
            main = (root / "src/main/java/com/x/o/ModMain.java").read_text()
            self.assertIn('BiomeModifications.addFeature(BiomeSelectors.foundInOverworld(), GenerationStep.Decoration.UNDERGROUND_ORES, ResourceKey.create(Registries.PLACED_FEATURE, id("ruby_ore")))', main)
            self.assertIn("BiomeSelectors.foundInTheNether()", main)
            self.assertEqual(main.count("import net.minecraft.core.registries.Registries;"), 1, "imports deduped")


class VariantsAndEnchantments(unittest.TestCase):
    def test_variants_and_enchantment_files(self):
        from mod_orchestra.specedit import set_variants, add_enchantment
        from mod_orchestra.content import add_enchantment_any
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            proj = workflow.new_project(store, name="V", mod_id="v_mod", package="com.x.v", idea="items: gem; blocks: marble")
            set_variants(store, "v_mod", "marble", ["stairs", "slab", "fence", "wall"])
            with self.assertRaisesRegex(InputError, "not a block"):
                set_variants(store, "v_mod", "gem", ["slab"])
            add_enchantment(store, "v_mod", identifier="gem_edge", label="Gem Edge", kind="damage")
            with self.assertRaisesRegex(InputError, "kind must be"):
                add_enchantment(store, "v_mod", identifier="xx", label="X", kind="speed")
            workflow.plan_project(store, "v_mod"); workflow.approve_spec(store, "v_mod"); workflow.generate_project(store, "v_mod")
            root = Path(proj["root"]); res = root / "src/main/resources"
            main = (root / "src/main/java/com/x/v/ModMain.java").read_text()
            self.assertIn("new StairBlock(MARBLE.defaultBlockState(), BlockBehaviour.Properties.ofFullCopy(MARBLE))", main)
            self.assertIn('new BlockItem(MARBLE_WALL, new Item.Properties())', main); self.assertIn("entries.accept(MARBLE_SLAB_ITEM)", main)
            self.assertEqual(len(json.loads((res / "assets/v_mod/blockstates/marble_stairs.json").read_text())["variants"]), 40)
            self.assertEqual(len(json.loads((res / "assets/v_mod/blockstates/marble_wall.json").read_text())["multipart"]), 9)
            self.assertEqual(json.loads((res / "data/v_mod/recipe/marble_stairs.json").read_text())["result"]["count"], 4)
            self.assertEqual(json.loads((res / "data/minecraft/tags/block/fences.json").read_text())["values"], ["v_mod:marble_fence"])
            self.assertIn("v_mod:marble_slab", json.loads((res / "data/minecraft/tags/block/mineable/pickaxe.json").read_text())["values"])
            self.assertEqual(json.loads((res / "assets/v_mod/lang/en_us.json").read_text())["block.v_mod.marble_fence"], "marble Fence")  # grammar labels are kept as typed
            ench = json.loads((res / "data/v_mod/enchantment/gem_edge.json").read_text())
            self.assertEqual(ench["slots"], ["mainhand"]); self.assertIn("minecraft:damage", ench["effects"])
            self.assertEqual(json.loads((res / "data/minecraft/tags/enchantment/in_enchanting_table.json").read_text())["values"], ["v_mod:gem_edge"])
            out = add_enchantment_any(store, "v_mod", identifier="gem_skin", label="Gem Skin", kind="protection")
            self.assertTrue(out["generated"]); self.assertTrue((res / "data/v_mod/enchantment/gem_skin.json").is_file())
            self.assertEqual(json.loads((res / "data/v_mod/enchantment/gem_skin.json").read_text())["supported_items"], "#minecraft:enchantable/armor")


class Armor3D(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        from mod_orchestra.specedit import add_material
        proj = workflow.new_project(self.store, name="A", mod_id="a3", package="com.x.a3", idea="items: ovis ingot")
        add_material(self.store, "a3", identifier="ovis", label="Ovis", ingredient="ovis_ingot", tools=[], armor=["helmet", "chestplate"], armor_style="3d")
        with self.assertRaisesRegex(InputError, "armor_style"):
            add_material(self.store, "a3", identifier="bad", label="B", ingredient="ovis_ingot", tools=[], armor=["helmet"], armor_style="holographic")
        workflow.plan_project(self.store, "a3"); workflow.approve_spec(self.store, "a3"); workflow.generate_project(self.store, "a3")
        self.root = Path(proj["root"])

    def test_generated_geckolib_armor(self):
        j = self.root / "src/main/java/com/x/a3"
        item = (j / "gear/OvisArmorItem.java").read_text(); rend = (j / "client/OvisArmorRenderer.java").read_text()
        self.assertIn("extends ArmorItem implements GeoItem", item); self.assertIn("getGeoArmorRenderer", item); self.assertIn("new OvisArmorRenderer()", item)
        self.assertIn('new DefaultedItemGeoModel<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "armor/ovis"))', rend)
        main = (j / "ModMain.java").read_text()
        self.assertIn("new OvisArmorItem(OVIS_ARMOR_MATERIAL, ArmorItem.Type.HELMET", main); self.assertIn("import com.x.a3.gear.OvisArmorItem;", main)
        a = self.root / "src/main/resources/assets/a3"
        geo = json.loads((a / "geo/item/armor/ovis.geo.json").read_text())
        self.assertEqual(geo["minecraft:geometry"][0]["description"]["identifier"], "geometry.ovis_armor")
        self.assertEqual({b["name"] for b in geo["minecraft:geometry"][0]["bones"]}, set(__import__("mod_orchestra.armor3d", fromlist=["ARMOR_BONES"]).ARMOR_BONES))
        self.assertIn("animation.ovis_armor.idle", json.loads((a / "animations/item/armor/ovis.animation.json").read_text())["animations"])
        self.assertTrue((a / "textures/item/armor/ovis.png").is_file())
        self.assertIn("geckolib", (self.root / "gradle.properties").read_text()); self.assertIn("geckolib", json.loads((self.root / "src/main/resources/fabric.mod.json").read_text())["depends"])

    def test_designer_task_validation_and_install(self):
        from mod_orchestra.armor3d import request_armor3d, validate_armor3d_files, install_armor3d, TEMPLATE_DIR
        from mod_orchestra.dispatch import dispatch
        from mod_orchestra.provider import FakeProvider
        import shutil
        out = request_armor3d(self.store, "a3", "ovis", notes="samurai crest")
        self.assertEqual(out["task"], "a3:ARMOR3D:ovis"); self.assertTrue((self.root / "models/ovis_armor.bbmodel").is_file())
        self.assertIn("armorHead, armorBody", self.store.task_instructions(out["task"]))
        models = self.root / "models"
        geo = json.loads((TEMPLATE_DIR / "armor_template.geo.json").read_text()); geo["minecraft:geometry"][0]["description"]["identifier"] = "geometry.ovis_armor"
        (models / "ovis_armor.geo.json").write_text(json.dumps(geo))
        (models / "ovis_armor.animation.json").write_text(json.dumps({"format_version": "1.8.0", "animations": {"animation.ovis_armor.idle": {"loop": True, "bones": {}}}}))
        from mod_orchestra.textures import png_from_pixels
        (models / "ovis_armor.png").write_bytes(png_from_pixels(64, 64, [[(1, 2, 3, 255)] * 64 for _ in range(64)]))
        with self.assertRaisesRegex(InputError, "no render"):
            validate_armor3d_files(self.root, "ovis", ("helmet", "chestplate"))
        (models / "ovis_armor_render.png").write_bytes(png_from_pixels(16, 16, [[(1, 1, 1, 255)] * 16 for _ in range(16)]))
        info = validate_armor3d_files(self.root, "ovis", ("helmet", "chestplate")); self.assertEqual(info["cubes"], 8)
        # lose a required bone -> rejected
        geo2 = json.loads(json.dumps(geo)); geo2["minecraft:geometry"][0]["bones"] = [b for b in geo2["minecraft:geometry"][0]["bones"] if b["name"] != "armorBody"]
        (models / "ovis_armor.geo.json").write_text(json.dumps(geo2))
        with self.assertRaisesRegex(InputError, "lost required armor bones"):
            validate_armor3d_files(self.root, "ovis", ("helmet", "chestplate"))
        (models / "ovis_armor.geo.json").write_text(json.dumps(geo))
        h = {"task": out["task"], "status": "DONE", "scope": "s", "changed_files": [], "checks_run": [], "evidence": {"level": "STATIC", "pointer": "m"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "none"}
        res = dispatch(self.store, "a3", task_id=out["task"], provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))
        self.assertEqual(res["task_state"], "DONE", res.get("error"))
        self.assertEqual(len(res["handoff"]["armor3d"]["installed"]), 3); self.assertEqual(len(res["handoff"]["armor3d"]["previews"]), 1)
        self.assertEqual(json.loads((self.root / "src/main/resources/assets/a3/geo/item/armor/ovis.geo.json").read_text())["minecraft:geometry"][0]["description"]["identifier"], "geometry.ovis_armor")


@unittest.skipIf(__import__("os").name == "nt", "POSIX shell fixtures")
class GameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        from mod_orchestra.specedit import add_recipe, add_mob
        proj = workflow.new_project(self.store, name="G", mod_id="g_mod", package="com.x.g", idea="items: gem; blocks: gem ore; tab: G")
        add_recipe(self.store, "g_mod", recipe_id="gem_block", kind="shaped", result="gem_ore", pattern=["GG", "GG"], key={"G": "gem"})
        add_mob(self.store, "g_mod", identifier="gem_golem", label="Gem Golem")
        workflow.plan_project(self.store, "g_mod"); workflow.approve_spec(self.store, "g_mod"); workflow.generate_project(self.store, "g_mod")
        self.root = Path(proj["root"])

    def test_generated_gametest_class_and_wiring(self):
        src = (self.root / "src/main/java/com/x/g/gametest/ModGameTests.java").read_text()
        for needle in ("implements FabricGameTest", "itemsAreRegistered", 'id("gem")', "blocksPlaceAndStay", "recipesExist", 'byKey(id("gem_block"))', "mobsSpawn", "helper.spawn(ModMain.GEM_GOLEM", "modIsLoaded"):
            self.assertIn(needle, src, needle)
        fmj = json.loads((self.root / "src/main/resources/fabric.mod.json").read_text())
        self.assertEqual(fmj["entrypoints"]["fabric-gametest"], ["com.x.g.gametest.ModGameTests"])
        self.assertIn("runDir \"build/gametest\"", (self.root / "build.gradle").read_text())

    def test_parse_junit(self):
        from mod_orchestra.gametest import parse_junit
        x = self.root / "junit.xml"
        x.write_text('<testsuite tests="3" failures="1" errors="0"><testcase name="g_mod.itemsareregistered"/><testcase name="g_mod.mobsspawn"><failure message="no golem">boom</failure></testcase><testcase name="g_mod.modisloaded"/></testsuite>')
        r = parse_junit(x); self.assertEqual((r["tests"], r["failures"]), (3, 1)); self.assertEqual(r["failed"][0]["name"], "g_mod.mobsspawn")
        self.assertFalse(parse_junit(self.root / "nope.xml")["found"])

    def test_run_gametest_pass_and_fail(self):
        import stat
        from mod_orchestra import build as build_mod, gametest as gt
        from mod_orchestra.evidence import record_evidence, levels_for_current_source
        record_evidence(self.store, "g_mod", "BUILD_PASS", actor="controller", note="fake")
        with self.assertRaisesRegex(Exception, "required"):
            gt.run_gametest(self.store, "g_mod", "bogus")
        def fake_gradle(xml: str, code: int):
            f = Path(self.tmp.name) / f"gradle_{code}.sh"
            f.write_text(f"#!/bin/sh\nmkdir -p build/gametest\ncat > build/gametest/junit.xml <<'XML'\n{xml}\nXML\necho 'BUILD SUCCESSFUL'\nexit {code}\n")
            f.chmod(f.stat().st_mode | stat.S_IEXEC); return f
        good = '<testsuite tests="4" failures="0" errors="0"><testcase name="a"/><testcase name="b"/><testcase name="c"/><testcase name="d"/></testsuite>'
        bad = '<testsuite tests="4" failures="1" errors="0"><testcase name="a"/><testcase name="g_mod.mobsspawn"><failure message="Expected entity gem_golem">x</failure></testcase></testsuite>'
        a = gt.request_gametest(self.store, "g_mod"); self.store.decide_approval(a["id"], True)
        with patch.object(gt, "_gradle_launcher", return_value=fake_gradle(good, 0)):
            res = gt.run_gametest(self.store, "g_mod", a["id"])
        self.assertEqual(res["status"], "GAMETEST_PASS"); self.assertEqual(res["junit"]["tests"], 4)
        self.assertIn("GAMETEST_PASS", levels_for_current_source(self.store, "g_mod", self.root))
        a = gt.request_gametest(self.store, "g_mod"); self.store.decide_approval(a["id"], True)
        with patch.object(gt, "_gradle_launcher", return_value=fake_gradle(bad, 1)):
            res = gt.run_gametest(self.store, "g_mod", a["id"])
        self.assertEqual(res["status"], "GAMETEST_FAILED"); self.assertTrue(res["repair"]["task"].startswith("g_mod:REPAIR:"))
        self.assertIn("mobsspawn", self.store.task_instructions(res["repair"]["task"]) if hasattr(self.store, "task_instructions") else "mobsspawn")
