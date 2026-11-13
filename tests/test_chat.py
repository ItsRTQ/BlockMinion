"""The project's main panel: talk with the coordinator, see the plan, Launch."""
import json
import unittest

from mod_orchestra import chat
from mod_orchestra.cli import dispatch as cli_dispatch, parser
from mod_orchestra.dispatch import dispatch
from mod_orchestra.provider import FakeProvider
from mod_orchestra.state import StateError
from mod_orchestra.validation import InputError

from test_art_requests import Base, handoff


def turn(task, reply, plan="absent", status="DONE"):
    h = json.loads(handoff(task, status=status, card=False).split("```handoff\n")[1].split("\n```")[0])
    h["reply"] = reply
    if plan != "absent":
        h["plan"] = plan
    return FakeProvider("```handoff\n" + json.dumps(h) + "\n```")


class Chat(Base):
    def test_a_turn_records_the_reply_and_the_plan_and_launch_runs_it(self):
        out = chat.send(self.store, "s_mod", "I want the spit to leave an acid pool that hurts")
        brief = self.store.task_instructions(out["task"])
        self.assertIn("USER: I want the spit to leave an acid pool", brief); self.assertIn("## The project", brief); self.assertIn("(none yet)", brief)
        self.assertEqual(next(t for t in self.store.tasks("s_mod") if t["id"] == out["task"])["role"], "coordinator")
        v = chat.view(self.store, "s_mod"); self.assertTrue(v["thinking"]); self.assertEqual(v["messages"][-1]["role"], "user")
        plan = {"result": "The spitter's spit leaves a pool on the ground that damages anyone standing in it.",
                "steps": [{"step": 1, "action": "change", "card": "acid_spit", "text": "the glob leaves an acid pool entity for 5 s that deals 1 damage per second"}]}
        res = dispatch(self.store, "s_mod", task_id=out["task"], provider=turn(out["task"], "Got it. An acid pool for 5 seconds, 1 damage per second — does that match what you had in mind?", plan))
        self.assertEqual(res["task_state"], "DONE", res.get("error"))
        v = chat.view(self.store, "s_mod")
        self.assertFalse(v["thinking"]); self.assertEqual(v["messages"][-1]["role"], "coordinator"); self.assertIn("acid pool for 5 seconds", v["messages"][-1]["text"])
        self.assertEqual(v["plan"]["steps"][0]["action"], "change"); self.assertEqual(v["plan"]["problems"], []); self.assertIsNone(v["plan"]["launched"])
        # the next turn sees the plan; an absent plan field keeps it
        out2 = chat.send(self.store, "s_mod", "yes")
        self.assertIn('"action": "change"', self.store.task_instructions(out2["task"]))
        dispatch(self.store, "s_mod", task_id=out2["task"], provider=turn(out2["task"], "Great, press Launch when ready."))
        self.assertEqual(chat.view(self.store, "s_mod")["plan"]["steps"][0]["card"], "acid_spit")
        launched = chat.launch(self.store, "s_mod")
        self.assertEqual([a["action"] for a in launched["applied"]], ["change"]); self.assertTrue(launched["first"].startswith("s_mod:CHANGE:acid_spit:"))
        self.assertEqual(chat.view(self.store, "s_mod")["messages"][-1]["role"], "system")
        with self.assertRaisesRegex(StateError, "already launched"):
            chat.launch(self.store, "s_mod")

    def test_a_question_is_a_finished_turn_and_a_bad_plan_is_flagged_not_run(self):
        out = chat.send(self.store, "s_mod", "make the door reload")
        res = dispatch(self.store, "s_mod", task_id=out["task"], provider=turn(out["task"], "A door does not reload; did you mean the gun?", None, status="WAITING_USER"))
        self.assertEqual(res["task_state"], "DONE"); self.assertFalse(chat.view(self.store, "s_mod")["thinking"]); self.assertIsNone(chat.view(self.store, "s_mod")["plan"])
        out = chat.send(self.store, "s_mod", "the gun")
        dispatch(self.store, "s_mod", task_id=out["task"], provider=turn(out["task"], "ok", {"result": "x", "steps": [{"step": 1, "action": "animate", "kind": "item", "target": "gem", "anims": [{"name": "reload", "what": "x", "when": "y"}]},
                                                                                                                          {"step": 2, "action": "fly", "target": "x"}]}))
        plan = chat.view(self.store, "s_mod")["plan"]
        self.assertEqual(plan["problems"], ["step 1: 'gem' is not a 3D item (Make it 3D first)", "step 2: unknown action 'fly'"])
        with self.assertRaisesRegex(InputError, "cannot run as written"):
            chat.launch(self.store, "s_mod")
        chat.discard(self.store, "s_mod"); self.assertIsNone(chat.view(self.store, "s_mod")["plan"])
        with self.assertRaisesRegex(StateError, "no plan"):
            chat.launch(self.store, "s_mod")

    def test_cli(self):
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "chat", "s_mod", "hello"]))
        self.assertTrue(out["task"].startswith("s_mod:CHAT:"))
        self.assertEqual(cli_dispatch(parser().parse_args(["--state-db", str(self.db), "chat", "s_mod", "--show"]))["messages"][-1]["text"], "hello")
        with self.assertRaisesRegex(InputError, "Say something"):
            chat.send(self.store, "s_mod", "  ")


if __name__ == "__main__":
    unittest.main()


class Migration(unittest.TestCase):
    def test_an_existing_v8_database_gains_the_chat_table(self):
        import sqlite3, tempfile
        from pathlib import Path
        from mod_orchestra.state import MIGRATIONS, Store
        db = Path(tempfile.mkdtemp()) / "s.sqlite"
        con = sqlite3.connect(db)
        for version, _, sql in MIGRATIONS:
            if version > 8:
                break
            for st in (x.strip() for x in sql.split(";")):
                if st:
                    con.execute(st)
        con.execute("PRAGMA user_version=8"); con.commit(); con.close()
        store = Store(db)
        self.assertEqual(store.chat_messages("nope"), [])
        self.assertEqual(sqlite3.connect(db).execute("PRAGMA user_version").fetchone()[0], 9)
