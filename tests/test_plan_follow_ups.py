"""Work that a step's own work calls for is part of that step: the plan shows it, Start runs it, the next step waits."""
import unittest

import test_item3d as t3
from mod_orchestra import chat
from mod_orchestra.dispatch import dispatch
from mod_orchestra.provider import FakeProvider

from test_art_requests import ASSET, GLOB, Base, handoff, png
from test_chat import turn


def planned(case, pid, plan):
    out = chat.send(case.store, pid, "go")
    res = dispatch(case.store, pid, task_id=out["task"], provider=turn(out["task"], "Here is the plan.", plan))
    case.assertEqual(res["task_state"], "DONE", res.get("error"))
    case.assertEqual(chat.view(case.store, pid)["plan"]["problems"], [])
    launched = chat.launch(case.store, pid)
    case.assertEqual(launched["skipped"], [])
    return [a["tasks"][0] for a in launched["applied"]]


def steps(case, pid):
    return {s["step"]: s for s in chat.progress(case.store, pid, chat.current_plan(case.store, pid))["steps"]}


def said(case, pid):
    return [m["text"] for m in chat.view(case.store, pid)["messages"] if m["role"] == "system"]


class A3DProjectileFromTheChat(t3.Base):
    """What the user met: the designer delivered the model, the step read done, and the game still drew the sprite,
    because the coder task that switches the renderer was born outside the plan and nothing offered to run it."""
    SPRITE = t3.Projectile.SPRITE
    deliver_p = t3.Projectile.deliver_p

    def setUp(self):
        super().setUp()
        self.store.add_event("m_mod", "controller", "ART_REQUESTED", {"task": "m_mod:ART:acid_spit", "card": "acid_spit", "assets": [
            {"id": "acid_glob", "kind": "projectile", "path": self.SPRITE, "size": [16, 16], "for": ["moon_beast"], "what": "a glob of acid the beast spits"}]})

    def state(self, tid):
        return next(t["state"] for t in self.store.tasks("m_mod") if t["id"] == tid)

    def test_the_step_is_not_done_until_the_game_draws_the_model(self):
        model, change = planned(self, "m_mod", {"result": "The glob flies in 3D.", "steps": [
            {"step": 1, "action": "make_3d", "kind": "projectile", "target": "acid_glob", "text": "spiky"},
            {"step": 2, "action": "change", "card": "moon_gem", "text": "it shines a little"}]})
        self.assertIn(":PROJ3D:", model); self.assertEqual(self.state(change), "BACKLOG")
        self.deliver_p()
        self.assertEqual(dispatch(self.store, "m_mod", task_id=model, provider=FakeProvider(t3.handoff(model)))["task_state"], "DONE")
        wire = self.tasks("PROJ3DWIRE")[0]["id"]
        s = steps(self, "m_mod")
        self.assertEqual([t["id"] for t in s[1]["tasks"]], [model, wire], "the coder task that makes the game draw it joined the step")
        self.assertEqual((s[1]["status"], s[1]["start"], s[1]["done_tasks"]), ("ready", wire, 1), "and Start in the plan runs it")
        self.assertEqual((s[2]["status"], s[2]["waiting_for"]), ("waiting", [1])); self.assertEqual(self.state(change), "BACKLOG", "the next step still waits")
        talk = said(self, "m_mod")
        self.assertIn("Step 1 of 2: 1 of 2 parts finished. Press Start in the plan for the next part.", talk[-1])
        self.assertFalse(any("Step 1 of 2 finished" in m for m in talk), "nobody is told a step finished with half of it not started")
        grew = [e["payload"] for e in self.store.events("m_mod", 80) if e["kind"] == "PLAN_STEP_GREW"]
        self.assertEqual(grew, [{"step": 1, "after": model, "tasks": [wire]}])
        out = dispatch(self.store, "m_mod", task_id=wire, provider=FakeProvider(handoff(wire, card=False)))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        s = steps(self, "m_mod")
        self.assertEqual(s[1]["status"], "done"); self.assertEqual((s[2]["status"], s[2]["start"]), ("ready", change)); self.assertEqual(self.state(change), "READY")
        self.assertIn("Step 1 of 2 finished", said(self, "m_mod")[-1]); self.assertIn("Step 2 is ready", said(self, "m_mod")[-1])

    def test_a_projectile_without_art_says_what_to_plan_first(self):
        from mod_orchestra import made, model3d
        from mod_orchestra.ask import project_context
        from mod_orchestra.validation import InputError
        made.record_art(self.store, "m_mod", "acid_spit", [{"id": "web_ball", "kind": "projectile", "what": "a ball of web", "for": ["moon_beast"]}])
        self.assertEqual(model3d.projectiles_without_art(self.store, "m_mod"), {"web_ball": "acid_spit"})
        context = project_context(self.store, "m_mod")
        self.assertIn("projectiles with art of their own (can be made 3D; animated once 3D): acid_glob", context)
        self.assertIn("made things without art of their own (art_pass on their feature first): web_ball (feature acid_spit)", context)
        brief = self.store.task_instructions(chat.send(self.store, "m_mod", "make the web ball 3D")["task"])
        self.assertIn("plan the `art_pass` of its feature alone", brief); self.assertIn("web_ball (feature acid_spit)", brief)
        out = chat.send(self.store, "m_mod", "again")
        plan = {"result": "x", "steps": [{"step": 1, "action": "make_3d", "kind": "projectile", "target": "web_ball", "text": ""},
                                         {"step": 2, "action": "make_3d", "kind": "projectile", "target": "nothing_like_it", "text": ""},
                                         {"step": 3, "action": "make_3d", "kind": "projectile", "target": "acid_glob", "text": ""}]}
        dispatch(self.store, "m_mod", task_id=out["task"], provider=turn(out["task"], "ok", plan))
        problems = chat.view(self.store, "m_mod")["plan"]["problems"]
        self.assertEqual(len(problems), 2)
        self.assertIn("step 1: 'web_ball' has no art of its own yet", problems[0]); self.assertIn("plan `art_pass` for its feature `acid_spit` first", problems[0])
        self.assertIn("step 2: 'nothing_like_it' is not a projectile with its own art (projectiles that have it: acid_glob", problems[1]); self.assertIn("must be adopted first", problems[1])
        with self.assertRaisesRegex(InputError, "has no art of its own yet"):
            model3d.request_proj3d(self.store, "m_mod", "web_ball")

    def test_outside_a_plan_nothing_changes(self):
        from mod_orchestra import model3d
        tid = model3d.request_proj3d(self.store, "m_mod", "acid_glob")["task"]
        self.deliver_p()
        self.assertEqual(dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(t3.handoff(tid)))["task_state"], "DONE")
        self.assertEqual(self.state(self.tasks("PROJ3DWIRE")[0]["id"]), "READY")
        self.assertEqual([e for e in self.store.events("m_mod", 80) if e["kind"] in ("PLAN_STEP_GREW", "PLAN_NOTE_FAILED")], [])
        self.assertEqual(chat.adopt_follow_ups(self.store, "m_mod", tid, ["m_mod:NOPE"]), [])


class ArtACoderAskedFor(Base):
    def test_painting_and_placing_the_art_are_parts_of_the_step_that_asked(self):
        first, second = planned(self, "s_mod", {"result": "The spit looks like acid.", "steps": [
            {"step": 1, "action": "change", "card": "acid_spit", "text": "the glob looks like acid"},
            {"step": 2, "action": "change", "card": "spitter", "text": "a little faster"}]})
        self.placeholder()
        self.coder_done([GLOB], task=first)
        art, wire = "s_mod:ART:acid_spit", "s_mod:ARTWIRE:acid_spit"
        s = steps(self, "s_mod")
        self.assertEqual([t["id"] for t in s[1]["tasks"]], [first, art, wire]); self.assertEqual((s[1]["status"], s[1]["start"]), ("ready", art))
        self.assertEqual(self.task(second)["state"], "BACKLOG"); self.assertEqual(s[2]["waiting_for"], [1])
        self.assertIn("Step 1 of 2: 1 of 3 parts finished", said(self, "s_mod")[-1])
        (self.ws / "models/art").mkdir(parents=True, exist_ok=True)
        (self.ws / "models/art/acid_glob.png").write_bytes(png(16, 16, ((40, 160, 40, 255), (120, 230, 90, 255), (20, 70, 20, 255), (0, 0, 0, 0))))
        self.assertEqual(dispatch(self.store, "s_mod", task_id=art, provider=FakeProvider(handoff(art, card=False)))["task_state"], "DONE")
        s = steps(self, "s_mod"); self.assertEqual((s[1]["status"], s[1]["start"]), ("ready", wire)); self.assertEqual(self.task(second)["state"], "BACKLOG")
        self.assertEqual(dispatch(self.store, "s_mod", task_id=wire, provider=FakeProvider(handoff(wire, card=False)))["task_state"], "DONE")
        s = steps(self, "s_mod"); self.assertEqual(s[1]["status"], "done"); self.assertEqual(self.task(second)["state"], "READY")
        self.assertEqual(len([m for m in said(self, "s_mod") if "Step 1 of 2 finished" in m]), 1)

    def test_skipping_the_step_drops_its_unfinished_parts_and_frees_the_next(self):
        first, second = planned(self, "s_mod", {"result": "x", "steps": [
            {"step": 1, "action": "change", "card": "acid_spit", "text": "the glob looks like acid"},
            {"step": 2, "action": "change", "card": "spitter", "text": "a little faster"}]})
        self.placeholder(); self.coder_done([GLOB], task=first)
        chat.skip_step(self.store, "s_mod", 1)
        self.assertEqual((self.task("s_mod:ART:acid_spit")["state"], self.task("s_mod:ARTWIRE:acid_spit")["state"]), ("CANCELLED", "CANCELLED"))
        self.assertEqual(self.task(second)["state"], "READY")

    def test_a_gate_that_is_the_users_never_joins_a_step(self):
        first, _ = planned(self, "s_mod", {"result": "x", "steps": [
            {"step": 1, "action": "change", "card": "acid_spit", "text": "a"}, {"step": 2, "action": "change", "card": "spitter", "text": "b"}]})
        self.store.add_task("s_mod", "s_mod:GAME:9", "user", "Try it"); self.store.add_task("s_mod", "s_mod:BUILD:9", "controller", "Build")
        self.assertEqual(chat.adopt_follow_ups(self.store, "s_mod", first, ["s_mod:GAME:9", "s_mod:BUILD:9"]), [])
        self.assertEqual([t["id"] for t in steps(self, "s_mod")[1]["tasks"]], [first])


if __name__ == "__main__":
    unittest.main()
