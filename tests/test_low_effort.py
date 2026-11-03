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
