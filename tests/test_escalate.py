"""A limitation becomes work: an animation at a moment the code lacks sends the coder first, the designer after."""
import json
import unittest

from mod_orchestra import animate, escalate
from mod_orchestra.cli import dispatch as cli_dispatch, parser
from mod_orchestra.dispatch import dispatch
from mod_orchestra.provider import FakeProvider
from mod_orchestra.validation import InputError

from test_animate import Item as ItemBase, Mob as MobBase, KEY
from test_art_requests import handoff as coder_handoff
from test_model_edit import MOB, TASK as MOB_TASK
from mod_orchestra.modeledit import _requeue_model


class Items(ItemBase):
    RELOAD = {"name": "reload", "what": "the guard drops and snaps back", "when": "the player reloads it with ammo from the inventory"}

    def test_a_moment_the_code_lacks_goes_to_the_coder_first_on_the_things_own_card(self):
        out = animate.request_animate(self.store, "m_mod", "item", "moon_sword", [self.RELOAD, {"name": "idle", "what": "sway"}])
        self.assertEqual([s["role"] for s in out["plan"]], ["coder", "designer"]); self.assertEqual(out["first"], out["plan"][0]["task"])
        self.assertTrue(out["first"].startswith("m_mod:CHANGE:moon:"), "the sword belongs to the moon material's card")
        states = {t["id"]: t["state"] for t in self.store.tasks("m_mod")}
        self.assertEqual((states[out["first"]], states[out["task"]]), ("READY", "BACKLOG"))
        brief = self.store.task_instructions(out["first"])
        self.assertIn("- `reload` (happens once): the player reloads it with ammo from the inventory", brief)
        self.assertNotIn("`idle`", brief, "idle is never a code moment")
        self.assertIn("MINIMUM behaviour", brief); self.assertIn("Item3DBase", brief); self.assertIn("animation_events", brief)
        self.assertIn("being added by a coder before you", self.store.task_instructions(out["task"]))
        # the coder makes it real and declares it: the designer is released, and a later install needs no wiring
        h = json.loads(coder_handoff(out["first"]).split("```handoff\n")[1].split("\n```")[0])
        h["animation_events"] = [{"item": "moon_sword", "name": "reload", "when": self.RELOAD["when"]}]; h["geo_items"] = ["moon_sword"]
        res = dispatch(self.store, "m_mod", task_id=out["first"], provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))
        self.assertEqual(res["task_state"], "DONE", res.get("error"))
        self.assertEqual({t["id"]: t["state"] for t in self.store.tasks("m_mod")}[out["task"]], "READY")
        self.assertEqual(escalate.code_moments(self.store, "m_mod", "item", "moon_sword"), {"reload"})

    def test_a_moment_the_code_has_needs_no_coder(self):
        from mod_orchestra.artreq import record_contract
        record_contract(self.store, "m_mod", "t", {"animation_events": [{"item": "moon_sword", "name": "reload", "when": "x"}], "geo_items": ["moon_sword"]})
        out = animate.request_animate(self.store, "m_mod", "item", "moon_sword", [self.RELOAD])
        self.assertEqual([s["role"] for s in out["plan"]], ["designer"]); self.assertEqual(out["first"], out["task"])

    def test_no_escalate_and_cli(self):
        out = animate.request_animate(self.store, "m_mod", "item", "moon_sword", [self.RELOAD], escalate=False)
        self.assertEqual([s["role"] for s in out["plan"]], ["designer"])
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "animate", "m_mod", "--item", "moon_sword", "--anim", "reload|x|when it reloads"]))
        self.assertEqual([s["role"] for s in out["plan"]], ["coder", "designer"])


class Mobs(MobBase):
    def test_built_ins_need_nothing_and_a_new_moment_goes_to_the_mobs_card(self):
        self.designed()
        out = animate.request_animate(self.store, "c_mod", "mob", MOB, [{"name": "walk", "what": "a limp"}])
        self.assertEqual([s["role"] for s in out["plan"]], ["designer"])
        out = animate.request_animate(self.store, "c_mod", "mob", MOB, [{"name": "roar", "what": "jaw open", "when": "it first sees a player"},
                                                                       {"name": "swim", "what": "paddles", "when": "it is in water", "loop": True}])
        self.assertEqual([s["role"] for s in out["plan"]], ["coder", "designer"])
        self.assertTrue(out["first"].startswith(f"c_mod:CHANGE:{MOB}:"))
        brief = self.store.task_instructions(out["first"])
        self.assertIn('triggerAnim("actions"', brief); self.assertIn("- `swim` (lasts while it holds): it is in water", brief)


if __name__ == "__main__":
    unittest.main()


class FromInsideARun(MobBase):
    """Piece 2: an agent hits the limitation while working and says what it needs; the controller makes it and brings the agent back."""

    def blocked(self, needs, task=None):
        tid = task or MOB_TASK
        h = {"task": tid, "status": "BLOCKED", "scope": "model", "changed_files": [], "checks_run": [], "evidence": {"level": "NONE", "pointer": "-"},
             "risks": [], "unknowns": ["the thing to animate does not exist"], "needs_user": [], "next_agent": "coder", "needs": needs}
        return dispatch(self.store, "c_mod", task_id=tid, provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))

    def test_the_designer_needs_code_the_coder_makes_it_and_the_designer_comes_back(self):
        self.designed()
        _requeue_model(self.store, "c_mod", MOB, "animate")
        out = self.blocked([{"role": "coder", "what": "an acid pool entity the spit leaves on the ground, with damage over time while a player stands in it",
                             "why": "the user asked for a pool animation and there is no pool", "target": MOB}])
        self.assertEqual(out["task_state"], "BACKLOG")
        esc = out["handoff"]["escalation"]; coder = esc["created"][0]["task"]
        self.assertTrue(coder.startswith(f"c_mod:CHANGE:{MOB}:"), "on the mob's own card")
        brief = self.store.task_instructions(coder)
        self.assertIn("an acid pool entity the spit leaves on the ground", brief); self.assertIn("MINIMUM behaviour", brief); self.assertIn("art_needed", brief)
        states = {t["id"]: t["state"] for t in self.store.tasks("c_mod")}
        self.assertEqual((states[coder], states[MOB_TASK]), ("READY", "BACKLOG"))
        self.assertIn("## Since your last run", self.store.task_instructions(MOB_TASK)); self.assertIn(coder, self.store.task_instructions(MOB_TASK))
        # the coder finishes: the designer is released on its own
        res = dispatch(self.store, "c_mod", task_id=coder, provider=FakeProvider(coder_handoff(coder)))
        self.assertEqual(res["task_state"], "DONE", res.get("error"))
        self.assertEqual({t["id"]: t["state"] for t in self.store.tasks("c_mod")}[MOB_TASK], "READY")
        self.assertIn("NEEDS_ESCALATED", [e["kind"] for e in self.store.events("c_mod")])

    def test_a_need_with_no_card_becomes_a_feature_and_other_roles_are_reported_not_automated(self):
        self.designed(); _requeue_model(self.store, "c_mod", MOB, "x")
        out = self.blocked([{"role": "coder", "what": "a weather system with acid rain", "why": "the mob should only spawn in it", "target": "nope"},
                            {"role": "designer", "what": "a second skin", "why": "variants"}])
        esc = out["handoff"]["escalation"]
        self.assertEqual(len(esc["created"]), 1); self.assertTrue(esc["created"][0]["card"] in (MOB, None))
        self.assertEqual(esc["unmet"][0]["role"], "designer")

    def test_blocked_without_needs_stays_blocked(self):
        self.designed(); _requeue_model(self.store, "c_mod", MOB, "x")
        out = self.blocked([])
        self.assertEqual(out["task_state"], "BLOCKED"); self.assertNotIn("escalation", out["handoff"])


class Ask(ItemBase):
    """Piece 3: a free-text request becomes a plan the controller applies with the requests that already exist."""

    def test_the_planner_gets_the_project_and_its_plan_becomes_chained_tasks(self):
        from mod_orchestra import ask
        out = ask.request_ask(self.store, "m_mod", "I want the sword to be able to reload and show the animation")
        brief = self.store.task_instructions(out["task"])
        self.assertIn("## The user's request", brief); self.assertIn("I want the sword to be able to reload", brief)
        self.assertIn("- moon · material", brief); self.assertIn("3D already: items moon_sword", brief); self.assertIn("Actions and their fields", brief)
        self.assertEqual(next(t for t in self.store.tasks("m_mod") if t["id"] == out["task"])["role"], "planner")
        plan = [{"step": 1, "action": "change", "card": "moon", "text": "the sword reloads with ammo from the inventory"},
                {"step": 2, "action": "animate", "kind": "item", "target": "moon_sword", "after": [1],
                 "anims": [{"name": "reload", "what": "the guard snaps", "when": "the player reloads it"}]},
                {"step": 3, "action": "fly", "target": "x"}]
        h = json.loads(coder_handoff(out["task"]).split("```handoff\n")[1].split("\n```")[0]); h["plan"] = plan
        res = dispatch(self.store, "m_mod", task_id=out["task"], provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))
        self.assertEqual(res["task_state"], "DONE", res.get("error"))
        applied = res["handoff"]["plan_applied"]
        self.assertEqual([a["action"] for a in applied["applied"]], ["change", "animate"]); self.assertEqual(applied["skipped"][0]["why"], "unknown action 'fly'")
        change = applied["applied"][0]["tasks"][0]; first_anim = applied["applied"][1]["tasks"][0]
        states = {t["id"]: t["state"] for t in self.store.tasks("m_mod")}
        self.assertEqual(states[change], "READY"); self.assertEqual(states[first_anim], "BACKLOG", "step 2 waits for step 1")
        self.assertEqual(applied["first"], change)
        with self.assertRaisesRegex(InputError, "Say what you want"):
            ask.request_ask(self.store, "m_mod", "  ")

    def test_no_plan_fails_the_ask(self):
        from mod_orchestra import ask
        out = ask.request_ask(self.store, "m_mod", "make it shiny")
        res = dispatch(self.store, "m_mod", task_id=out["task"], provider=FakeProvider(coder_handoff(out["task"])))
        self.assertEqual(res["task_state"], "FAILED"); self.assertIn("no plan", res["error"])
