import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import rigs, skin, workflow
from mod_orchestra.interpreter import spec_from_proposal, SPEC_INSTRUCTIONS
from mod_orchestra.spec import Behavior, behavior_id, coerce_behavior, read_spec
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError

FIX = Path(__file__).parent / "fixtures"
IDEA = (FIX / "infectious_zombies.idea.txt").read_text(encoding="utf8").strip()
PROPOSAL = json.loads((FIX / "infectious_zombies.proposal.json").read_text(encoding="utf8"))
CURRENT = {"name": "Infectious Zombies", "mod_id": "infect", "package": "com.example.infect", "idea": IDEA, "profile": "fabric-1.21.1-candidate"}


def proposal(**over):
    p = json.loads(json.dumps(PROPOSAL)); p.update(over); return p


class TestBehaviorSpec(unittest.TestCase):
    def test_the_ideal_interpretation_is_a_valid_spec(self):
        spec = spec_from_proposal(CURRENT, PROPOSAL)
        self.assertEqual([(m.identifier, m.body_plan, m.health) for m in spec.mobs], [("runner", "biped", 30), ("spitter", "biped", 24), ("brute", "primate", 80)])
        self.assertEqual([behavior_id(b.title) for b in spec.behaviors], ["infectious_poison_and_conversion", "infection", "spitter_acid_spit", "brute_breaks_blocks_and_leaps", "brute_thrown_blocks_and_shield_breaker"])
        again = read_spec(json.loads(json.dumps(spec.to_dict())))
        self.assertEqual(again.behaviors, spec.behaviors)

    def test_coercion(self):
        b = coerce_behavior({"title": " Acid ", "description": "d" * 30, "acceptance": "one criterion here", "affects": ["spitter"]})
        self.assertEqual((b.title, b.acceptance, b.after), ("Acid", ("one criterion here",), ()))
        with self.assertRaises(InputError):
            coerce_behavior(["not", "a", "dict"])

    def test_every_rule(self):
        def with_behavior(**kw):
            b = {"title": "Extra mechanic", "description": "x" * 40, "acceptance": ["something observable happens"], "affects": ["brute"], "after": []}; b.update(kw)
            return spec_from_proposal(CURRENT, proposal(behaviors=PROPOSAL["behaviors"] + [b]))
        with_behavior()
        for bad, why in ((dict(title="ab"), "title"), (dict(description="short"), "description"), (dict(acceptance=[]), "acceptance"), (dict(acceptance=["x"]), "acceptance"),
                         (dict(affects=["ghost"]), "unknown identifiers"), (dict(after=["No such behavior"]), "not other behaviors"), (dict(after=["Extra mechanic"]), "not other behaviors"),
                         (dict(title="Brute"), "identifier of a mob"), (dict(title="Spitter acid spit"), "same card id"),
                         (dict(kind="trait"), "kind is capability or mechanic"), (dict(kind="capability", affects=[]), "lists the mobs that carry it"),
                         (dict(kind="capability", affects=["brute", "ghost"]), "lists the mobs that carry it")):
            with self.assertRaisesRegex(InputError, why, msg=str(bad)):
                with_behavior(**bad)
        with self.assertRaisesRegex(InputError, "At most 12"):
            spec_from_proposal(CURRENT, proposal(behaviors=[{"title": f"Mechanic number {i}", "description": "d" * 30, "acceptance": ["observable thing happens"], "affects": ["brute"]} for i in range(13)]))

    def test_loops_are_rejected(self):
        a = {"title": "Alpha mechanic", "description": "d" * 30, "acceptance": ["observable thing happens"], "affects": ["brute"], "after": ["Beta mechanic"]}
        b = {"title": "Beta mechanic", "description": "d" * 30, "acceptance": ["observable thing happens"], "affects": ["brute"], "after": ["Alpha mechanic"]}
        with self.assertRaisesRegex(InputError, "loop"):
            spec_from_proposal(CURRENT, proposal(behaviors=[a, b]))

    def test_a_spec_without_behaviors_still_reads(self):
        raw = spec_from_proposal(CURRENT, proposal(behaviors=[])).to_dict(); raw.pop("behaviors")
        self.assertEqual(read_spec(raw).behaviors, [])

    def test_the_interpreter_is_told_about_behaviors_and_primates(self):
        for needle in ('"behaviors"', "3-6 coherent behaviors", "EVERY number the user gave", "never one per sentence", "primate", "knuckle-walking primates", "write each as a `behavior`"):
            self.assertIn(needle, SPEC_INSTRUCTIONS.replace("{{", "{").replace("}}", "}"))
        self.assertNotIn("keep the user's wish in `unknowns`", SPEC_INSTRUCTIONS)                    # the old instruction that dropped custom AI

    def test_the_rules_learned_from_a_real_interpretation(self):
        text = SPEC_INSTRUCTIONS.replace("{{", "{").replace("}}", "}")
        for needle in ("A behavior is a `capability` when it is something mobs CARRY", "built once as a\nreusable component wired to each carrier", "Use `after` ONLY when a behavior needs code or an effect that another one creates", "must not wait for each other", "Say WHEN every mechanic triggers",
                       "what every new effect, projectile or state DOES in numbers", "state the reading you chose as the FIRST assumption", "over many trials every outcome appears",
                       "What the user says explicitly always wins", "only the Spitter spits", "belongs to every member of that group", "that effect IS how the group does the thing", "never let a member bypass the effect with a shortcut of your own", "so the user can see how far you went"):
            self.assertIn(needle, text)
        from mod_orchestra.guidance import guidance
        self.assertNotIn("a tab and mobs", open(Path(__file__).resolve().parents[1] / "src/mod_orchestra/guidance.py", encoding="utf8").read())


class TestGenerationPlansBehaviors(unittest.TestCase):
    def setUp(self):
        from mod_orchestra.interpreter import apply_interpretation
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "s.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop); (base / "projects").mkdir()
        # these tests are about behaviors: the icons task is covered in test_art.py
        no_icons = patch("mod_orchestra.models.ensure_initial_sprites", lambda *a, **k: None); no_icons.start(); self.addCleanup(no_icons.stop)
        workflow.new_project(self.store, name="Infectious Zombies", mod_id="infect", package="com.example.infect", idea=IDEA)
        apply_interpretation(self.store, "infect", {"status": "WAITING_USER", "spec": PROPOSAL, "questions": []}, "run-1")
        workflow.plan_project(self.store, "infect"); workflow.approve_spec(self.store, "infect")
        self.out = workflow.generate_project(self.store, "infect")
        self.tasks = {t["id"]: t for t in self.store.tasks("infect")}

    def test_each_behavior_becomes_a_card_and_a_coder_task(self):
        self.assertEqual(sorted(self.out["behavior_tasks"]), sorted(f"infect:FEATURE:{i}" for i in
                         ("infectious_poison_and_conversion", "infection", "spitter_acid_spit", "brute_breaks_blocks_and_leaps", "brute_thrown_blocks_and_shield_breaker")))
        for tid in self.out["behavior_tasks"]:
            self.assertEqual(self.tasks[tid]["role"], "coder")
        from mod_orchestra.modmap import custom_cards
        cards = custom_cards(self.store, "infect")
        self.assertEqual(cards["infectious_poison_and_conversion"]["derived_from"], ["runner", "spitter", "brute"])
        self.assertEqual(len(cards["infectious_poison_and_conversion"]["acceptance"]), 5); self.assertEqual(cards["infection"]["derived_from"], ["runner", "spitter", "brute"])

    def test_dependencies_order_the_tasks(self):
        self.assertEqual(self.tasks["infect:FEATURE:infectious_poison_and_conversion"]["state"], "READY")        # the foundation: the effect and what it does when a mob dies under it
        for waits in ("infection", "spitter_acid_spit"):
            self.assertEqual(self.tasks[f"infect:FEATURE:{waits}"]["state"], "BACKLOG")                          # each way of applying it waits for the effect
        for free in ("brute_breaks_blocks_and_leaps", "brute_thrown_blocks_and_shield_breaker"):
            self.assertEqual(self.tasks[f"infect:FEATURE:{free}"]["state"], "READY")                             # independent: they do not wait for the infection
        with self.store.tx() as con:
            edges = [tuple(r) for r in con.execute("SELECT predecessor, successor FROM task_edges WHERE successor LIKE 'infect:FEATURE:%'")]
        self.assertEqual(sorted(edges), [("infect:FEATURE:infectious_poison_and_conversion", "infect:FEATURE:infection"),
                                         ("infect:FEATURE:infectious_poison_and_conversion", "infect:FEATURE:spitter_acid_spit")])

    def test_the_coder_brief_has_the_description_the_criteria_and_the_gametests(self):
        text = self.store.task_instructions("infect:FEATURE:brute_breaks_blocks_and_leaps")
        for needle in ("Title: Brute breaks blocks and leaps", "obsidian and bedrock never", "up to 4 blocks high", "- A Brute does not break obsidian or bedrock",
                       "Builds on: brute", "@GameTest per acceptance criterion"):
            self.assertIn(needle, text)

    def test_the_mobs_are_generated_with_their_rigs(self):
        import json as _json
        root = Path(self.store.project("infect")["root"]) / "src/main/resources/assets/infect"
        brute = _json.loads((root / "geo/entity/brute.geo.json").read_text())["minecraft:geometry"][0]["bones"]
        self.assertIn("left_arm_lower", [b["name"] for b in brute]); self.assertNotIn("held_item", [b["name"] for b in brute])
        runner = _json.loads((root / "geo/entity/runner.geo.json").read_text())["minecraft:geometry"][0]["bones"]
        self.assertIn("held_item", [b["name"] for b in runner])                                        # bipeds keep the weapon bone (nothing to hold here: no tool drops)

    def test_planning_is_idempotent_and_the_map_shows_the_cards(self):
        from mod_orchestra.modmap import plan_behaviors, mod_map
        self.assertEqual(plan_behaviors(self.store, "infect"), [])
        ids = {c["id"] for c in mod_map(self.store, "infect")["cards"]}
        self.assertTrue({"infectious_poison_and_conversion", "brute", "runner"} <= ids)


class TestCapabilities(TestGenerationPlansBehaviors):
    """INFECTION is a capability: the coder builds it once and wires every carrier; the user checks and edits who carries it."""

    def test_the_coder_is_told_to_build_it_once_and_wire_the_carriers(self):
        text = self.store.task_instructions("infect:FEATURE:infection")
        for needle in ("This is a CAPABILITY carried by: runner, spitter, brute", "Implement it ONCE as a reusable component", "never a copy of the logic", "one @GameTest per carrier"):
            self.assertIn(needle, text)
        self.assertNotIn("CAPABILITY", self.store.task_instructions("infect:FEATURE:spitter_acid_spit"))             # a mechanic gets the plain brief

    def test_a_carrier_change_before_the_coder_starts_rewrites_the_brief(self):
        from mod_orchestra.content import set_behavior_carriers
        from mod_orchestra.modmap import custom_cards
        out = set_behavior_carriers(self.store, "infect", "infection", ["runner", "brute"])
        self.assertEqual((out["changed"], out["task"], out["how"]), (True, "infect:FEATURE:infection", "brief rewritten: the coder has not started it"))
        self.assertIn("carried by: runner, brute", self.store.task_instructions("infect:FEATURE:infection"))
        self.assertEqual(custom_cards(self.store, "infect")["infection"]["derived_from"], ["runner", "brute"])
        self.assertEqual(read_spec(self.store.project("infect")["spec"]).behaviors[1].affects, ("runner", "brute"))
        self.assertEqual(self.store.project("infect")["spec_state"], "APPROVED")                                  # after generation the edit is cosmetic for the spec
        self.assertFalse([t for t in self.store.tasks("infect") if ":CHANGE:" in t["id"]])

    def test_after_the_coder_built_it_the_change_is_a_task_that_wires_only_the_carriers(self):
        from mod_orchestra.content import set_behavior_carriers
        with self.store.tx() as con:
            con.execute("UPDATE tasks SET state='DONE' WHERE id='infect:FEATURE:infection'")
        out = set_behavior_carriers(self.store, "infect", "infection", ["runner", "spitter", "brute"][:1] + ["spitter"])
        self.assertEqual(out["how"], "change request for the coder")
        text = self.store.task_instructions(out["task"])
        for needle in ("Take it away from: brute", "remove only their wiring and their GameTests", "Do not duplicate the component", "REQUESTED CHANGE"):
            self.assertIn(needle, text)
        out2 = set_behavior_carriers(self.store, "infect", "infection", ["runner", "spitter", "brute"])
        self.assertIn("Give it to: brute", self.store.task_instructions(out2["task"])); self.assertIn("a GameTest per new carrier", self.store.task_instructions(out2["task"]))

    def test_nothing_changes_when_the_carriers_are_the_same_and_bad_input_is_refused(self):
        from mod_orchestra.content import set_behavior_carriers
        self.assertEqual(set_behavior_carriers(self.store, "infect", "infection", ["brute", "runner", "spitter"])["changed"], True)   # a new order counts
        self.assertFalse(set_behavior_carriers(self.store, "infect", "infection", ["brute", "runner", "spitter"])["changed"])
        for args, why in ((("ghost", ["runner"]), "Unknown behavior"), (("spitter_acid_spit", ["runner"]), "mechanic"), (("infection", []), "one or more mobs"), (("infection", ["villager"]), "one or more mobs")):
            with self.assertRaisesRegex(InputError, why):
                set_behavior_carriers(self.store, "infect", *args)


class TestCarriersBeforeGeneration(unittest.TestCase):
    def test_it_edits_the_spec_and_resets_the_approval(self):
        from mod_orchestra.content import set_behavior_carriers
        from mod_orchestra.interpreter import apply_interpretation
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite")
            with patch.object(workflow, "PROJECTS", Path(tmp) / "p"):
                (Path(tmp) / "p").mkdir()
                workflow.new_project(store, name="Infectious Zombies", mod_id="infect", package="com.example.infect", idea=IDEA)
                apply_interpretation(store, "infect", {"status": "WAITING_USER", "spec": PROPOSAL, "questions": []}, "run-1")
                workflow.plan_project(store, "infect"); workflow.approve_spec(store, "infect")
                out = set_behavior_carriers(store, "infect", "infection", ["runner"])
                self.assertEqual((out["task"], out["spec_state"]), (None, "DRAFT")); self.assertEqual(store.project("infect")["spec_state"], "DRAFT")
                self.assertEqual(read_spec(store.project("infect")["spec"]).behaviors[1].affects, ("runner",))


class TestFittingTheProposal(unittest.TestCase):
    """Regression: the interpreter's whole proposal was rejected over a 61+ character art.silhouette of the Runner and the run was lost."""
    LONG = "a lean sprinter hunched forward with long clawed hands dragging low and a ragged coat flapping behind it"

    def long_silhouette(self):
        p = proposal(); p["mobs"][0]["art"]["silhouette"] = self.LONG; return p

    def test_a_long_silhouette_is_trimmed_not_rejected_and_the_user_is_told(self):
        spec = spec_from_proposal(CURRENT, self.long_silhouette())
        runner = next(m for m in spec.mobs if m.identifier == "runner")
        self.assertLessEqual(len(runner.art.silhouette), 60); self.assertTrue(self.LONG.startswith(runner.art.silhouette))   # cut at a word, nothing rewritten
        note = spec.assumptions[-1]
        self.assertTrue(note.startswith("Trimmed to fit the spec's limits")); self.assertIn("mob runner art.silhouette to 60 characters", note)

    def test_every_cosmetic_field_is_fitted(self):
        from mod_orchestra.interpreter import fit_proposal
        p = proposal()
        p["mobs"][0]["art"] = {"concept": "word " * 100, "tags": ["ok tag", "x", "a" * 80, "ok tag"] + [f"cue number {i}" for i in range(30)], "silhouette": "s " * 40, "pieces": {"sword": "no"}}
        p["materials"] = [{"identifier": "g", "label": "G", "ingredient": "minecraft:iron_ingot", "tools": ["sword"], "armor": [], "art": {"pieces": {"sword": "fine", "wand": "drop me"}}}]
        p["behaviors"][0]["description"] = "d" * 2000
        p["behaviors"][0]["acceptance"] = ["a criterion that is far too long " * 20, "no"] + ["an observable criterion %d" % i for i in range(20)]
        fitted, notes = fit_proposal(p)
        art = fitted["mobs"][0]["art"]
        self.assertLessEqual(len(art["concept"]), 320); self.assertLessEqual(len(art["silhouette"]), 60)
        self.assertEqual(len(art["tags"]), 16); self.assertNotIn("x", art["tags"]); self.assertEqual(art["tags"].count("ok tag"), 1); self.assertTrue(all(2 <= len(t) <= 48 for t in art["tags"]))
        self.assertEqual(fitted["materials"][0]["art"]["pieces"], {"sword": "fine"})
        b = fitted["behaviors"][0]
        self.assertLessEqual(len(b["description"]), 1500); self.assertEqual(len(b["acceptance"]), 12); self.assertTrue(all(5 <= len(a) <= 300 for a in b["acceptance"]))
        self.assertEqual(p["mobs"][0]["art"]["silhouette"], "s " * 40)                                      # the original is not touched
        self.assertTrue(any("art.pieces.wand dropped" in n for n in notes))

    def test_dangerous_characters_become_spaces(self):
        from mod_orchestra.interpreter import fit_proposal
        p = proposal(); p["mobs"][0]["art"]["concept"] = "a <b>zombie</b> with {braces}, [brackets] and a back\\slash\x07"
        self.assertEqual(fit_proposal(p)[0]["mobs"][0]["art"]["concept"], "a b zombie /b with braces , brackets and a back slash")

    def test_structure_is_still_rejected_and_so_are_the_users_own_edits(self):
        p = proposal(); p["behaviors"][0]["affects"] = ["ghost"]
        with self.assertRaisesRegex(InputError, "unknown identifiers"):
            spec_from_proposal(CURRENT, p)
        p = proposal(); p["behaviors"][0]["title"] = "T" * 80
        with self.assertRaisesRegex(InputError, "title"):
            spec_from_proposal(CURRENT, p)                                                                   # titles feed ids and `after`: never trimmed silently
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite")
            with patch.object(workflow, "PROJECTS", Path(tmp) / "p"):
                (Path(tmp) / "p").mkdir()
                workflow.new_project(store, name="G", mod_id="g_mod", package="com.x.g", idea="hostile mobs: brute")
                from mod_orchestra.content import set_art
                with self.assertRaisesRegex(InputError, "silhouette"):
                    set_art(store, "g_mod", "mob", "brute", concept="a hulking ork", silhouette=self.LONG)      # what the user types is not trimmed behind their back

    def test_the_prompt_states_the_limits(self):
        text = SPEC_INSTRUCTIONS.replace("{{", "{").replace("}}", "}")
        for needle in ("Field limits", "art.silhouette 60 (a short phrase, not a sentence)", "each tag 2-48 characters and at most 16 tags", "behavior title 3-60 characters, description 20-1500, 1-12 criteria of 5-300"):
            self.assertIn(needle, text)


class TestTheButtonRetries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "s.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop); (base / "projects").mkdir()
        workflow.new_project(self.store, name="Infectious Zombies", mod_id="infect", package="com.example.infect", idea=IDEA)
        workflow.plan_project(self.store, "infect")

    def reply(self, spec):
        handoff = {"task": "infect:SPEC", "status": "WAITING_USER", "scope": "propose the spec", "changed_files": [], "checks_run": [], "evidence": {"level": "NONE", "pointer": "proposal"},
                   "risks": [], "unknowns": [], "questions": [], "spec": spec, "needs_user": ["craftctl approve-spec"], "next_agent": "none"}
        return "Here is the proposal.\n```handoff\n" + json.dumps(handoff) + "\n```\n"

    def test_a_trimmable_proposal_needs_one_run_and_no_retry(self):
        from mod_orchestra.dispatch import dispatch_with_retry
        from mod_orchestra.provider import FakeProvider
        p = proposal(); p["mobs"][0]["art"]["silhouette"] = TestFittingTheProposal.LONG
        out = dispatch_with_retry(self.store, "infect", task_id="infect:SPEC", provider=FakeProvider(self.reply(p)))
        self.assertEqual(out["task_state"], "WAITING_USER"); self.assertEqual(sum(1 for r in self.store.runs("infect")), 1)
        self.assertTrue(read_spec(self.store.project("infect")["spec"]).assumptions[-1].startswith("Trimmed to fit"))

    def test_a_structural_error_is_retried_once_with_its_reason_and_then_reported(self):
        from mod_orchestra.dispatch import dispatch_with_retry
        from mod_orchestra.provider import FakeProvider
        p = proposal(); p["behaviors"][0]["affects"] = ["ghost"]
        out = dispatch_with_retry(self.store, "infect", task_id="infect:SPEC", provider=FakeProvider(self.reply(p)))
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("proposal rejected", out["error"])
        self.assertEqual(len(self.store.runs("infect")), 2)                                                  # the first run plus exactly one retry
        retries = [e for e in self.store.events("infect", 200) if e["kind"] == "AUTO_RETRY"]
        self.assertEqual(len(retries), 1); self.assertIn("unknown identifiers", retries[0]["payload"]["reason"])
        self.assertIn("PREVIOUS ATTEMPT REJECTED BY THE CONTROLLER", self.store.task_instructions("infect:SPEC"))

    def test_the_retry_gets_the_reason_and_can_succeed(self):
        from mod_orchestra.dispatch import dispatch_with_retry
        from mod_orchestra.provider import FakeProvider
        bad = proposal(); bad["behaviors"][0]["affects"] = ["ghost"]
        replies = iter([self.reply(bad), self.reply(proposal())])
        class Sequence(FakeProvider):
            def run(self, envelope, log_path):
                self.reply = next(replies); return super().run(envelope, log_path)
        out = dispatch_with_retry(self.store, "infect", task_id="infect:SPEC", provider=Sequence(""))
        self.assertEqual(out["task_state"], "WAITING_USER"); self.assertEqual(len(self.store.runs("infect")), 2)
        self.assertEqual(len(read_spec(self.store.project("infect")["spec"]).behaviors), 5)


class TestPrimateRig(unittest.TestCase):
    def test_it_is_a_registered_plan_with_the_usual_clips(self):
        self.assertIn("primate", rigs.BODY_PLANS)
        rec = rigs.recipe("primate")
        self.assertEqual([a["name"] for a in rec["animations"]], ["animation.primate.idle", "animation.primate.walk", "animation.primate.attack"])
        self.assertEqual(rec["bones"][0], {"name": "root", "origin": [0, 0, 0]})

    def test_the_torso_is_hunched_and_the_arms_are_long_front_legs(self):
        bones = {b["name"]: b for b in rigs.recipe("primate")["bones"]}
        self.assertLess(bones["body"]["rotation"][0], -20)                                               # pitched forward (negative X leans the top toward the front)
        self.assertEqual((bones["left_arm_lower"]["parent"], bones["left_arm"]["parent"], bones["left_leg"]["parent"]), ("left_arm", "body", "root"))
        reach = max(c["to"][1] for c in rigs.recipe("primate")["cubes"] if c["bone"] == "left_arm") - min(c["from"][1] for c in rigs.recipe("primate")["cubes"] if c["bone"] == "left_arm_lower")
        leg = max(c["to"][1] for c in rigs.recipe("primate")["cubes"] if c["bone"] == "left_leg") - min(c["from"][1] for c in rigs.recipe("primate")["cubes"] if c["bone"] == "left_leg_shin")
        self.assertGreater(reach, leg * 1.5)                                                             # the arms reach further than the legs: knuckle-walker
        self.assertNotIn("held_item", bones)

    def test_a_skin_with_a_readable_face_can_be_painted_on_it(self):
        model = rigs.load_rig("primate", "bbmodel")
        png, report = skin.paint_skin(model, palette={"base": "#5f7a3a", "metal": "#3d1f47"}, face={"tusks": True})
        self.assertTrue(report["face_check"]["ok"], report["face_check"])
        self.assertEqual(skin.decode_png(png)[:2], (128, 128))

    def test_the_art_cues_know_the_plan(self):
        from mod_orchestra.art import KIND_CUES
        self.assertIn("knuckle-walking", KIND_CUES["primate"])

    def test_the_plan_is_choosable_everywhere(self):
        from mod_orchestra.specedit import set_body_plan
        index = (Path(__file__).resolve().parents[1] / "src/mod_orchestra/static/index.html").read_text(encoding="utf8")
        self.assertIn('<option value="primate">', index)
        cli = (Path(__file__).resolve().parents[1] / "src/mod_orchestra/cli.py").read_text(encoding="utf8")
        self.assertEqual(cli.count('"insect", "primate"'), 2)                                            # add-mob and set-body-plan


if __name__ == "__main__":
    unittest.main()
