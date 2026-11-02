"""Mod map: derived cards and edges from the spec, custom feature cards, change/feature tasks, agent text."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.dispatch import dispatch
from mod_orchestra.modmap import apply_card_handoff, create_feature_card, derived_cards, map_text, mod_map, request_change, request_feature, update_card
from mod_orchestra.provider import FakeProvider
from mod_orchestra.specedit import add_drop, add_material, add_mob, add_recipe
from mod_orchestra.state import Store, StateError
from mod_orchestra.validation import InputError


def handoff(task, **extra):
    h = {"task": task, "status": "DONE", "scope": "s", "changed_files": [], "checks_run": [{"command": "./gradlew build", "exit_code": 0}],
         "evidence": {"level": "BUILD_PASS", "pointer": "jar"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "none"} | extra
    return "```handoff\n" + json.dumps(h) + "\n```"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        workflow.new_project(self.store, name="Ovis", mod_id="ovis", package="com.x.ovis", idea="items: raw ovis, ovis ingot; blocks: ovis ore; tab: Ovis")
        add_recipe(self.store, "ovis", recipe_id="ovis_ingot", kind="smelting", result="ovis_ingot", ingredients=["raw_ovis"], experience=0.9)
        add_drop(self.store, "ovis", block="ovis_ore", item="raw_ovis", count_min=1, count_max=2, fortune=True)
        add_material(self.store, "ovis", identifier="ovisium", label="Ovisium", ingredient="ovis_ingot", tools=["sword"], armor=["helmet"])
        add_mob(self.store, "ovis", identifier="cyborg_alien", label="Cyborg Alien", behavior="hostile", drops=["raw_ovis"])


class Derived(Base):
    def test_cards_and_edges_follow_the_spec(self):
        cards, edges = derived_cards(self.store.project("ovis")["spec"], None)
        self.assertEqual({c["kind"] for c in cards.values()}, {"item", "block", "material", "mob", "tab"})
        rel = {(e["from"], e["kind"], e["to"]) for e in edges}
        for want in [("ovis_ore", "drops", "raw_ovis"), ("raw_ovis", "smelts_into", "ovis_ingot"), ("ovis_ingot", "made_of", "ovisium"), ("cyborg_alien", "drops_on_death", "raw_ovis")]:
            self.assertIn(want, rel)
        self.assertEqual([p["id"] for p in cards["ovisium"]["pieces"]], ["ovisium_sword", "ovisium_helmet"])

    def test_vanilla_references_become_light_nodes(self):
        add_recipe(self.store, "ovis", recipe_id="stick_thing", kind="shapeless", result="raw_ovis", ingredients=["minecraft:stick"])
        cards, edges = derived_cards(self.store.project("ovis")["spec"], None)
        self.assertEqual(cards["vanilla:minecraft:stick"]["kind"], "vanilla")
        self.assertIn(("vanilla:minecraft:stick", "crafts", "raw_ovis"), {(e["from"], e["kind"], e["to"]) for e in edges})

    def test_map_text_is_in_every_worker_packet(self):
        workflow.plan_project(self.store, "ovis"); workflow.approve_spec(self.store, "ovis"); workflow.generate_project(self.store, "ovis")
        txt = map_text(self.store, "ovis")
        self.assertIn("## Mod map", txt); self.assertIn("ovis_ore --drops (1-2 fortune)--> raw_ovis", txt)
        from mod_orchestra.capabilities import handoff as packet
        self.assertIn("## Mod map", packet(self.store, "ovis", "ovis:MODEL:cyborg_alien"))


class CustomCards(Base):
    def setUp(self):
        super().setUp()
        workflow.plan_project(self.store, "ovis"); workflow.approve_spec(self.store, "ovis"); workflow.generate_project(self.store, "ovis")

    def test_feature_request_creates_card_and_coder_task_then_handoff_updates_card(self):
        out = request_feature(self.store, "ovis", title="Ovis Backpack", description="Right-click opens a 27-slot inventory.", acceptance=["opens on right click", "items persist"], derived_from=["ovis_ingot"])
        self.assertEqual(out["card"]["id"], "ovis_backpack"); self.assertEqual(out["task"], "ovis:FEATURE:ovis_backpack")
        instr = self.store.task_instructions(out["task"]); self.assertIn("27-slot", instr); self.assertIn("Builds on: ovis_ingot", instr); self.assertIn("`card` object", instr)
        m = mod_map(self.store, "ovis"); card = next(c for c in m["cards"] if c["id"] == "ovis_backpack")
        self.assertEqual(card["status"], "planned"); self.assertEqual([t["id"] for t in card["open_tasks"]], [out["task"]])
        self.assertIn(("ovis_ingot", "uses", "ovis_backpack"), {(e["from"], e["kind"], e["to"]) for e in m["edges"]})
        fake = FakeProvider(handoff(out["task"], card={"files": ["src/main/java/com/x/ovis/BackpackItem.java"], "description": "Backpack with a persistent 27-slot container.", "produces": ["ovis_backpack_item"]}))
        res = dispatch(self.store, "ovis", task_id=out["task"], provider=fake)
        self.assertEqual(res["task_state"], "DONE"); self.assertIn("## Mod map", fake.envelopes[0].packet)
        card = next(c for c in mod_map(self.store, "ovis")["cards"] if c["id"] == "ovis_backpack")
        self.assertEqual(card["status"], "generated"); self.assertEqual(card["files"], ["src/main/java/com/x/ovis/BackpackItem.java"]); self.assertIn("persistent", card["description"])
        self.assertEqual(card["open_tasks"], [])
        with self.assertRaisesRegex(InputError, "already exists"):
            create_feature_card(self.store, "ovis", title="Ovis Backpack", description="x", acceptance=[])

    def test_change_request_on_derived_card_carries_its_files_and_relations(self):
        out = request_change(self.store, "ovis", "ovisium", "1500 durability instead of 500")
        self.assertEqual(out["task"], "ovis:CHANGE:ovisium:1")
        instr = self.store.task_instructions(out["task"])
        self.assertIn("OvisiumTier.java", instr); self.assertIn("ovis_ingot --made of--> ovisium", instr); self.assertIn("REQUESTED CHANGE:", instr); self.assertIn("generated from the spec", instr)
        with self.assertRaisesRegex(InputError, "Unknown card"):
            request_change(self.store, "ovis", "vanilla:minecraft:stick", "x")
        with self.assertRaisesRegex(InputError, "Describe the change"):
            request_change(self.store, "ovis", "ovisium", "  ")
        res = dispatch(self.store, "ovis", task_id=out["task"], provider=FakeProvider(handoff(out["task"], card={"files": ["src/main/java/com/x/ovis/gear/OvisiumTier.java"], "description": "durability 1500"})))
        self.assertEqual(res["task_state"], "DONE")
        self.assertIn("CARD_CHANGED", [e["kind"] for e in self.store.events("ovis")])
        self.assertNotEqual(next(t["state"] for t in self.store.tasks("ovis") if t["id"] == "ovis:BUILD"), "DONE")

    def test_update_card_validation_and_layout_setting(self):
        create_feature_card(self.store, "ovis", title="Minimap", description="A corner minimap.", acceptance=[])
        c = update_card(self.store, "ovis", "minimap", by="user", status="verified", note="seen in game")
        self.assertEqual(c["status"], "verified"); self.assertEqual(c["history"][-1]["what"], "seen in game")
        with self.assertRaisesRegex(InputError, "status must be"):
            update_card(self.store, "ovis", "minimap", by="user", status="done")
        with self.assertRaisesRegex(InputError, "Unknown custom card"):
            update_card(self.store, "ovis", "ovisium", by="user", description="x")
        self.store.set_setting("ovis", "map_layout", {"minimap": {"x": 10, "y": 20}})
        self.assertEqual(mod_map(self.store, "ovis")["layout"]["minimap"], {"x": 10, "y": 20})


if __name__ == "__main__":
    unittest.main()
