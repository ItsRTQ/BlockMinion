"""Pointing at cards from the chat with @card_id: the coordinator is told where to start, and only an explicit mention does that."""
import unittest

from mod_orchestra import chat, mapmeta
from mod_orchestra.dispatch import dispatch

from test_art_requests import Base
from test_chat import turn

CARDS = {"ak47": {"kind": "item", "title": "AK47"}, "ak47_ammo": {"kind": "item", "title": "AK47 Ammo"}, "firearm_ballistics": {"kind": "custom", "title": "Firearm Ballistics"},
         "vanilla:minecraft:iron_ingot": {"kind": "vanilla", "title": "iron_ingot"}, "__tab": {"kind": "tab", "title": "Creative tab"}, "Barrett_M82": {"kind": "item", "title": "Barrett M82"}}


class Mentions(Base):
    def ids(self, text):
        return [c["id"] for c in chat.mentions(CARDS, text)]

    def test_a_card_is_found_by_id_any_case_or_by_its_title_and_nothing_else_is_a_mention(self):
        self.assertEqual(self.ids("make @ak47 louder, and @AK47_Ammo cheaper."), ["ak47", "ak47_ammo"])
        self.assertEqual(self.ids("(@firearm_ballistics), @ak47's recoil; @ak47"), ["firearm_ballistics", "ak47"], "once each, punctuation around it is fine")
        self.assertEqual(self.ids("@barrett_m82 and @Barrett_M82"), ["Barrett_M82"]); self.assertEqual(self.ids("uses @vanilla:minecraft:iron_ingot: yes"), ["vanilla:minecraft:iron_ingot"])
        self.assertEqual(self.ids("@Firearm_Ballistics"), ["firearm_ballistics"])
        for text in ("@Override public void tick()", "mail me at rtq@ak47.dev", "see @@ak47", "path/@ak47", "@", "@ ak47", "the ak47", "@__tab", "@ak4", "@everyone", ""):
            self.assertEqual(self.ids(text), [], text)
        self.assertEqual(len(chat.mentions({f"c{i}": {"kind": "item", "title": f"C{i}"} for i in range(40)}, " ".join(f"@c{i}" for i in range(40)))), chat.MAX_MENTIONS)

    def test_the_coordinator_is_told_what_the_newest_message_points_at_and_where_those_things_are(self):
        out = chat.send(self.store, "s_mod", "make @acid_spit hit harder. Also @Override is in my log and @nothing_here is not a card")
        self.assertEqual([c["id"] for c in out["cards"]], ["acid_spit"])
        brief = self.store.task_instructions(out["task"])
        self.assertIn("## What the user points at in the newest message (start here)", brief)
        block = brief.split("## What the user points at")[1].split("## The conversation")[0]
        self.assertIn("- `acid_spit` (custom):", block); self.assertIn("  files: ", block); self.assertIn("  relations: ", block)
        self.assertNotIn("Override", block); self.assertNotIn("nothing_here", block)
        self.assertIn("  the user points at: `acid_spit` (custom:", brief.split("## The conversation")[1])
        self.assertIn("it does not limit the work", brief)
        v = chat.view(self.store, "s_mod"); self.assertEqual(v["messages"][-1]["meta"]["cards"][0]["id"], "acid_spit")
        self.assertEqual([e["payload"]["cards"] for e in self.store.events("s_mod", 50) if e["kind"] == "CHAT_SENT"], [["acid_spit"]])
        # the next message points at nothing: the detail block is gone, the history still says what was pointed at before
        dispatch(self.store, "s_mod", task_id=out["task"], provider=turn(out["task"], "How much harder?"))
        nxt = self.store.task_instructions(chat.send(self.store, "s_mod", "twice as hard")["task"])
        self.assertNotIn("## What the user points at", nxt); self.assertIn("the user points at: `acid_spit`", nxt)

    def test_a_message_without_mentions_is_exactly_as_before_and_folders_and_tags_still_never_reach_the_agent(self):
        mapmeta.save(self.store, "s_mod", {"folders": {"op": {"id": "op", "name": "Overpowered Zzyzx", "parent": None, "mode": "manual", "rules": {}}}, "members": {"acid_spit": ["op"]},
                                           "tags": {"acid_spit": {"add": ["Qwertag"]}}})
        plain = self.store.task_instructions(chat.send(self.store, "s_mod", "make the spit hit harder")["task"])
        self.assertNotIn("What the user points at", plain); self.assertNotIn("the user points at:", plain)
        pointed = self.store.task_instructions(chat.send(self.store, "s_mod", "make @acid_spit hit harder")["task"])
        for secret in ("Overpowered Zzyzx", "Qwertag"):
            self.assertNotIn(secret, pointed, "pointing at a card sends the card, not how the map is organised")


if __name__ == "__main__":
    unittest.main()
