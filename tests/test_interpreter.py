"""R3 interpreter (v1 criterion 1): proposal validation, questions, answers, approval flow."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.dispatch import dispatch, orchestrate
from mod_orchestra.interpreter import answer, spec_from_proposal, MAX_QUESTIONS
from mod_orchestra.provider import FakeProvider
from mod_orchestra.state import Store, StateError
from mod_orchestra.validation import InputError

PROPOSAL = {"features": [{"kind": "item", "identifier": "sky_crystal", "label": "Sky Crystal"},
                         {"kind": "block", "identifier": "crystal_ore", "label": "Crystal Ore"},
                         {"kind": "block", "identifier": "crystal_block", "label": "Crystal Block"}],
            "tab": "Crystals", "tab_icon": "sky_crystal",
            "recipes": [{"id": "crystal_block", "kind": "shaped", "result": "crystal_block", "pattern": ["CCC", "CCC", "CCC"], "key": {"C": "sky_crystal"}},
                        {"id": "crystal_smelt", "kind": "smelting", "result": "sky_crystal", "ingredients": ["crystal_ore"], "experience": 0.7}],
            "drops": [{"block": "crystal_ore", "item": "sky_crystal", "count_min": 1, "count_max": 2, "fortune": True, "silk_touch": True}],
            "assumptions": ["ore drops 1-2 crystals (vanilla-like)"]}


def handoff(status="WAITING_USER", spec=PROPOSAL, questions=None, task="i_mod:SPEC"):
    h = {"task": task, "status": status, "scope": "interpretation", "changed_files": [], "checks_run": [],
         "evidence": {"level": "NONE", "pointer": "no files"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "planner"}
    if spec is not None: h["spec"] = spec
    if questions is not None: h["questions"] = questions
    return "```handoff\n" + json.dumps(h) + "\n```"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        self.proj = workflow.new_project(self.store, name="Crystals", mod_id="i_mod", package="com.x.i",
                                         idea="quiero un mod de cristales del cielo: un ore que dropee cristales y un bloque hecho de 9 cristales, con su propia pestaña")

    def spec(self):
        return self.store.project("i_mod")["spec"]


class FreeText(Base):
    def test_free_text_idea_is_accepted_with_an_open_question(self):
        self.assertEqual(self.spec()["features"], [])
        self.assertTrue(any("interpreter" in q for q in self.spec()["questions"]))
        with self.assertRaisesRegex(StateError, "Open questions remain"):
            workflow.approve_spec(self.store, "i_mod")

    def test_grammar_ideas_still_work_without_an_agent(self):
        workflow.new_project(self.store, name="G", mod_id="g_mod", package="com.x.g", idea="items: gem; blocks: ore; tab: Gems")
        workflow.approve_spec(self.store, "g_mod")
        self.assertEqual(self.store.project("g_mod")["spec_state"], "APPROVED")


class Proposal(Base):
    def test_valid_proposal_becomes_the_draft_spec_and_waits_for_approval(self):
        fake = FakeProvider(handoff())
        out = dispatch(self.store, "i_mod", task_id="i_mod:SPEC", provider=fake)
        self.assertIn("interpreter", fake.envelopes[0].extra_instructions)
        self.assertEqual(out["task_state"], "WAITING_USER")
        self.assertEqual(out["handoff"]["needs_user"], ["craftctl approve-spec i_mod"])
        s = self.spec()
        self.assertEqual([f["identifier"] for f in s["features"]], ["sky_crystal", "crystal_ore", "crystal_block"])
        self.assertEqual(s["tab"], "Crystals"); self.assertEqual(len(s["recipes"]), 2); self.assertEqual(s["questions"], [])
        self.assertEqual(self.store.project("i_mod")["spec_state"], "DRAFT")
        # approval closes the parked SPEC task and unblocks the board
        workflow.approve_spec(self.store, "i_mod")
        self.assertEqual(next(t["state"] for t in self.store.tasks("i_mod") if t["id"] == "i_mod:SPEC"), "DONE")
        self.assertEqual(self.store.project("i_mod")["spec_state"], "APPROVED")
        self.assertTrue(any(t["id"] == "i_mod:SCAFFOLD" and t["state"] == "READY" for t in self.store.tasks("i_mod")))

    def test_questions_are_surfaced_and_answers_reopen_the_task(self):
        qs = ["Should the ore require an iron pickaxe?", "How many crystals per block: 4 or 9?"]
        out = dispatch(self.store, "i_mod", task_id="i_mod:SPEC", provider=FakeProvider(handoff(questions=qs)))
        self.assertEqual(out["task_state"], "WAITING_USER")
        self.assertTrue(out["handoff"]["needs_user"][0].startswith('craftctl answer i_mod "<your answer to: Should'))
        with self.assertRaisesRegex(StateError, "Open questions remain"):
            workflow.approve_spec(self.store, "i_mod")
        res = answer(self.store, "i_mod", "no pickaxe requirement; 9 per block")
        self.assertIn("[user answer] no pickaxe requirement", self.spec()["idea"]); self.assertEqual(self.spec()["questions"], [])
        self.assertEqual(next(t["state"] for t in self.store.tasks("i_mod") if t["id"] == "i_mod:SPEC"), "READY")
        self.assertIn("craftctl dispatch i_mod --task i_mod:SPEC", res["next"])

    def test_too_many_questions_or_bad_spec_fail_the_run(self):
        out = dispatch(self.store, "i_mod", task_id="i_mod:SPEC", provider=FakeProvider(handoff(questions=["a?", "b?", "c?", "d?"])))
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn(f"limit is {MAX_QUESTIONS}", out["error"])
        # first rejection: auto-retried with the reason in the packet (the task is READY again, no human needed)
        self.assertEqual(out["auto_retry"]["attempt"], 1)
        self.assertEqual(next(t["state"] for t in self.store.tasks("i_mod") if t["id"] == "i_mod:SPEC"), "READY")
        self.assertIn("PREVIOUS ATTEMPT REJECTED", self.store.task_instructions("i_mod:SPEC"))
        bad = dict(PROPOSAL, recipes=[{"id": "x1", "kind": "shaped", "result": "crystal_block", "pattern": ["CC", "CCC"], "key": {"C": "sky_crystal"}}])
        fake = FakeProvider(handoff(spec=bad))
        out = dispatch(self.store, "i_mod", task_id="i_mod:SPEC", provider=fake)
        self.assertIn("PREVIOUS ATTEMPT REJECTED", fake.envelopes[0].extra_instructions)
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("same width", out["error"])
        self.assertNotIn("auto_retry", out, "second rejection stops: a human looks")
        self.assertEqual(self.spec()["features"], [], "a rejected proposal must not touch the stored spec")

    def test_orchestrate_survives_one_format_failure(self):
        calls = {"n": 0}
        class Flaky(FakeProvider):
            def run(self, envelope, log_path):
                calls["n"] += 1
                self.reply = handoff(spec=None) if calls["n"] == 1 else handoff()
                return super().run(envelope, log_path)
        out = orchestrate(self.store, "i_mod", max_runs=4, provider=Flaky(""))
        self.assertEqual([r["task_state"] for r in out["runs"]], ["FAILED", "WAITING_USER"])
        self.assertIn("approve-spec", out["stopped_because"])

    def test_proposal_cannot_change_identity_fields(self):
        cur = self.spec()
        spec = spec_from_proposal(cur, dict(PROPOSAL, mod_id="evil", package="com.evil", name="Evil"))
        self.assertEqual((spec.mod_id, spec.package, spec.name), ("i_mod", "com.x.i", "Crystals"))

    def test_proposal_without_features_is_rejected(self):
        with self.assertRaisesRegex(InputError, "no items, blocks, mobs"):
            spec_from_proposal(self.spec(), {"features": []})

    def test_orchestrate_runs_spec_first_and_stops_for_the_user(self):
        out = orchestrate(self.store, "i_mod", max_runs=3, provider=FakeProvider(handoff()))
        self.assertEqual(len(out["runs"]), 1); self.assertEqual(out["runs"][0]["task"], "i_mod:SPEC")
        self.assertIn("craftctl approve-spec i_mod", out["stopped_because"])


if __name__ == "__main__":
    unittest.main()


class Suite(unittest.TestCase):
    def test_suite_scores_prompts_with_fake_provider(self):
        from mod_orchestra.suite import run_suite, score
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        prompts = base / "prompts"; prompts.mkdir()
        (prompts / "01.json").write_text(json.dumps({"name": "01_a_case", "idea": "crystals please", "expect": {"min_items": 1, "min_blocks": 2, "tab": True, "max_questions": 0}}))
        (prompts / "02.json").write_text(json.dumps({"name": "02_b_case", "idea": "dragon boss", "expect": {"min_items": 1, "unknown_mentions": "dragon", "max_questions": 3}}))
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            class Echo(FakeProvider):
                def run(self, envelope, log_path):
                    self.reply = handoff(task=envelope.task_id); return super().run(envelope, log_path)
            out = run_suite(store, provider=Echo(""), prompts_dir=prompts)
        self.assertEqual(out["total"], 2); self.assertTrue(out["results"][0]["pass"])
        self.assertFalse(out["results"][1]["pass"]); self.assertIn("'dragon' not surfaced", out["results"][1]["fails"][0])
        self.assertTrue(Path(out["written"]).is_file())
        self.assertEqual(score({"min_items": 5}, {"features": []}, {}, []), ["items 0 < 5"])
