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
            self.assertEqual([a["name"] for a in rec["animations"]], [f"animation.{plan}.idle", f"animation.{plan}.walk"])
            bones = {b["name"] for b in rec["bones"]}
            for a in rec["animations"]:
                self.assertEqual(a["loop"], "loop")
                for ch in a["channels"]:
                    self.assertIn(ch["bone"], bones, (plan, a["name"]))
                    keys = ch["keyframes"]
                    self.assertEqual(keys[0]["value"], keys[-1]["value"], f"{plan}/{a['name']}/{ch['bone']}: loop seam")
                    for k in keys:
                        self.assertAlmostEqual(round(k["time"] / 0.05) * 0.05, k["time"], places=6, msg=(plan, a["name"], k))


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
            self.assertEqual(set(anim["animations"]), {f"animation.{plan}.idle", f"animation.{plan}.walk"})
            renamed = rigs.rig_animation_for(plan, "my_mob")
            self.assertEqual(set(renamed["animations"]), {"animation.my_mob.idle", "animation.my_mob.walk"})
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
        self.assertEqual(set(anim["animations"]), {"animation.cave_golem.idle", "animation.cave_golem.walk"})
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
        self.assertEqual({a["name"] for a in m["animations"]}, {"animation.cave_golem.idle", "animation.cave_golem.walk"})
        src.write_text(src.read_text().replace('"name": "torso"', '"name": "chest"'))  # the designer edited it
        self.assertIn("already present", rig_block(self.store, "r_mod", "cave_golem", self.root))
        self.assertIn('"chest"', src.read_text())  # not overwritten

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_staged_source_validates_and_exports_with_the_server(self):
        """The renamed .bbmodel is something the designer's tools accept as-is."""
        from mod_orchestra.models import rig_block, MODEL_DIR
        rig_block(self.store, "r_mod", "cave_golem", self.root)
        script = ("import {readFileSync} from 'node:fs';"
                  f"import {{validateGecko, exportGeometry, exportAnimations}} from '{ROOT}/tools/blockbench-mcp-safe/src/geckolib.mjs';"
                  f"const m=JSON.parse(readFileSync('{self.root / MODEL_DIR / 'cave_golem.bbmodel'}','utf8'));"
                  "const v=validateGecko(m); if(!v.valid) throw Error(JSON.stringify(v));"
                  "console.log(JSON.stringify({id:exportGeometry(m)['minecraft:geometry'][0].description.identifier, clips:Object.keys(exportAnimations(m).animations)}));")
        proc = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out, {"id": "geometry.cave_golem", "clips": ["animation.cave_golem.idle", "animation.cave_golem.walk"]})


if __name__ == "__main__":
    unittest.main()
