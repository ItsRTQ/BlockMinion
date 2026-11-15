"""A launched plan in the chat: steps run in order, one at a time, each started by the user; the chat says what finished."""
import json
import unittest

from mod_orchestra import chat
from mod_orchestra.ask import apply_plan
from mod_orchestra.dispatch import dispatch
from mod_orchestra.provider import FakeProvider
from mod_orchestra.state import StateError

from test_art_requests import Base, handoff
from test_chat import turn


def worker(task, status="DONE", files=("src/main/java/com/x/s/A.java",)):
    h = json.loads(handoff(task, status=status).split("```handoff\n")[1].split("\n```")[0]); h["changed_files"] = list(files)
    return FakeProvider("```handoff\n" + json.dumps(h) + "\n```")


class Progress(Base):
    def plan(self, n=3, **first):
        steps = [{"step": i, "action": "change", "card": "acid_spit", "text": f"part {i} of the pool"} for i in range(1, n + 1)]
        steps[0] |= first
        out = chat.send(self.store, "s_mod", "an acid pool, in parts")
        dispatch(self.store, "s_mod", task_id=out["task"], provider=turn(out["task"], "Here is the plan.", {"result": "A pool.", "steps": steps}))
        return chat.launch(self.store, "s_mod")

    def prog(self):
        return chat.view(self.store, "s_mod")["plan"]["progress"]

    def states(self):
        return [s["status"] for s in self.prog()["steps"]]

    def notes(self):
        return [m["text"] for m in chat.view(self.store, "s_mod")["messages"] if (m.get("meta") or {}).get("plan_note")]

    def test_steps_wait_for_the_one_before_even_when_the_plan_named_no_order(self):
        launched = self.plan()
        t1, t2, t3 = (a["tasks"][0] for a in launched["applied"])
        self.assertEqual(self.states(), ["ready", "waiting", "waiting"])
        p = self.prog(); self.assertEqual((p["state"], p["done"], p["total"]), ("ready", 0, 3))
        self.assertEqual(p["steps"][0]["start"], t1); self.assertIsNone(p["steps"][1]["start"]); self.assertEqual(p["steps"][1]["waiting_for"], [1]); self.assertEqual(p["steps"][2]["waiting_for"], [2])
        # the store refuses it too, not only the screen: a step behind another cannot be dispatched from anywhere
        with self.assertRaises(StateError):
            dispatch(self.store, "s_mod", task_id=t2, provider=worker(t2))
        self.assertEqual(self.states(), ["ready", "waiting", "waiting"])
        self.assertIn("one at a time and in order", chat.view(self.store, "s_mod")["messages"][-1]["text"])

    def test_each_finished_step_is_announced_once_and_frees_only_the_next(self):
        launched = self.plan()
        t1, t2, t3 = (a["tasks"][0] for a in launched["applied"])
        dispatch(self.store, "s_mod", task_id=t1, provider=worker(t1))
        self.assertEqual(self.states(), ["done", "ready", "waiting"]); self.assertEqual(self.prog()["steps"][1]["start"], t2)
        self.assertEqual(self.notes(), ["Step 1 of 3 finished: 1 file changed\nStep 2 is ready: press Start in the plan when you want it to run."])
        chat.note_progress(self.store, "s_mod", t1); self.assertEqual(len(self.notes()), 1, "said once")
        chat.note_progress(self.store, "s_mod", "s_mod:SPEC"); self.assertEqual(len(self.notes()), 1, "a task outside the plan says nothing")
        dispatch(self.store, "s_mod", task_id=t2, provider=worker(t2, files=()))
        self.assertEqual(self.states(), ["done", "done", "ready"]); self.assertEqual(self.notes()[-1].splitlines()[0], "Step 2 of 3 finished.")
        dispatch(self.store, "s_mod", task_id=t3, provider=worker(t3))
        p = self.prog(); self.assertEqual((p["state"], p["done"]), ("done", 3))
        end = self.notes()[-1]
        self.assertIn("All 3 steps finished.", end); self.assertIn("nothing has been tried in the game yet", end)
        self.assertIn("- part 1 of the pool", end); self.assertIn("- part 3 of the pool", end); self.assertIn("Test in game", end)
        self.assertEqual(len(self.notes()), 4)
        self.assertEqual([e["kind"] for e in self.store.events("s_mod", 400)].count("PLAN_FINISHED"), 1)

    def test_a_step_that_stops_holds_the_rest_and_can_be_retried(self):
        launched = self.plan()
        t1, t2, _ = (a["tasks"][0] for a in launched["applied"])
        dispatch(self.store, "s_mod", task_id=t1, provider=FakeProvider("no handoff here"))
        p = self.prog(); self.assertEqual(p["state"], "stopped"); self.assertEqual(self.states(), ["stopped", "waiting", "waiting"])
        self.assertEqual(p["steps"][0]["retry"], t1); self.assertTrue(p["steps"][0]["error"]); self.assertIsNone(p["steps"][1]["start"])
        self.assertIn("Step 1 of 3 stopped:", self.notes()[-1]); self.assertIn("The steps after it wait", self.notes()[-1])
        self.store.requeue(t1, "retry from the plan")
        self.assertEqual(self.states(), ["ready", "waiting", "waiting"])
        dispatch(self.store, "s_mod", task_id=t1, provider=worker(t1))
        self.assertEqual(self.states(), ["done", "ready", "waiting"])

    def test_a_step_that_could_not_become_a_task_is_shown_and_the_next_still_waits_in_order(self):
        steps = [{"step": 1, "action": "change", "card": "acid_spit", "text": "one"}, {"step": 2, "action": "change", "card": "ghost_card", "text": "two"},
                 {"step": 3, "action": "change", "card": "acid_spit", "text": "three"}]
        out = apply_plan(self.store, "s_mod", "s_mod:CHAT:9", {"plan": chat.in_order(steps)})
        self.assertEqual([s["step"] for s in out["skipped"]], [2])
        t1, t3 = (a["tasks"][0] for a in out["applied"])
        states = {t["id"]: t["state"] for t in self.store.tasks("s_mod")}
        self.assertEqual((states[t1], states[t3]), ("READY", "BACKLOG"), "step 3 waits for step 1 through the step that was skipped")
        prog = chat.progress(self.store, "s_mod", {"launched": out, "steps": steps})
        self.assertEqual([(s["step"], s["status"]) for s in prog["steps"]], [(1, "ready"), (2, "skipped"), (3, "waiting")]); self.assertEqual(prog["total"], 2)

    def test_in_order_keeps_what_the_plan_said_and_adds_the_step_before(self):
        got = chat.in_order([{"step": 1, "action": "feature"}, {"step": 2, "action": "change"}, {"step": 5, "action": "change", "after": [1, "x"]}, {"action": "change", "after": [5]}])
        self.assertEqual([s["after"] for s in got], [[], [1], [1, 2], [5]])

    def test_a_plan_launched_before_this_existed_still_shows_where_it_stands(self):
        launched = self.plan(1)
        self.assertEqual(self.states(), ["ready"])
        dispatch(self.store, "s_mod", task_id=launched["first"], provider=worker(launched["first"]))
        self.assertEqual(self.prog()["state"], "done"); self.assertIn("All 1 step finished.", self.notes()[-1])
        self.assertIsNone(chat.progress(self.store, "s_mod", {"steps": [], "launched": None}))


if __name__ == "__main__":
    unittest.main()
