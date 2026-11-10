"""3D models for items, on demand: the designer builds it, the controller installs and wires it without touching item code."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import model3d, workflow
from mod_orchestra.cli import dispatch as cli_dispatch, parser
from mod_orchestra.content import list_features
from mod_orchestra.dispatch import dispatch
from mod_orchestra.fabric import accept_changes, validate_generated
from mod_orchestra.provider import FakeProvider
from mod_orchestra.skin import encode_png
from mod_orchestra.specedit import add_material
from mod_orchestra.state import Store, StateError
from mod_orchestra.validation import InputError

ROOT = Path(__file__).resolve().parents[1]
PNG = encode_png(16, 16, bytes(c for y in range(16) for x in range(16) for c in ((90, 90, 110, 255) if (x + y) % 3 else (200, 200, 220, 255))))


def handoff(task, status="DONE"):
    h = {"task": task, "status": status, "scope": "model", "changed_files": [], "checks_run": [{"command": "bbmodel_geckolib_validate", "exit_code": 0}],
         "evidence": {"level": "STATIC", "pointer": "models/items3d"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "coder"}
    return "```handoff\n" + json.dumps(h) + "\n```"


class Base(unittest.TestCase):
    IDEA = "items: moon gem; blocks: moon ore; hostile mobs: moon beast; tab: Moon"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.db = base / "state.sqlite"; self.store = Store(self.db)
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        self.ws = Path(workflow.new_project(self.store, name="M", mod_id="m_mod", package="com.x.m", idea=self.IDEA)["root"])
        add_material(self.store, "m_mod", identifier="moon", label="Moon", ingredient="moon_gem", tools=["sword"], armor=["helmet"])
        workflow.plan_project(self.store, "m_mod"); workflow.approve_spec(self.store, "m_mod"); workflow.generate_project(self.store, "m_mod")
        self.res = self.ws / "src/main/resources"; self.assets = self.res / "assets/m_mod"

    def deliver(self, ident="moon_sword", *, ident_in_geo=None, cubes=None, tex=(16, 16), render=True, animated=True):
        d = self.ws / model3d.DIR; d.mkdir(parents=True, exist_ok=True)
        cubes = cubes if cubes is not None else [{"origin": [-1, 2, -0.5], "size": [2, 13, 1], "uv": [0, 0]}]
        geo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": ident_in_geo or f"geometry.{ident}", "texture_width": tex[0], "texture_height": tex[1]},
                                                                    "bones": [{"name": "blade", "pivot": [0, 0, 0], "cubes": cubes}]}]}
        idle = {"loop": True, "animation_length": 1, "bones": {"blade": {"rotation": {"0.0": {"vector": [0, 0, 0]}}}} if animated else {}}
        (d / f"{ident}.geo.json").write_text(json.dumps(geo))
        (d / f"{ident}.animation.json").write_text(json.dumps({"format_version": "1.8.0", "animations": {f"animation.{ident}.idle": idle}}))
        (d / f"{ident}.png").write_bytes(PNG); (d / f"{ident}.bbmodel").write_text("{}")
        if render:
            (d / f"{ident}_render.png").write_bytes(PNG)

    def task(self, ident="moon_sword", notes=""):
        return model3d.request_item3d(self.store, "m_mod", ident, notes)["task"]

    def tasks(self, kind):
        return [t for t in self.store.tasks("m_mod") if f":{kind}:" in t["id"]]


class Request(Base):
    def test_what_can_be_3d(self):
        from mod_orchestra.spec import read_spec
        cand = model3d.candidates(read_spec(self.store.project("m_mod")["spec"]))
        self.assertIn("moon_gem", cand); self.assertTrue(cand["moon_sword"]["handheld"]); self.assertFalse(cand["moon_gem"]["handheld"])
        self.assertNotIn("moon_ore", cand); self.assertNotIn("moon_helmet", cand)
        rows = {r["identifier"]: r for r in list_features(self.store, "m_mod")}
        self.assertTrue(rows["moon_sword"]["can3d"]); self.assertTrue(rows["moon_ore"]["can3d"], "blocks too (blocks3d)"); self.assertFalse(rows["moon_helmet"]["can3d"])
        self.assertFalse(rows["moon_sword"]["model3d"])

    def test_the_designer_brief(self):
        tid = self.task(notes="a crescent blade")
        t = next(x for x in self.store.tasks("m_mod") if x["id"] == tid)
        brief = self.store.task_instructions(tid)
        self.assertEqual(t["role"], "designer")
        self.assertIn("models/items3d/moon_sword.bbmodel", brief); self.assertIn("textures/item/moon_sword.png", brief)
        self.assertIn('"hold": {"style": "aim", "front": "-z", "top": "+y"}', brief); self.assertIn("orchestra_preview_hold", brief)
        self.assertIn("a crescent blade", brief); self.assertIn("held like a tool or weapon", brief)
        self.assertIn("art direction:", brief)
        self.deliver()
        self.assertIn("already exists", self.store.task_instructions(self.task(notes="thicker")))
        self.assertIn("- a crescent blade", self.store.task_instructions(self.tasks("ITEM3D")[-1]["id"]))

    def test_refusals_and_estimate(self):
        with self.assertRaisesRegex(InputError, "cannot get a 3D model"):
            self.task("moon_ore")
        self.assertEqual(model3d.designer_cost(self.store), {"runs": 0})
        for cost, secs in ((10.0, 600), (20.0, 1200)):
            run = self.store.create_run("m_mod", self.task(), "designer", "fake")
            self.store.finish_run(run["id"], state="DONE", exit_code=0, duration_s=secs, log_path="x", cost_usd=cost)
        self.assertEqual(model3d.designer_cost(self.store), {"runs": 2, "avg_usd": 15.0, "max_usd": 20.0, "avg_minutes": 15.0})


class Validate(Base):
    def test_each_rule(self):
        cases = [({"render": False}, "no render"), ({"ident_in_geo": "geometry.other"}, "identifier must be geometry.moon_sword"),
                 ({"cubes": []}, "no cubes"), ({"cubes": [{"origin": [-1, 0, 0], "size": [2, 30, 1], "uv": [0, 0]}]}, "keep it within"),
                 ({"tex": (32, 32)}, "texture is 16x16")]
        for kw, why in cases:
            with self.subTest(why=why):
                for f in (self.ws / model3d.DIR).glob("*"):
                    f.unlink()
                self.deliver(**kw)
                with self.assertRaisesRegex(InputError, why):
                    model3d.validate_item3d(self.ws, "moon_sword")
        for f in (self.ws / model3d.DIR).glob("*"):
            f.unlink()
        with self.assertRaisesRegex(InputError, "missing"):
            model3d.validate_item3d(self.ws, "moon_sword")
        self.deliver(animated=False)
        self.assertFalse(model3d.validate_item3d(self.ws, "moon_sword")["animated"])


class Install(Base):
    def test_a_fresh_project_is_wired_without_touching_item_code(self):
        main = (self.ws / "src/main/java/com/x/m/ModMain.java").read_text()
        tid = self.task(); self.deliver()
        out = dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        for rel in ("geo/item/model3d/moon_sword.geo.json", "animations/item/model3d/moon_sword.animation.json", "textures/item/model3d/moon_sword.png"):
            self.assertTrue((self.assets / rel).is_file(), rel)
        entry = json.loads((self.assets / "model3d/index.json").read_text())["items"][0]
        self.assertEqual((entry["id"], entry["animated"], entry["hold"]["style"], entry["hold"]["front"]), ("moon_sword", True, "wield", "+y"), "a tool defaults to wield")
        fmj = json.loads((self.res / "fabric.mod.json").read_text())
        self.assertIn("com.x.m.client.Model3DClient", fmj["entrypoints"]["client"]); self.assertIn("geckolib", fmj["depends"])
        item = json.loads((self.assets / "models/item/moon_sword.json").read_text())
        self.assertEqual(item["parent"], "builtin/entity")
        from mod_orchestra import pose
        want = pose.display(json.loads((self.ws / model3d.DIR / "moon_sword.bbmodel").read_text()), style="wield", front="+y")
        self.assertEqual(item["display"]["thirdperson_righthand"], want["thirdperson_righthand"], "held as the pose engine computes, not as a sprite")
        self.assertEqual(item["display"]["gui"]["scale"], [1, 1, 1])
        self.assertTrue((self.ws / ".mod-orchestra/items3d/moon_sword.icon-model.json").is_file(), "the icon's model is kept")
        self.assertEqual((self.ws / "src/main/java/com/x/m/ModMain.java").read_text(), main, "item code untouched")
        self.assertEqual(self.tasks("ITEM3DWIRE"), [])
        self.assertEqual(validate_generated(self.ws)["status"], "PASS")
        self.assertTrue({r["identifier"]: r for r in list_features(self.store, "m_mod")}["moon_sword"]["model3d"])
        java = (self.ws / "src/main/java/com/x/m/client/Item3DRenderer.java").read_text()
        self.assertIn("mode == ItemDisplayContext.GUI", java); self.assertIn("textures/item/model3d/", java); self.assertIn("translate(0f, -0.51f, 0f)", java)

    def test_a_plain_item_keeps_the_generated_transforms_and_a_second_item_extends_the_index(self):
        for ident in ("moon_sword", "moon_gem"):
            tid = self.task(ident); self.deliver(ident, animated=ident == "moon_sword")
            self.assertEqual(dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))["task_state"], "DONE")
        gem = json.loads((self.assets / "model3d/index.json").read_text())["items"][1]
        self.assertEqual(gem["hold"]["style"], "carry", "a plain item defaults to carry")
        self.assertEqual([i["id"] for i in json.loads((self.assets / "model3d/index.json").read_text())["items"]], ["moon_sword", "moon_gem"])

    def test_files_with_unreported_edits_go_to_the_coder(self):
        fmj = self.res / "fabric.mod.json"; fmj.write_text(fmj.read_text().replace('"main"', '"main"  '))
        model = self.assets / "models/item/moon_sword.json"; edited = model.read_text() + "\n"; model.write_text(edited)
        tid = self.task(); self.deliver()
        out = dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        self.assertEqual(model.read_text(), edited); self.assertNotIn("Model3DClient", fmj.read_text())
        wire = self.tasks("ITEM3DWIRE")
        self.assertEqual([t["role"] for t in wire], ["coder"])
        brief = self.store.task_instructions(wire[0]["id"])
        self.assertIn("com.x.m.client.Model3DClient", brief); self.assertIn('"builtin/entity"', brief)

    def test_an_accepted_edit_is_patched(self):
        model = self.assets / "models/item/moon_sword.json"; model.write_text(model.read_text() + "\n")
        accept_changes(self.ws, run_id="coder", actor="coder", changed=["src/main/resources/assets/m_mod/models/item/moon_sword.json"])
        tid = self.task(); self.deliver()
        dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(json.loads(model.read_text())["parent"], "builtin/entity"); self.assertEqual(self.tasks("ITEM3DWIRE"), [])

    def test_a_bad_delivery_installs_nothing(self):
        tid = self.task(); self.deliver(render=False)
        out = dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("no render", out["error"])
        self.assertFalse((self.assets / "model3d/index.json").exists())

    def test_cli(self):
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "make-3d", "m_mod", "--item", "moon_sword", "--notes", "x"]))
        self.assertTrue(out["task"].startswith("m_mod:ITEM3D:moon_sword"))


class Actions(Base):
    def deliver_anims(self, anims):
        self.deliver()
        (self.ws / model3d.DIR / "moon_sword.animation.json").write_text(json.dumps({"format_version": "1.8.0", "animations": anims}))

    KEY = {"blade": {"rotation": {"0.0": {"vector": [0, 0, 0]}, "0.2": {"vector": [-20, 0, 0]}}}}

    def test_actions_are_found_and_named_or_refused(self):
        self.deliver_anims({"animation.moon_sword.use": {"loop": False, "animation_length": 0.3, "bones": self.KEY},
                            "animation.moon_sword.reload": {"animation_length": 1, "bones": self.KEY}})
        info = model3d.validate_item3d(self.ws, "moon_sword")
        self.assertEqual((info["actions"], info["animated"]), (["reload", "use"], False))
        self.deliver_anims({"animation.moon_sword.aim": {"loop": True, "bones": self.KEY}})
        self.assertEqual(model3d.validate_item3d(self.ws, "moon_sword")["loops"], ["aim"], "an action that lasts loops")
        for anims, why in (({"animation.other.wobble": {"bones": self.KEY}}, "name it animation.moon_sword"),):
            with self.subTest(why=why):
                self.deliver_anims(anims)
                with self.assertRaisesRegex(InputError, why):
                    model3d.validate_item3d(self.ws, "moon_sword")

    def test_actions_go_to_a_coder_with_the_recipe(self):
        tid = self.task(); self.deliver_anims({"animation.moon_sword.idle": {"loop": True, "bones": self.KEY},
                                               "animation.moon_sword.attack": {"bones": self.KEY}, "animation.moon_sword.reload": {"bones": self.KEY}})
        out = dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        anim = self.tasks("ITEM3DANIM")
        self.assertEqual([(t["role"], t["state"]) for t in anim], [("coder", "READY")])
        brief = self.store.task_instructions(anim[0]["id"])
        self.assertIn('Item3DActions.controllers(this, controllers, "moon_sword", true, "attack", "reload");', brief)
        self.assertIn('new Item3DGeoRenderer<>(ModMain.MOD_ID, "moon_sword")', brief)
        self.assertIn('hurtEnemy(...)): Item3DActions.trigger(this, attacker, stack, "attack")', brief)
        self.assertIn('at the moment its name describes', brief)
        self.assertEqual(json.loads((self.assets / "model3d/index.json").read_text())["items"][0]["actions"], ["attack", "reload"])
        for name in ("model3d/Item3DActions.java", "client/Item3DGeoRenderer.java"):
            self.assertTrue((self.ws / "src/main/java/com/x/m" / name).is_file(), name)
        self.assertIn("instanceof software.bernie.geckolib.animatable.GeoItem", (self.ws / "src/main/java/com/x/m/client/Model3DClient.java").read_text())
        # a new model before the coder starts rewrites the same brief
        tid = self.task(); self.deliver_anims({"animation.moon_sword.use": {"bones": self.KEY}})
        dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(len(self.tasks("ITEM3DANIM")), 1)
        self.assertIn('false, "use");', self.store.task_instructions(anim[0]["id"]))

    def test_no_actions_no_coder(self):
        tid = self.task(); self.deliver()
        dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(self.tasks("ITEM3DANIM"), [])

    def test_an_older_support_file_is_updated_unless_someone_edited_it(self):
        tid = self.task(); self.deliver(); dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        client = self.ws / "src/main/java/com/x/m/client/Model3DClient.java"
        old = client.read_text().replace("                if (item instanceof software.bernie.geckolib.animatable.GeoItem) continue;   // it draws itself (Item3DGeoRenderer) and plays its actions\n", "")
        client.write_text(old); accept_changes(self.ws, run_id="older", actor="controller", changed=["src/main/java/com/x/m/client/Model3DClient.java"])
        from mod_orchestra.spec import read_spec
        written, coder = model3d.ensure_support(self.ws, read_spec(self.store.project("m_mod")["spec"]))
        self.assertIn("src/main/java/com/x/m/client/Model3DClient.java", written); self.assertEqual(coder, [])
        self.assertIn("instanceof", client.read_text())
        client.write_text(old + "// hand edit\n")
        written, coder = model3d.ensure_support(self.ws, read_spec(self.store.project("m_mod")["spec"]))
        self.assertEqual(len(coder), 1); self.assertIn("// hand edit", client.read_text())


class Projectile(Base):
    SPRITE = "src/main/resources/assets/m_mod/textures/item/acid_glob.png"

    def setUp(self):
        super().setUp()
        self.store.add_event("m_mod", "controller", "ART_REQUESTED", {"task": "m_mod:ART:acid_spit", "card": "acid_spit", "assets": [
            {"id": "acid_glob", "kind": "projectile", "path": self.SPRITE, "size": [16, 16], "for": ["moon_beast"], "what": "a glob of acid the beast spits"}]})

    def deliver_p(self, cubes=None):
        d = self.ws / model3d.PDIR; d.mkdir(parents=True, exist_ok=True)
        cubes = cubes or [{"origin": [-3, -2, -2], "size": [6, 4, 4], "uv": [0, 0]}]
        geo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": "geometry.acid_glob", "texture_width": 16, "texture_height": 16},
                                                                    "bones": [{"name": "glob", "pivot": [0, 0, 0], "cubes": cubes}]}]}
        (d / "acid_glob.geo.json").write_text(json.dumps(geo)); (d / "acid_glob.animation.json").write_text('{"animations": {}}')
        for name in ("acid_glob.png", "acid_glob_render.png"):
            (d / name).write_bytes(PNG)
        (d / "acid_glob.bbmodel").write_text("{}")

    def test_the_designer_then_the_coder_switches_the_renderer(self):
        self.assertEqual(model3d.projectile_assets(self.store, "m_mod")["acid_glob"]["card"], "acid_spit")
        tid = model3d.request_proj3d(self.store, "m_mod", "acid_glob", "spiky")["task"]
        brief = self.store.task_instructions(tid)
        self.assertIn("toward +X", brief); self.assertIn(self.SPRITE, brief); self.assertIn("spiky", brief)
        self.assertIn("it belongs to moon_beast (mob)", brief)
        self.deliver_p()
        out = dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        self.assertTrue((self.assets / "geo/item/model3d/projectile/acid_glob.geo.json").is_file())
        self.assertEqual(json.loads((self.assets / "model3d/index.json").read_text())["projectiles"], ["acid_glob"])
        java = (self.ws / "src/main/java/com/x/m/client/Projectile3DRenderer.java").read_text()
        self.assertIn("Axis.YP.rotationDegrees(Mth.lerp(partialTick, entity.yRotO, entity.getYRot()) - 90.0F)", java)
        wire = self.tasks("PROJ3DWIRE")
        self.assertEqual([(t["role"], t["state"]) for t in wire], [("coder", "READY")])
        wbrief = self.store.task_instructions(wire[0]["id"])
        self.assertIn('new Projectile3DRenderer<>(ctx, ModMain.MOD_ID, "acid_glob")', wbrief); self.assertIn(self.SPRITE, wbrief)
        self.assertTrue(model3d.projectile_assets(self.store, "m_mod")["acid_glob"]["model3d"])
        self.assertEqual(validate_generated(self.ws)["status"], "PASS")

    def test_refusals(self):
        with self.assertRaisesRegex(InputError, "not a projectile with its own art"):
            model3d.request_proj3d(self.store, "m_mod", "moon_sword")
        tid = model3d.request_proj3d(self.store, "m_mod", "acid_glob")["task"]
        self.deliver_p([{"origin": [-20, 0, 0], "size": [40, 2, 2], "uv": [0, 0]}])
        out = dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("keep it within", out["error"]); self.assertEqual(self.tasks("PROJ3DWIRE"), [])
        with self.assertRaisesRegex(InputError, "one"):
            cli_dispatch(parser().parse_args(["--state-db", str(self.db), "make-3d", "m_mod"]))
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "make-3d", "m_mod", "--projectile", "acid_glob"]))
        self.assertTrue(out["task"].startswith("m_mod:PROJ3D:acid_glob"))


class OpenInBlockbench(Base):
    def test_3d_items_and_projectiles_open_like_mobs(self):
        import os as _os
        import mod_orchestra.feedback as fb
        from mod_orchestra.feedback import open_in_blockbench
        self.store.add_event("m_mod", "controller", "ART_REQUESTED", {"task": "t", "card": "c", "assets": [
            {"id": "acid_glob", "kind": "projectile", "path": "x.png", "for": [], "what": "a glob"}]})
        with self.assertRaisesRegex(InputError, "Make it 3D first"):
            open_in_blockbench(self.store, "m_mod", "moon_sword", "item")
        with self.assertRaisesRegex(InputError, "Make it 3D first"):
            open_in_blockbench(self.store, "m_mod", "acid_glob", "projectile")
        for kind, bad in (("item", "moon_ore"), ("projectile", "moon_sword")):
            with self.assertRaisesRegex(InputError, f"Unknown {kind}"):
                open_in_blockbench(self.store, "m_mod", bad, kind)
        with self.assertRaisesRegex(InputError, "kind must be"):
            open_in_blockbench(self.store, "m_mod", "moon_sword", "statue")
        self.deliver()
        (self.ws / model3d.PDIR).mkdir(parents=True, exist_ok=True); (self.ws / model3d.PDIR / "acid_glob.bbmodel").write_text("{}")
        opened = []
        with patch("subprocess.Popen", lambda cmd, **k: opened.append(list(cmd))), patch.object(fb, "find_blockbench", return_value=None), \
             patch("sys.platform", "linux"), patch.object(_os, "startfile", lambda path: opened.append(["startfile", str(path)]), create=True):
            a = open_in_blockbench(self.store, "m_mod", "moon_sword", "item")
            b = open_in_blockbench(self.store, "m_mod", "acid_glob", "projectile")
        self.assertTrue(a["opened"].replace("\\", "/").endswith("models/items3d/moon_sword.bbmodel"))
        self.assertTrue(b["opened"].replace("\\", "/").endswith("models/projectiles3d/acid_glob.bbmodel"))
        self.assertEqual(len(opened), 2)
        ev = [e["payload"] for e in self.store.events("m_mod") if e["kind"] == "OPENED_IN_BLOCKBENCH"]
        self.assertEqual({(e["kind"], e["name"]) for e in ev}, {("item", "moon_sword"), ("projectile", "acid_glob")})


class Hold(Base):
    """How a 3D item is held: declared by the designer, checked against the geometry, computed by the pose engine, previewed."""
    GUN = {"meta": {"model_format": "geckolib_model"}, "resolution": {"width": 16, "height": 16},
           "elements": [{"name": "barrel", "uuid": "e1", "from": [-1, 1, -8], "to": [1, 3, 8]}, {"name": "sight", "uuid": "e2", "from": [-1, 3, -2], "to": [1, 4, 0]},
                        {"name": "handle", "uuid": "e3", "from": [-1, -3, 1], "to": [1, 1, 3]}],
           "groups": [{"name": "grip", "uuid": "g1", "origin": [0, 0, 2]}], "outliner": []}

    def deliver_gun(self):
        self.deliver(cubes=[{"origin": [-1, 1, -8], "size": [2, 2, 16], "uv": [0, 0]}])
        (self.ws / model3d.DIR / "moon_sword.bbmodel").write_text(json.dumps(self.GUN))

    def done_with_hold(self, hold):
        tid = self.task(); self.deliver_gun()
        h = json.loads(handoff(tid).split("```handoff\n")[1].split("\n```")[0]); h["hold"] = hold
        return dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))

    def test_the_designers_declaration_is_used_and_previewed(self):
        out = self.done_with_hold({"style": "aim", "front": "-z"})
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        entry = json.loads((self.assets / "model3d/index.json").read_text())["items"][0]
        self.assertEqual(entry["hold"], {"style": "aim", "front": "-z", "top": "+y"})
        item = json.loads((self.assets / "models/item/moon_sword.json").read_text())
        from mod_orchestra import pose
        self.assertEqual(item["display"]["firstperson_righthand"], pose.display(self.GUN, style="aim", front="-z")["firstperson_righthand"])
        for tag in ("hand", "firstperson"):
            self.assertTrue((self.ws / model3d.DIR / f"moon_sword_{tag}_preview.png").is_file(), tag)
        row = {r["identifier"]: r for r in list_features(self.store, "m_mod")}["moon_sword"]
        self.assertEqual(row["hold"]["style"], "aim"); self.assertEqual(len(row["hold_previews"]), 2)
        self.assertEqual(out["handoff"]["item3d"]["hold"]["grip_from"], "bone grip")

    def test_a_front_that_contradicts_the_geometry_is_refused(self):
        out = self.done_with_hold({"style": "aim", "front": "+x"})
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("longest along z", out["error"])

    def test_change_the_hold_without_an_agent_and_tune_the_style(self):
        self.assertEqual(self.done_with_hold({"style": "aim", "front": "-z"})["task_state"], "DONE")
        before = json.loads((self.assets / "models/item/moon_sword.json").read_text())["display"]["thirdperson_righthand"]
        out = model3d.set_hold(self.store, "m_mod", "moon_sword", style="wield", front="-z")
        self.assertEqual(out["hold"]["style"], "wield")
        self.assertEqual(json.loads((self.assets / "model3d/index.json").read_text())["items"][0]["hold"]["style"], "wield")
        self.assertNotEqual(json.loads((self.assets / "models/item/moon_sword.json").read_text())["display"]["thirdperson_righthand"], before)
        with self.assertRaisesRegex(InputError, "hold: style"):
            model3d.set_hold(self.store, "m_mod", "moon_sword", style="grab")
        base = json.loads((self.assets / "models/item/moon_sword.json").read_text())["display"]["firstperson_righthand"]
        out = model3d.set_style_tweaks(self.store, "m_mod", "wield", {"firstperson_righthand": {"translation": [0, -3, 0], "scale": 1.2}})
        self.assertEqual(out["recomputed"], ["moon_sword"])
        after = json.loads((self.assets / "models/item/moon_sword.json").read_text())["display"]["firstperson_righthand"]
        self.assertAlmostEqual(after["translation"][1], base["translation"][1] - 3, 1); self.assertAlmostEqual(after["scale"][0], base["scale"][0] * 1.2, 2)
        self.assertEqual(json.loads((self.assets / "model3d/index.json").read_text())["styles"]["wield"]["firstperson_righthand"]["scale"], 1.2)
        with self.assertRaisesRegex(InputError, "unknown context"):
            model3d.set_style_tweaks(self.store, "m_mod", "wield", {"elbow": {"scale": 1}})
        model3d.set_style_tweaks(self.store, "m_mod", "wield", {})
        self.assertEqual(json.loads((self.assets / "models/item/moon_sword.json").read_text())["display"]["firstperson_righthand"], base)

    def test_the_designer_can_look_at_it_in_the_hand(self):
        from mod_orchestra.mcp import invoke
        self.deliver_gun()
        out = invoke(self.store, "orchestra_preview_hold", {"project": "m_mod", "item": "moon_sword", "style": "aim", "front": "-z"})
        self.assertEqual(out["hold"]["grip_from"], "bone grip"); self.assertEqual(len(out["previews"]), 2)
        with self.assertRaisesRegex(InputError, "longest along z"):
            invoke(self.store, "orchestra_preview_hold", {"project": "m_mod", "item": "moon_sword", "style": "wield", "front": "+y"})
        for path in ("src/mod_orchestra/resources/claude/agents/designer.md", ".claude/agents/designer.md"):
            self.assertIn("orchestra_preview_hold", (ROOT / path).read_text())

    def test_cli(self):
        self.assertEqual(self.done_with_hold({"style": "aim", "front": "-z"})["task_state"], "DONE")
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "hold", "m_mod", "--item", "moon_sword", "--style", "carry"]))
        self.assertEqual(out["hold"]["style"], "carry")
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "hold-tweak", "m_mod", "--style", "carry", "--context", "ground", "--scale", "1.5"]))
        self.assertEqual(out["tweaks"], {"ground": {"scale": 1.5}})


class NoGeckoLib(Base):
    IDEA = "items: moon gem; blocks: moon ore; tab: Moon"   # no mobs: the build has no GeckoLib yet

    def test_the_build_gets_geckolib(self):
        self.assertNotIn("geckolib", (self.ws / "build.gradle").read_text())
        tid = self.task(); self.deliver()
        self.assertEqual(dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))["task_state"], "DONE")
        gradle = (self.ws / "build.gradle").read_text()
        self.assertIn("software.bernie.geckolib", gradle); self.assertIn("maven", gradle)
        self.assertIn("geckolib_version=", (self.ws / "gradle.properties").read_text())
        self.assertEqual(validate_generated(self.ws)["status"], "PASS")
        self.assertEqual(model3d.patch_gradle("plugins {}\n", ""), None)


if __name__ == "__main__":
    unittest.main()
