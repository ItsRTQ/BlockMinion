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
