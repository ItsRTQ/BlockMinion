"""One change request across several Map cards: one coder task with every card's context, results recorded per card."""
import json
import unittest

from mod_orchestra.cli import dispatch as cli_dispatch, parser
from mod_orchestra.dispatch import dispatch
from mod_orchestra.modmap import mod_map, request_change, request_feature
from mod_orchestra.provider import FakeProvider
from mod_orchestra.validation import InputError

from test_art_requests import Base, handoff


class MultiCard(Base):
    def test_one_task_many_cards(self):
        other = request_feature(self.store, "s_mod", title="Ammo pouch", description="a pouch", acceptance=["holds ammo"])
        dispatch(self.store, "s_mod", task_id=other["task"], provider=FakeProvider(handoff(other["task"])))   # the pouch exists
        out = request_change(self.store, "s_mod", "acid_spit", "every weapon reloads from magazines with real ammo counts", ["ammo_pouch", "gem"])
        self.assertEqual(out["cards"], ["acid_spit", "ammo_pouch", "gem"]); self.assertEqual(out["task"], "s_mod:CHANGE:acid_spit+ammo_pouch+gem:1")
        brief = self.store.task_instructions(out["task"])
        self.assertIn("Change request across 3 feature cards", brief); self.assertIn("- `ammo_pouch` (custom): Ammo pouch", brief); self.assertIn("- `gem` (item)", brief)
        self.assertIn("change it once there rather than per card", brief); self.assertIn("every weapon reloads from magazines", brief)
        cards = {c["id"]: c for c in mod_map(self.store, "s_mod")["cards"]}
        for cid in ("acid_spit", "ammo_pouch", "gem"):
            self.assertIn(out["task"], [t["id"] for t in cards[cid]["open_tasks"]], f"{cid} shows the shared task")
        with self.assertRaisesRegex(InputError, "Unknown card"):
            request_change(self.store, "s_mod", "acid_spit", "x", ["nope"])
        # the coder reports per card; each custom card gets its own files and description, the spec card a CARD_CHANGED event
        h = json.loads(handoff(out["task"]).split("```handoff\n")[1].split("\n```")[0])
        h["cards"] = {"acid_spit": {"files": ["src/a.java"], "description": "spit reloads"}, "ammo_pouch": {"files": ["src/p.java"], "description": "pouch feeds magazines"}}
        res = dispatch(self.store, "s_mod", task_id=out["task"], provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))
        self.assertEqual(res["task_state"], "DONE", res.get("error"))
        cards = {c["id"]: c for c in mod_map(self.store, "s_mod")["cards"]}
        self.assertEqual((cards["acid_spit"]["description"], cards["ammo_pouch"]["description"]), ("spit reloads", "pouch feeds magazines"))
        self.assertIn("src/p.java", cards["ammo_pouch"]["files"])
        changed = [e["payload"]["card"] for e in self.store.events("s_mod") if e["kind"] == "CARD_CHANGED"]
        self.assertIn("gem", changed)

    def test_cli_and_single_card_unchanged(self):
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "change", "s_mod", "--cards", "acid_spit", "gem", "--request", "x"]))
        self.assertEqual(out["cards"], ["acid_spit", "gem"])
        one = request_change(self.store, "s_mod", "acid_spit", "only this one")
        self.assertNotIn("cards", one); self.assertTrue(one["task"].startswith("s_mod:CHANGE:acid_spit:"))


if __name__ == "__main__":
    unittest.main()
