"""Edit an existing mob's model without redesigning it: --scale sizes the model and its hitbox through vanilla's scale attribute."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.cli import dispatch, parser
from mod_orchestra.config import SUPPORTED_PROFILE
from mod_orchestra.fabric import accept_changes, validate_generated
from mod_orchestra.geckolib import entity_java
from mod_orchestra.models import patch_scale, set_mob_scale
from mod_orchestra.spec import interpret, read_spec
from mod_orchestra.specedit import add_mob
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError

IDEA = "items: fang; hostile mobs: runner; tab: Runners"
ENTITY = "src/main/java/com/x/r/entity/RunnerEntity.java"


class Generator(unittest.TestCase):
    def setUp(self):
        self.spec = interpret(name="R", mod_id="r_mod", package="com.x.r", idea=IDEA + "; mobs: critter", profile=SUPPORTED_PROFILE)

    def mob(self, ident, **kw):
        return replace(next(m for m in self.spec.mobs if m.identifier == ident), **kw)

    def test_default_is_as_modeled_and_writes_nothing(self):
        for ident in ("runner", "critter"):
            self.assertEqual(self.mob(ident).scale, 1.0)
            self.assertNotIn("Attributes.SCALE", entity_java(self.spec, self.mob(ident)))

    def test_a_scale_is_one_attribute_in_the_chain(self):
        java = entity_java(self.spec, self.mob("runner", scale=1.5))
        self.assertIn(".add(Attributes.SCALE, 1.5)\n", java)
        chain = java[java.index("createMonsterAttributes()"):]
        self.assertEqual(chain[:chain.index(";")].count(".add("), 4)   # health, speed, damage, scale: one statement

    def test_range_is_the_attribute_range(self):
        raw = self.spec.to_dict()
        for bad in (0.05, 17, -1):
            raw["mobs"][0]["scale"] = bad
            with self.assertRaisesRegex(InputError, "scale"):
                read_spec(raw)
        raw["mobs"][0]["scale"] = 16
        read_spec(raw)
        del raw["mobs"][0]["scale"]   # a spec written before the field existed
        self.assertEqual(read_spec(raw).mobs[0].scale, 1.0)

    def test_patch_equals_generating_with_the_scale(self):
        for ident in ("runner", "critter"):   # hostile chain ends on ATTACK_DAMAGE, passive on MOVEMENT_SPEED
            plain, big, small = (entity_java(self.spec, self.mob(ident, scale=s)) for s in (1.0, 1.5, 0.5))
            self.assertEqual(patch_scale(plain, 1.5), big)
            self.assertEqual(patch_scale(big, 0.5), small)
            self.assertEqual(patch_scale(big, 1.0), plain)
            self.assertEqual(patch_scale(plain, 1.0), plain)

    def test_patch_keeps_windows_line_endings(self):
        crlf = entity_java(self.spec, self.mob("critter")).replace("\n", "\r\n")
        out = patch_scale(crlf, 2.0)
        self.assertIn(".add(Attributes.SCALE, 2.0);", out); self.assertNotIn("\n", out.replace("\r\n", ""))
        self.assertEqual(patch_scale(out, 1.0), crlf)

    def test_patch_refuses_shapes_it_did_not_write(self):
        plain = entity_java(self.spec, self.mob("critter"))
        self.assertIsNone(patch_scale(plain.replace("MOVEMENT_SPEED", "FLYING_SPEED"), 1.5))
        speed = plain[plain.index(".add(Attributes.MOVEMENT_SPEED"):].split("\n")[0]
        self.assertIsNone(patch_scale(plain + "\n// " + speed, 1.5))
        twice = entity_java(self.spec, self.mob("critter", scale=2.0)) + "\n// .add(Attributes.SCALE, 3.0)"
        self.assertIsNone(patch_scale(twice, 1.5))


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.db = base / "state.sqlite"; self.store = Store(self.db)
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        self.root = Path(workflow.new_project(self.store, name="R", mod_id="r_mod", package="com.x.r", idea=IDEA)["root"])

    def generate(self):
        workflow.plan_project(self.store, "r_mod"); workflow.approve_spec(self.store, "r_mod"); workflow.generate_project(self.store, "r_mod")

    def scale(self):
        return next(m for m in read_spec(self.store.project("r_mod")["spec"]).mobs if m.identifier == "runner").scale

    def scale_tasks(self):
        return [t for t in self.store.tasks("r_mod") if ":SCALE:" in t["id"]]

    def test_before_generation_it_is_a_spec_edit(self):
        out = set_mob_scale(self.store, "r_mod", "runner", 1.5)
        self.assertEqual((out["how"], out["spec_state"], self.scale()), ("spec edit", "DRAFT", 1.5))
        self.generate()
        self.assertIn(".add(Attributes.SCALE, 1.5)", (self.root / ENTITY).read_text())

    def test_after_generation_the_untouched_entity_is_patched(self):
        self.generate()
        before = self.store.project("r_mod")["status"]
        out = set_mob_scale(self.store, "r_mod", "runner", 2)
        self.assertEqual((out["how"], out["accepted"], self.scale()), ("patched", [ENTITY], 2.0))
        self.assertIn(".add(Attributes.SCALE, 2.0)", (self.root / ENTITY).read_text())
        self.assertEqual(validate_generated(self.root)["status"], "PASS")
        manifest = json.loads((self.root / ".mod-orchestra/generation-manifest.json").read_text())
        self.assertEqual((manifest["revisions"][-1]["actor"], list(manifest["revisions"][-1]["files"])), ("user", [ENTITY]))
        self.assertEqual(self.scale_tasks(), [])
        self.assertEqual(before, "SOURCE_GENERATED_UNVERIFIED")
        self.assertIn("MOB_SCALED", [e["kind"] for e in self.store.events("r_mod")])
        again = set_mob_scale(self.store, "r_mod", "runner", 2.0)
        self.assertFalse(again["changed"])

    def test_a_verified_project_must_be_built_again(self):
        self.generate()
        self.store.update_project("r_mod", status="GAME_VERIFIED")
        with self.store.tx() as con:
            con.execute("UPDATE tasks SET state='DONE' WHERE id=?", ("r_mod:BUILD",))
        set_mob_scale(self.store, "r_mod", "runner", 1.5)
        self.assertEqual(self.store.project("r_mod")["status"], "SOURCE_GENERATED_UNVERIFIED")
        self.assertNotEqual(next(t for t in self.store.tasks("r_mod") if t["id"] == "r_mod:BUILD")["state"], "DONE")

    def test_an_accepted_coder_edit_survives_the_patch(self):
        self.generate()
        f = self.root / ENTITY
        f.write_text(f.read_text().replace("public class RunnerEntity", "// infection wired by the coder\npublic class RunnerEntity"))
        accept_changes(self.root, run_id="coder-run", actor="coder", changed=[ENTITY])
        self.assertEqual(set_mob_scale(self.store, "r_mod", "runner", 1.25)["how"], "patched")
        text = f.read_text()
        self.assertIn("// infection wired by the coder", text); self.assertIn(".add(Attributes.SCALE, 1.25)", text)
        self.assertEqual(validate_generated(self.root)["status"], "PASS")

    def test_an_unreported_edit_is_never_overwritten_or_laundered(self):
        self.generate()
        f = self.root / ENTITY
        tampered = f.read_text() + "\n// edited outside the orchestra\n"
        f.write_text(tampered)
        out = set_mob_scale(self.store, "r_mod", "runner", 1.5)
        self.assertEqual(out["how"], "coder task"); self.assertIn("edits the manifest does not record", out["why"])
        self.assertEqual(f.read_text(), tampered)
        self.assertIn("CHANGED: " + ENTITY, validate_generated(self.root)["problems"])
        self.assertEqual(self.scale(), 1.5)   # the spec follows the user; the code follows through the coder
        task = self.scale_tasks()
        self.assertEqual([t["role"] for t in task], ["coder"])
        brief = self.store.task_instructions(task[0]["id"])
        self.assertIn(".add(Attributes.SCALE, 1.5)", brief); self.assertIn(ENTITY, brief); self.assertIn("do not touch the renderer", brief)
        # a second change before the coder starts rewrites the same brief instead of stacking tasks
        set_mob_scale(self.store, "r_mod", "runner", 3)
        self.assertEqual(len(self.scale_tasks()), 1)
        self.assertIn(".add(Attributes.SCALE, 3.0)", self.store.task_instructions(task[0]["id"]))

    def test_errors(self):
        with self.assertRaisesRegex(InputError, "Unknown mob"):
            set_mob_scale(self.store, "r_mod", "ghost", 1.5)
        with self.assertRaisesRegex(InputError, "scale"):
            set_mob_scale(self.store, "r_mod", "runner", 40)
        with self.assertRaisesRegex(InputError, "number"):
            set_mob_scale(self.store, "r_mod", "runner", "big")
        self.assertEqual(self.scale(), 1.0)

    def test_cli(self):
        self.generate()
        out = dispatch(parser().parse_args(["--state-db", str(self.db), "edit-model", "r_mod", "--mob", "runner", "--scale", "1.5"]))
        self.assertEqual((out["how"], out["scale"]), ("patched", 1.5))


if __name__ == "__main__":
    unittest.main()
