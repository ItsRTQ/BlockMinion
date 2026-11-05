import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mod_orchestra import rigs

ROOT = Path(__file__).resolve().parents[1]
BONE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class TestRecipes(unittest.TestCase):
    def test_every_body_plan_has_a_recipe_and_committed_files(self):
        self.assertEqual(set(rigs.BODY_PLANS), set(rigs.RECIPES))
        for plan in rigs.BODY_PLANS:
            for kind in ("bbmodel", "geo", "anim", "recipe"):
                self.assertTrue(rigs.rig_path(plan, kind).is_file(), (plan, kind))

    def test_committed_recipe_matches_code(self):
        """scripts/regen_rigs.py must be re-run when a recipe changes."""
        for plan in rigs.BODY_PLANS:
            self.assertEqual(rigs.load_rig(plan, "recipe"), rigs.recipe(plan), f"{plan}: run scripts/regen_rigs.py {plan}")

    def test_bones_are_well_formed_and_paired(self):
        for plan in rigs.BODY_PLANS:
            rec = rigs.recipe(plan)
            names = [b["name"] for b in rec["bones"]]
            self.assertEqual(len(names), len(set(names)), plan)
            self.assertTrue(all(BONE.match(n) for n in names), plan)
            self.assertIsNone(rec["bones"][0].get("parent"), f"{plan}: first bone is the root")
            self.assertEqual(sum(1 for b in rec["bones"] if not b.get("parent")), 1, f"{plan}: single root")
            by_name = {b["name"]: b for b in rec["bones"]}
            for b in rec["bones"]:
                if b.get("parent"):
                    self.assertIn(b["parent"], by_name, (plan, b["name"]))
                if b["name"].startswith("left_"):
                    other = by_name["right_" + b["name"][5:]]
                    self.assertEqual(other["origin"], [-b["origin"][0], b["origin"][1], b["origin"][2]], (plan, b["name"]))
            for c in rec["cubes"]:
                self.assertIn(c["bone"], by_name, (plan, c["name"]))
                self.assertTrue(all(c["from"][i] < c["to"][i] for i in range(3)), (plan, c["name"]))

    def test_clips_are_idle_and_walk_on_tick_boundaries(self):
        for plan in rigs.BODY_PLANS:
            rec = rigs.recipe(plan)
            self.assertEqual([a["name"] for a in rec["animations"]], [f"animation.{plan}.idle", f"animation.{plan}.walk", f"animation.{plan}.attack"])
            bones = {b["name"] for b in rec["bones"]}
            for a in rec["animations"]:
                self.assertEqual(a["loop"], "once" if a["name"].endswith(".attack") else "loop")
                for ch in a["channels"]:
                    self.assertIn(ch["bone"], bones, (plan, a["name"]))
                    keys = ch["keyframes"]
                    self.assertEqual(keys[0]["time"], 0.0); self.assertEqual(keys[-1]["time"], a["length"], (plan, a["name"], ch["bone"]))
                    if a["loop"] == "loop":
                        self.assertEqual(keys[0]["value"], keys[-1]["value"], f"{plan}/{a['name']}/{ch['bone']}: loop seam")
                    else:  # one-shot: starts and ends at rest so it blends with idle/walk
                        self.assertEqual(keys[0]["value"], [0, 0, 0]); self.assertEqual(keys[-1]["value"], [0, 0, 0])
                    self.assertEqual([k["time"] for k in keys], sorted(k["time"] for k in keys))
                    for k in keys:
                        self.assertAlmostEqual(round(k["time"] / 0.05) * 0.05, k["time"], places=6, msg=(plan, a["name"], k))


    def test_root_is_empty_and_limbs_are_jointed(self):
        for plan in rigs.BODY_PLANS:
            rec = rigs.recipe(plan)
            self.assertEqual(rec["bones"][0], {"name": "root", "origin": [0, 0, 0]})
            self.assertFalse([c for c in rec["cubes"] if c["bone"] == "root"], plan)
        bones = {b["name"]: b for b in rigs.recipe("biped")["bones"]}
        self.assertEqual(bones["left_arm_forearm"]["parent"], "left_arm"); self.assertEqual(bones["left_leg_shin"]["parent"], "left_leg")
        b, c = rigs.jointed_limb("left_x", "body", [("", [1, 2, 3], [0, 0, 0], [1, 1, 1]), ("lower", [1, 1, 3], [0, -1, 0], [1, 0, 1])])
        self.assertEqual([x["name"] for x in b], ["left_x", "left_x_lower"]); self.assertEqual(b[1]["parent"], "left_x"); self.assertEqual(c[1]["bone"], "left_x_lower")


    def test_combine_drift_lift_helpers(self):
        a = rigs.swing("b", 1.0, 20, 1, axis=1); b = rigs.lift("b", 1.0, 10, 1, axis=2)
        c = rigs.combine(a, b)
        self.assertEqual([k["time"] for k in c["keyframes"]], [0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertEqual(c["keyframes"][3]["value"], [0.0, 0.0, 10.0])          # phase 1 moves forward in the second half: sweep crosses zero at 0.75, lift at its peak
        self.assertEqual(c["keyframes"][1]["value"], [0.0, 0.0, 0.0])           # ... and the foot stays planted while it pushes back
        self.assertEqual(c["keyframes"][0]["value"], c["keyframes"][-1]["value"])
        self.assertEqual(rigs.lift("b", 1.0, 10, -1, axis=2)["keyframes"][1]["value"], [0.0, 0.0, 10.0])   # phase -1 swings forward in the first half
        d = rigs.drift("h", 2.0, (2, 3, 1), seed=1, spike=(1.3, 0, -8))
        times = [k["time"] for k in d["keyframes"]]
        self.assertEqual(times, sorted(times)); self.assertEqual(len(times), len(set(times)))
        self.assertEqual(d["keyframes"][0]["value"], [0.0, 0.0, 0.0]); self.assertEqual(d["keyframes"][-1]["value"], [0.0, 0.0, 0.0])
        self.assertTrue(any(k["time"] == 1.35 and k["value"][0] == -8 for k in d["keyframes"]))
        self.assertTrue(all(abs(v) <= 3 for k in d["keyframes"] for v in k["value"] if k["time"] not in (1.3, 1.35, 1.4)))
        self.assertNotEqual(rigs.drift("x", 2.0, (2, 2, 2), seed=0)["keyframes"][2]["value"], rigs.drift("x", 2.0, (2, 2, 2), seed=1)["keyframes"][2]["value"])

    def test_rest_rotation_lives_on_bones_and_is_mirrored_in_geo(self):
        rec = rigs.recipe("insect"); bones = {b["name"]: b for b in rec["bones"]}
        self.assertEqual(bones["left_front_leg"]["rotation"], [0, -20, 35]); self.assertEqual(bones["right_front_leg"]["rotation"], [0, 20, -35])
        geo = {b["name"]: b for b in rigs.load_rig("insect", "geo")["minecraft:geometry"][0]["bones"]}
        self.assertEqual(geo["left_front_leg"]["rotation"], [0, 20, 35])       # export flips X and Y rotation
        self.assertFalse(any(c.get("rotation") for b in geo.values() for c in b.get("cubes", [])), "shape comes from bone rest pose, not cube rotation")


    def test_snap_and_chain_helpers(self):
        c = rigs.curve("a", "rotation", [(0, [0, 0, 0]), (0.3, [-100, 0, 0]), (0.45, [20, 0, 0]), (1.0, [0, 0, 0])], snap=2)
        self.assertEqual([k["interpolation"] for k in c["keyframes"]], ["catmullrom", "linear", "linear", "catmullrom"])
        for plan in rigs.BODY_PLANS:   # every attack has a linear impact pair
            atk = next(a for a in rigs.recipe(plan)["animations"] if a["name"].endswith(".attack"))
            self.assertTrue(any([k["interpolation"] for k in ch["keyframes"]].count("linear") >= 2 for ch in atk["channels"]), plan)
        ch = rigs.chain(["s1", "s2", "s3"], 1.0, 10, axis=1, lag=0.25, grow=2, samples=8)
        self.assertEqual([c["bone"] for c in ch], ["s1", "s2", "s3"])
        for c in ch:
            self.assertEqual(c["keyframes"][0]["value"], c["keyframes"][-1]["value"])
        peak = lambda c: max(abs(k["value"][1]) for k in c["keyframes"])
        self.assertLess(peak(ch[0]), peak(ch[1])); self.assertLess(peak(ch[1]), peak(ch[2]))   # amplitude grows to the tip
        self.assertEqual(ch[0]["keyframes"][2]["value"][1], 10.0); self.assertEqual(ch[1]["keyframes"][4]["value"][1], 20.0)   # lag of a quarter cycle


    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_every_foot_lifts_in_the_forward_swing(self):
        """Regression: knees flexed in the push-off half of the cycle (foot raised while it travels backward) on every walking rig."""
        for plan in ("quadruped", "biped", "insect"):
            proc = subprocess.run(["node", str(ROOT / "scripts/gait_check.mjs"), str(rigs.rig_path(plan, "bbmodel")), f"animation.{plan}.walk"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            legs = json.loads(proc.stdout)["legs"]
            self.assertGreaterEqual(len(legs), 2, plan)
            self.assertEqual([l["bone"] for l in legs if not l["ok"]], [], f"{plan}: feet raised while pushing back")


class TestPacker(unittest.TestCase):
    def test_strips_never_overlap_and_fit(self):
        for plan in rigs.BODY_PLANS:
            rec = rigs.recipe(plan)
            w, h = rec["texture_width"], rec["texture_height"]
            boxes = []
            for c in rec["cubes"]:
                sw, sh = rigs.strip_size(c["from"], c["to"])
                x, y = c["uv_offset"]
                self.assertTrue(0 <= x and x + sw <= w and 0 <= y and y + sh <= h, (plan, c["name"]))
                for (bx, by, bw, bh, bn) in boxes:
                    self.assertTrue(x >= bx + bw or bx >= x + sw or y >= by + bh or by >= y + sh, (plan, c["name"], bn))
                boxes.append((x, y, sw, sh, c["name"]))

    def test_packer_rejects_small_texture(self):
        cubes = [{"name": "big", "from": [0, 0, 0], "to": [16, 16, 16]}]
        with self.assertRaises(ValueError):
            rigs.pack_box_uv(cubes, 32, 32)
        self.assertEqual(rigs.pack_box_uv(cubes, 64, 32)[0]["uv_offset"], [0, 0])


class TestExports(unittest.TestCase):
    def test_geo_mirrors_recipe_bones(self):
        for plan in rigs.BODY_PLANS:
            rec, geo = rigs.recipe(plan), rigs.load_rig(plan, "geo")
            desc = geo["minecraft:geometry"][0]["description"]
            self.assertEqual(desc["identifier"], f"geometry.{plan}")
            self.assertEqual((desc["texture_width"], desc["texture_height"]), (rec["texture_width"], rec["texture_height"]))
            bones = geo["minecraft:geometry"][0]["bones"]
            self.assertEqual([b["name"] for b in bones], [b["name"] for b in rec["bones"]])
            for rb, gb in zip(rec["bones"], bones):
                self.assertEqual(gb.get("parent"), rb.get("parent"))
                self.assertEqual(gb["pivot"], [-rb["origin"][0], rb["origin"][1], rb["origin"][2]], (plan, rb["name"]))  # X mirrored
            self.assertEqual(sum(len(b.get("cubes", [])) for b in bones), len(rec["cubes"]))

    def test_animation_export_names_and_renaming(self):
        for plan in rigs.BODY_PLANS:
            anim = rigs.load_rig(plan, "anim")
            self.assertEqual(set(anim["animations"]), {f"animation.{plan}.idle", f"animation.{plan}.walk", f"animation.{plan}.attack"})
            self.assertNotIn("loop", anim["animations"][f"animation.{plan}.attack"])  # one-shot
            renamed = rigs.rig_animation_for(plan, "my_mob")
            self.assertEqual(set(renamed["animations"]), {"animation.my_mob.idle", "animation.my_mob.walk", "animation.my_mob.attack"})
            self.assertEqual(rigs.rig_geo_for(plan, "my_mob")["minecraft:geometry"][0]["description"]["identifier"], "geometry.my_mob")
            self.assertEqual(rigs.load_rig(plan, "geo")["minecraft:geometry"][0]["description"]["identifier"], f"geometry.{plan}")

    def test_bbmodel_is_a_geckolib_model_with_matching_structure(self):
        for plan in rigs.BODY_PLANS:
            m, rec = rigs.load_rig(plan, "bbmodel"), rigs.recipe(plan)
            self.assertEqual((m["meta"]["format_version"], m["meta"]["model_format"]), ("5.0", "geckolib_model"))
            self.assertEqual(m["model_identifier"], plan)
            self.assertEqual([g["name"] for g in m["groups"]], [b["name"] for b in rec["bones"]])
            self.assertEqual(len(m["elements"]), len(rec["cubes"]))
            self.assertTrue(all(e["type"] == "cube" for e in m["elements"]))

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_rebuild_is_deterministic_and_matches_committed(self):
        for plan in rigs.BODY_PLANS:
            with tempfile.TemporaryDirectory() as tmp:
                rpath = Path(tmp) / "r.json"
                rpath.write_text(json.dumps(rigs.recipe(plan)), encoding="utf8")
                proc = subprocess.run(["node", str(ROOT / "scripts/build_rig.mjs"), str(rpath), tmp], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                report = json.loads(proc.stdout)
                self.assertTrue(report["validate"]["valid"], (plan, report))
                self.assertEqual(report["quality"].get("errors", []), [], plan)
                for kind, ext in (("bbmodel", "bbmodel"), ("geo", "geo.json"), ("anim", "animation.json")):
                    self.assertEqual((Path(tmp) / f"{plan}.{ext}").read_text(encoding="utf8"),
                                     rigs.rig_path(plan, kind).read_text(encoding="utf8"), (plan, kind))


class TestIntegration(unittest.TestCase):
    """body_plan flows from add-mob into the generated placeholders and the staged designer source."""

    def setUp(self):
        from unittest.mock import patch
        from mod_orchestra import workflow
        from mod_orchestra.specedit import add_mob
        from mod_orchestra.state import Store
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="R", mod_id="r_mod", package="com.x.r", idea="mobs: cave golem; items: pebble")
        add_mob(self.store, "r_mod", identifier="cave_golem", label="Cave Golem", body_plan="biped")
        workflow.plan_project(self.store, "r_mod"); workflow.approve_spec(self.store, "r_mod"); workflow.generate_project(self.store, "r_mod")
        self.root = Path(proj["root"]); self.res = self.root / "src/main/resources/assets/r_mod"

    def test_placeholders_use_the_body_plan_rig(self):
        geo = json.loads((self.res / "geo/entity/cave_golem.geo.json").read_text())
        self.assertEqual(geo["minecraft:geometry"][0]["description"]["identifier"], "geometry.cave_golem")
        self.assertEqual([b["name"] for b in geo["minecraft:geometry"][0]["bones"]], [b["name"] for b in rigs.recipe("biped")["bones"]])
        anim = json.loads((self.res / "animations/entity/cave_golem.animation.json").read_text())
        self.assertEqual(set(anim["animations"]), {"animation.cave_golem.idle", "animation.cave_golem.walk", "animation.cave_golem.attack"})
        png = (self.res / "textures/entity/cave_golem.png").read_bytes()
        self.assertEqual((int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")), (64, 64))  # biped resolution

    def test_invalid_body_plan_rejected(self):
        from mod_orchestra.specedit import add_mob
        from mod_orchestra.validation import InputError
        with self.assertRaises(InputError):
            add_mob(self.store, "r_mod", identifier="thing", label="Thing", body_plan="centaur")

    def test_rig_block_stages_source_once(self):
        from mod_orchestra.models import rig_block, MODEL_DIR
        text = rig_block(self.store, "r_mod", "cave_golem", self.root)
        self.assertIn("Base rig: biped", text); self.assertIn("placed now", text); self.assertIn("left_arm (child of body)", text)
        src = self.root / MODEL_DIR / "cave_golem.bbmodel"
        m = json.loads(src.read_text())
        self.assertEqual((m["model_identifier"], m["mod_id"], m["meta"]["model_format"]), ("cave_golem", "r_mod", "geckolib_model"))
        self.assertEqual({a["name"] for a in m["animations"]}, {"animation.cave_golem.idle", "animation.cave_golem.walk", "animation.cave_golem.attack"})
        src.write_text(src.read_text().replace('"name": "torso"', '"name": "chest"'))  # the designer edited it
        self.assertIn("already present", rig_block(self.store, "r_mod", "cave_golem", self.root))
        self.assertIn('"chest"', src.read_text())  # not overwritten

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_staged_source_validates_and_exports_with_the_server(self):
        """The renamed .bbmodel is something the designer's tools accept as-is."""
        from mod_orchestra.models import rig_block, MODEL_DIR
        rig_block(self.store, "r_mod", "cave_golem", self.root)
        server = (ROOT / "tools/blockbench-mcp-safe/src/geckolib.mjs").as_uri()          # file:// works on every OS for ESM imports
        source = (self.root / MODEL_DIR / "cave_golem.bbmodel").as_posix()               # no backslash escapes inside the JS string
        script = ("import {readFileSync} from 'node:fs';"
                  f"import {{validateGecko, exportGeometry, exportAnimations}} from '{server}';"
                  f"const m=JSON.parse(readFileSync('{source}','utf8'));"
                  "const v=validateGecko(m); if(!v.valid) throw Error(JSON.stringify(v));"
                  "console.log(JSON.stringify({id:exportGeometry(m)['minecraft:geometry'][0].description.identifier, clips:Object.keys(exportAnimations(m).animations)}));")
        proc = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out, {"id": "geometry.cave_golem", "clips": ["animation.cave_golem.idle", "animation.cave_golem.walk", "animation.cave_golem.attack"]})


if __name__ == "__main__":
    unittest.main()


class TestSetBodyPlan(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        from mod_orchestra import workflow
        from mod_orchestra.state import Store
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "s.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop); (base / "projects").mkdir()
        workflow.new_project(self.store, name="G", mod_id="g_mod", package="com.x.g", idea="hostile mobs: brute, scout; mobs: pig")
        workflow.plan_project(self.store, "g_mod"); workflow.approve_spec(self.store, "g_mod")

    def plans(self):
        return {m["identifier"]: m["body_plan"] for m in self.store.project("g_mod")["spec"]["mobs"]}

    def test_changes_named_mobs_and_returns_the_spec_to_draft(self):
        from mod_orchestra.specedit import set_body_plan
        out = set_body_plan(self.store, "g_mod", "biped", ["brute", "scout"])
        self.assertEqual(out["spec_state"], "DRAFT")
        self.assertEqual(self.plans(), {"brute": "biped", "scout": "biped", "pig": "quadruped"})

    def test_all_mobs_when_none_named_and_validation(self):
        from mod_orchestra.specedit import set_body_plan
        from mod_orchestra.validation import InputError
        set_body_plan(self.store, "g_mod", "insect")
        self.assertEqual(set(self.plans().values()), {"insect"})
        with self.assertRaises(InputError):
            set_body_plan(self.store, "g_mod", "centaur")
        with self.assertRaisesRegex(InputError, "unknown mob"):
            set_body_plan(self.store, "g_mod", "biped", ["ghost"])
