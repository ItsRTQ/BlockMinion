"""Mod Map 2.0: the user's organisation of the map (folders, tags, positions) is view metadata.
It is validated and stored apart from the mod, survives reloads, and never reaches an agent."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import mapmeta, workflow
from mod_orchestra.capabilities import handoff as packet
from mod_orchestra.modmap import map_text, mod_map, request_change
from mod_orchestra.specedit import add_mob
from mod_orchestra.state import Store, StateError
from mod_orchestra.validation import InputError

MARK = "Overpowered Zzyzx Weapons"      # a folder name that would be an instruction if a coder ever read it
TAG = "Qwertag Instakill"


def folder(fid, name, parent=None, **extra):
    return {"id": fid, "name": name, "parent": parent, "mode": "manual", "rules": {}} | extra


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        workflow.new_project(self.store, name="Ovis", mod_id="ovis", package="com.x.ovis", idea="items: raw ovis, ovis ingot; blocks: ovis ore; tab: Ovis")
        add_mob(self.store, "ovis", identifier="cyborg_alien", label="Cyborg Alien", behavior="hostile", drops=["raw_ovis"])


class Normalize(Base):
    def test_a_project_from_before_folders_has_an_empty_organisation(self):
        self.assertEqual(mapmeta.load(self.store, "ovis"), mapmeta.empty())
        self.assertEqual(mapmeta.normalize({}), mapmeta.empty())

    def test_folders_nest_and_never_inside_themselves(self):
        ok = mapmeta.normalize({"folders": {"a": folder("a", "Weapons"), "b": folder("b", "Rifles", "a")}})
        self.assertEqual(ok["folders"]["b"]["parent"], "a")
        with self.assertRaisesRegex(InputError, "inside itself"):
            mapmeta.normalize({"folders": {"a": folder("a", "A", "b"), "b": folder("b", "B", "a")}})
        with self.assertRaisesRegex(InputError, "inside itself"):
            mapmeta.normalize({"folders": {"a": folder("a", "A", "a")}})
        with self.assertRaisesRegex(InputError, "does not exist"):
            mapmeta.normalize({"folders": {"a": folder("a", "A", "ghost")}})
        with self.assertRaisesRegex(InputError, "needs a name"):
            mapmeta.normalize({"folders": {"a": folder("a", "   ")}})
        with self.assertRaisesRegex(InputError, "mode"):
            mapmeta.normalize({"folders": {"a": folder("a", "A", mode="psychic")}})
        with self.assertRaisesRegex(InputError, "Bad folder id"):
            mapmeta.normalize({"folders": {"../x": folder("../x", "A")}})
        deep = {f"f{i}": folder(f"f{i}", f"F{i}", f"f{i - 1}" if i else None) for i in range(mapmeta.MAX_DEPTH + 1)}
        with self.assertRaisesRegex(InputError, "deep"):
            mapmeta.normalize({"folders": deep})

    def test_what_dangles_is_dropped_not_stored(self):
        m = mapmeta.normalize({"folders": {"a": folder("a", "A")}, "members": {"ak47": ["a", "gone", "a"], "m16": ["gone"]},
                               "excluded": {"ak47": ["auto:item", "gone"]}, "fpos": {"a": {"x": 1, "y": 2}, "gone": {"x": 1, "y": 2}, "auto:mob": {"x": 5.04, "y": 6}},
                               "pos": {"a": {"ak47": {"x": 3, "y": 4}, "bad": {"x": "no"}}, "gone": {"ak47": {"x": 1, "y": 1}}}})
        self.assertEqual(m["members"], {"ak47": ["a"]})
        self.assertEqual(m["excluded"], {"ak47": ["auto:item"]})
        self.assertEqual(m["fpos"], {"a": {"x": 1.0, "y": 2.0}, "auto:mob": {"x": 5.0, "y": 6.0}})
        self.assertEqual(m["pos"], {"a": {"ak47": {"x": 3.0, "y": 4.0}}})

    def test_tags_have_one_spelling(self):
        m = mapmeta.normalize({"tags": {"ak47": {"add": ["  Ranged ", "ranged", "RANGED", "Heavy   weapon", ""], "remove": ["Item", "ranged"]}}})
        self.assertEqual(m["tags"]["ak47"], {"add": ["Ranged", "Heavy weapon"], "remove": ["Item"]})
        self.assertEqual(mapmeta.tag_key("  Heavy   WEAPON "), "heavy weapon")

    def test_rules_and_prefs_keep_only_plain_values(self):
        m = mapmeta.normalize({"folders": {"a": folder("a", "A", mode="auto", rules={"kinds": ["mob", 5], "tags": ["Loot", "loot"], "words": ["ak"]})},
                               "prefs": {"filterMode": "dim", "hiddenKinds": ["vanilla"], "nested": {"x": 1}}})
        self.assertEqual(m["folders"]["a"]["rules"], {"kinds": ["mob"], "tags": ["Loot"], "words": ["ak"]})
        self.assertEqual(m["prefs"], {"filterMode": "dim", "hiddenKinds": ["vanilla"]})


class Stored(Base):
    def meta(self):
        return {"folders": {"op": folder("op", MARK), "r": folder("r", "Rifles", "op")}, "members": {"cyborg_alien": ["r"], "raw_ovis": ["op"]},
                "tags": {"cyborg_alien": {"add": [TAG]}}, "pos": {"r": {"cyborg_alien": {"x": 10, "y": 20}}}}

    def test_it_persists_and_the_event_carries_counts_only(self):
        saved = mapmeta.save(self.store, "ovis", self.meta())
        self.assertEqual(mapmeta.load(self.store, "ovis"), saved)
        self.assertEqual(Store(self.store.path).get_setting("ovis", "map_meta")["folders"]["op"]["name"], MARK)   # a fresh connection: it is on disk
        ev = [e for e in self.store.events("ovis") if e["kind"] == "MAP_ORGANIZED"]
        self.assertEqual(ev[0]["payload"], {"folders": 2, "filed_cards": 2, "tagged_cards": 1})
        self.assertNotIn(MARK, json.dumps(self.store.events("ovis", 500)))
        with self.assertRaises(StateError):
            mapmeta.save(self.store, "nope", self.meta())
        with self.assertRaises(InputError):
            mapmeta.save(self.store, "ovis", "folders please")

    def test_organising_the_map_changes_nothing_in_the_mod(self):
        before = mod_map(self.store, "ovis"); spec = json.dumps(self.store.project("ovis")["spec"], sort_keys=True)
        mapmeta.save(self.store, "ovis", self.meta())
        mapmeta.save(self.store, "ovis", {"folders": {}})          # every folder deleted again
        after = mod_map(self.store, "ovis")
        self.assertEqual([c["id"] for c in after["cards"]], [c["id"] for c in before["cards"]])
        self.assertEqual(after["edges"], before["edges"])
        self.assertEqual(json.dumps(self.store.project("ovis")["spec"], sort_keys=True), spec)
        self.assertNotIn("meta", after)                                    # the graph the agents read has no organisation in it

    def test_folders_and_tags_never_reach_an_agent(self):
        workflow.plan_project(self.store, "ovis"); workflow.approve_spec(self.store, "ovis"); workflow.generate_project(self.store, "ovis")
        mapmeta.save(self.store, "ovis", self.meta())
        out = request_change(self.store, "ovis", "cyborg_alien", "make it walk faster")
        seen = map_text(self.store, "ovis") + self.store.task_instructions(out["task"]) + str(packet(self.store, "ovis", out["task"]))
        for secret in (MARK, TAG, "Rifles"):
            self.assertNotIn(secret, seen)
        self.assertIn("make it walk faster", seen)


if __name__ == "__main__":
    unittest.main()
