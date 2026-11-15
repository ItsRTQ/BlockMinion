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

    def test_a_folder_worth_of_cards_can_be_pointed_at_the_first_dozen_in_detail(self):
        cards = {f"c{i}": {"kind": "item", "title": f"C{i}"} for i in range(60)}
        got = chat.mentions(cards, " ".join(f"@c{i}" for i in range(60)))
        self.assertEqual(len(got), chat.MAX_MENTIONS); self.assertEqual(chat.MAX_MENTIONS, 40); self.assertEqual(chat.DETAILED, 12)
        block = "\n".join(chat._pointed_block(self.store, "s_mod", [{"id": "acid_spit", "kind": "custom", "title": "x"}] * 12 + [{"id": "spitter", "kind": "mob", "title": "Spitter"}, {"id": "ghost", "kind": "item", "title": "?"}]))
        self.assertIn("- and also (look them up when you need them): `spitter` (mob)", block); self.assertNotIn("ghost", block)

    def test_pointing_at_a_task_tells_the_coordinator_how_it_ended_and_where_its_log_is(self):
        from mod_orchestra.dispatch import dispatch as run
        from mod_orchestra.provider import FakeProvider
        from mod_orchestra.modmap import request_change
        from mod_orchestra.validation import InputError
        bad = request_change(self.store, "s_mod", "acid_spit", "make it hiss")["task"]
        run(self.store, "s_mod", task_id=bad, provider=FakeProvider("I did things but wrote no handoff"))
        out = chat.send(self.store, "s_mod", "what went wrong here?", task_ids=[bad])
        self.assertEqual([(t["id"], t["state"], t["role"]) for t in out["tasks"]], [(bad, "FAILED", "coder")])
        brief = self.store.task_instructions(out["task"])
        block = brief.split("## Tasks the user points at in the newest message")[1].split("## The conversation")[0]
        self.assertIn(f"- `{bad}` (coder):", block); self.assertIn("State: FAILED. It ended with:", block)
        self.assertRegex(block, r"the log of its last run: `\.mod-orchestra/runs/[^`]+\.log`"); self.assertNotIn(self.store.project("s_mod")["root"], block)
        self.assertIn(f"  the user points at these tasks: `{bad}`", brief); self.assertIn("You do not retry or skip anything yourself", brief)
        self.assertEqual(chat.view(self.store, "s_mod")["messages"][-1]["meta"]["tasks"][0]["id"], bad)
        only = chat.send(self.store, "s_mod", "", task_ids=[bad]); self.assertIn("USER: (no text", self.store.task_instructions(only["task"]))
        n = len(chat.view(self.store, "s_mod")["messages"])
        for wrong in (["s_mod:NOPE:1"], ["other:CHANGE:x:1"], [bad] + [f"s_mod:X:{i}" for i in range(9)]):
            with self.assertRaises(InputError):
                chat.send(self.store, "s_mod", "and this?", task_ids=wrong)
        self.assertEqual(len(chat.view(self.store, "s_mod")["messages"]), n, "a wrong task leaves no half message")

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
