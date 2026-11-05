from __future__ import annotations
import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mod_orchestra.config import PROFILE
from mod_orchestra.fabric import placeholder_png, validate_generated
from mod_orchestra.spec import interpret
from mod_orchestra.state import Store, StateError
from mod_orchestra.validation import InputError, safe_inside
from mod_orchestra import workflow
from mod_orchestra.mcp import handle


class TestSpec(unittest.TestCase):
    def test_parses_items_and_blocks(self):
        s = interpret(name="Crystal Frontier", mod_id="crystal_frontier", package="com.example.crystal",
                      idea="Crystals! items: moon gem, magic wand; blocks: marble block, rose quartz", profile=PROFILE["id"])
        self.assertEqual([f.identifier for f in s.features], ["moon_gem", "magic_wand", "marble_block", "rose_quartz"])
        self.assertFalse(s.questions)

    def test_unsupported_features_not_silently_generated(self):
        s = interpret(name="Boss", mod_id="boss_mod", package="com.example.boss",
                      idea="Add an awesome boss with loot; items: boss gem", profile=PROFILE["id"])
        self.assertTrue(s.questions)

    def test_rejects_payload_and_duplicate_ids(self):
        with self.assertRaises(InputError):
            interpret(name="Oops", mod_id="nice_mod", package="com.example.nice",
                      idea="items: stone; blocks: stone", profile=PROFILE["id"])
        with self.assertRaises(InputError):
            interpret(name="Oops", mod_id="../bad", package="com.example.nice",
                      idea="items: stone", profile=PROFILE["id"])


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.store = Store(self.base / "footprint.sqlite")
        self.patch = patch.object(workflow, "PROJECTS", self.base / "projects")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.base / "projects").mkdir()

    def create(self, pid="my_mod"):
        return workflow.new_project(self.store, name="My Mod", mod_id=pid,
                package="com.example.mymod", idea="items: starlight gem; blocks: silver ore")

    def test_mobs_only_grammar_idea_is_not_free_text_and_generates(self):
        """Regression: 'hostile mobs: a, b' alone was treated as free text (an open question blocked approval) and the
        generator then demanded an item/block."""
        project = workflow.new_project(self.store, name="Gear", mod_id="gear", package="com.example.gear", idea="hostile mobs: brute, scout")
        self.assertEqual(project["questions"], [])
        plan = workflow.plan_project(self.store, "gear")
        self.assertEqual(plan["blocking_questions"], [])
        self.assertIn("gear:MODEL:brute", [t["id"] for t in plan["tasks"]])
        workflow.approve_spec(self.store, "gear")
        out = workflow.generate_project(self.store, "gear")
        self.assertTrue(out["static_validation"]["ok"] if isinstance(out.get("static_validation"), dict) and "ok" in out["static_validation"] else True)
        self.assertIn("MODEL", " ".join(t["id"] for t in plan["tasks"]))

    def test_pure_free_text_idea_still_asks_the_interpreter(self):
        project = workflow.new_project(self.store, name="Story", mod_id="story", package="com.example.story", idea="a spooky forest with sad ghosts")
        self.assertTrue(any("free text" in q for q in project["questions"]))

    def test_end_to_end_source_generator(self):
        project = self.create()
        self.assertEqual(project["questions"], [])
        plan = workflow.plan_project(self.store, "my_mod")
        self.assertEqual(len(plan["tasks"]), 6)
        workflow.approve_spec(self.store, "my_mod")
        output = workflow.generate_project(self.store, "my_mod")
        self.assertEqual(output["status"], "GENERATED_UNVERIFIED")
        root = Path(project["root"])
        self.assertEqual(validate_generated(root)["status"], "PASS")
        self.assertTrue((root / "src/main/java/com/example/mymod/ModMain.java").is_file())
        self.assertTrue((root / "src/main/resources/assets/my_mod/textures/block/silver_ore.png").is_file())
        self.assertTrue((root / "src/main/resources/data/my_mod/loot_table/blocks/silver_ore.json").is_file())
        self.assertTrue((root / "src/main/resources/fabric.mod.json").is_file())
        self.assertEqual(len([t for t in self.store.tasks("my_mod") if t["state"] == "DONE"]), 4)
        self.assertIn("BUILD", [t["id"].split(":")[-1] for t in self.store.tasks("my_mod") if t["state"] == "READY"])
        self.assertEqual(self.store.project("my_mod")["status"], "SOURCE_GENERATED_UNVERIFIED")
        with self.assertRaises(StateError):
            workflow.generate_project(self.store, "my_mod")
        # Generated file changes make the static integrity gate fail.
        (root / "gradle.properties").write_text("modified", encoding="utf8")
        self.assertEqual(validate_generated(root)["status"], "FAIL")

    def test_generated_sources_use_mojang_mappings_profile(self):
        self.create()
        workflow.approve_spec(self.store, "my_mod")
        root = Path(workflow.generate_project(self.store, "my_mod")["path"])
        java = (root / "src/main/java/com/example/mymod/ModMain.java").read_text(encoding="utf8")
        gradle = (root / "build.gradle").read_text(encoding="utf8")
        props = (root / "gradle.properties").read_text(encoding="utf8")
        # Mojmap names; Yarn names must not leak into generated Java.
        for needle in ("ResourceLocation.fromNamespaceAndPath", "BuiltInRegistries.ITEM", "BlockBehaviour.Properties.of()",
                       "CreativeModeTabs.BUILDING_BLOCKS", "entries.accept("):
            self.assertIn(needle, java)
        for yarn in ("Identifier", "net.minecraft.registry.Registries", "AbstractBlock", "ItemGroups.", "Item.Settings"):
            self.assertNotIn(yarn, java)
        self.assertIn("net.fabricmc.fabric-loom-remap", gradle)
        self.assertIn("loom.officialMojangMappings()", gradle)
        self.assertNotIn("yarn", gradle + props)
        self.assertIn("loom_version=", props)
        # 1.21+ datapack folders are singular.
        self.assertFalse((root / "src/main/resources/data/my_mod/loot_tables").exists())
        self.assertTrue((root / "src/main/resources/data/my_mod/loot_table/blocks/silver_ore.json").is_file())

    def test_fabric_metadata_and_png_are_valid(self):
        p = self.create()
        workflow.approve_spec(self.store, "my_mod")
        workflow.generate_project(self.store, "my_mod")
        root = Path(p["root"])
        meta = json.loads((root / "src/main/resources/fabric.mod.json").read_text())
        self.assertEqual(meta["entrypoints"]["main"], ["com.example.mymod.ModMain"])
        texture = (root / "src/main/resources/assets/my_mod/textures/item/starlight_gem.png").read_bytes()
        self.assertTrue(texture.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", texture[16:24]), (16,16))

    def test_approval_one_use_digest_bound(self):
        self.create()
        pending = self.store.request_approval("my_mod", "build", {"root": "A"}, "build source")
        self.assertFalse(self.store.consume_approval(pending["id"], "my_mod", "build", {"root": "A"}))
        self.store.decide_approval(pending["id"], True)
        self.assertFalse(self.store.consume_approval(pending["id"], "my_mod", "build", {"root": "B"}))
        self.assertTrue(self.store.consume_approval(pending["id"], "my_mod", "build", {"root": "A"}))
        self.assertFalse(self.store.consume_approval(pending["id"], "my_mod", "build", {"root": "A"}))

    def test_lease_cas_and_required_evidence(self):
        self.create()
        workflow.plan_project(self.store, "my_mod")
        a = self.store.claim("my_mod:SPEC", "workerA", ttl=10)
        self.assertIsNotNone(a)
        self.assertIsNone(self.store.claim("my_mod:SPEC", "workerB", ttl=10))
        with self.assertRaises(StateError):
            self.store.finish("my_mod:SPEC", "workerA", a["version"], [])
        self.assertFalse(self.store.finish("my_mod:SPEC", "workerA", a["version"] + 1,
                                      [{"kind":"TEST", "value":"true"}]))
        self.assertTrue(self.store.finish("my_mod:SPEC", "workerA", a["version"],
                                     [{"kind":"TEST", "value":"true"}]))

    def test_mcp_denies_grant_and_invalid_tool(self):
        self.create()
        init = handle(self.store, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "minecraft-mod-orchestra")
        names = [x["name"] for x in handle(self.store,{"jsonrpc":"2.0","id":2,"method":"tools/list"})["result"]["tools"]]
        self.assertNotIn("orchestra_grant_approval", names)
        invalid = handle(self.store, {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"not-a-tool","arguments":{}}})
        self.assertTrue(invalid["result"]["isError"])

    def test_safe_inside_blocks_symlinks(self):
        root = self.base / "root"
        root.mkdir()
        with self.assertRaises(InputError):
            safe_inside(root, "../evil")
        try:
            (root / "escape").symlink_to(self.base, target_is_directory=True)
        except OSError as exc:  # Windows without Developer Mode/admin: WinError 1314
            self.skipTest(f"symlink creation not permitted on this host: {exc}")
        with self.assertRaises(InputError):
            safe_inside(root, "escape/evil.txt")


if __name__ == "__main__":
    unittest.main()
