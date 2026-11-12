"""Modify an existing model instead of redesigning it, and install a model made outside the orchestra."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import modeledit, skin, workflow
from mod_orchestra.cli import dispatch as cli_dispatch, parser
from mod_orchestra.dispatch import build_envelope, dispatch
from mod_orchestra.fabric import validate_generated
from mod_orchestra.feedback import give_model_feedback
from mod_orchestra.mcp import invoke
from mod_orchestra.provider import FakeProvider
from mod_orchestra.rigs import stage_rig
from mod_orchestra.state import Store, StateError
from mod_orchestra.validation import InputError

IDEA = "items: gem; mobs: sky critter; tab: Critters"
MOB, TASK = "sky_critter", "c_mod:MODEL:sky_critter"
PALETTE = {"base": "#5a7a3a", "dark": "#2a3a1a"}
ROOT = Path(__file__).resolve().parents[1]


def handoff(status="DONE"):
    h = {"task": TASK, "status": status, "scope": "model", "changed_files": [], "checks_run": [{"command": "bbmodel_geckolib_validate", "exit_code": 0}],
         "evidence": {"level": "STATIC", "pointer": "models/"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "coder"}
    return "```handoff\n" + json.dumps(h) + "\n```"


def make_model(folder: Path, mob: str = MOB, mod: str = "c_mod") -> None:
    """A real model: the quadruped rig, exported by the vendored exporter, painted by paint_skin (2x)."""
    stage_rig(folder.parent, "quadruped", mob, mod, folder.name)
    modeledit.export_bbmodel(folder / f"{mob}.bbmodel", folder, mob, mod)
    model = json.loads((folder / f"{mob}.bbmodel").read_text())
    png, _ = skin.paint_skin(model, palette=PALETTE, scale=2, seed="t")
    (folder / f"{mob}.png").write_bytes(png)
    for extra in ("out.bbmodel",):
        (folder / extra).unlink(missing_ok=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.db = base / "state.sqlite"; self.store = Store(self.db)
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="C", mod_id="c_mod", package="com.x.c", idea=IDEA)
        workflow.plan_project(self.store, "c_mod"); workflow.approve_spec(self.store, "c_mod"); workflow.generate_project(self.store, "c_mod")
        self.ws = Path(proj["root"]); self.models = self.ws / "models"; self.models.mkdir(exist_ok=True)
        self.assets = self.ws / "src/main/resources/assets/c_mod"

    def designed(self):
        """The designer's first model, installed (MODEL task DONE)."""
        make_model(self.models)
        out = dispatch(self.store, "c_mod", task_id=TASK, provider=FakeProvider(handoff()))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))

    # --- what a designer does on a modification, written straight into the exports
    def geo(self):
        return json.loads((self.models / f"{MOB}.geo.json").read_text())

    def put_geo(self, g):
        (self.models / f"{MOB}.geo.json").write_text(json.dumps(g))

    def anim(self):
        return json.loads((self.models / f"{MOB}.animation.json").read_text())

    def put_anim(self, a):
        (self.models / f"{MOB}.animation.json").write_text(json.dumps(a))

    def add_horn(self, uv=(0, 64), grow=True):
        """A new bone on the head with its own cube in the rows orchestra_grow_texture adds, painted, and swaying in idle."""
        if grow:
            modeledit.grow_texture(self.store, "c_mod", MOB)
        g = self.geo(); desc = g["minecraft:geometry"][0]["description"]
        if grow:
            desc["texture_height"] *= 2
        g["minecraft:geometry"][0]["bones"].append({"name": "horn", "parent": "head", "pivot": [0, 12, -6], "cubes": [{"origin": [-1, 12, -8], "size": [2, 4, 2], "uv": list(uv)}]})
        self.put_geo(g)
        a = self.anim(); a["animations"][f"animation.{MOB}.idle"]["bones"]["horn"] = {"rotation": {"0.0": {"vector": [0, 0, 0]}, "1.0": {"vector": [5, 0, 0]}}}
        self.put_anim(a)
        w, h, px = skin.decode_png((self.models / f"{MOB}.png").read_bytes()); px = bytearray(px)
        for y in range(uv[1] * 2, (uv[1] + 6) * 2):
            for x in range(uv[0] * 2, (uv[0] + 8) * 2):
                if y < h:
                    px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((200, 190, 160, 255))
        (self.models / f"{MOB}.png").write_bytes(skin.encode_png(w, h, bytes(px)))


class Request(Base):
    def test_it_needs_a_finished_model_and_words(self):
        with self.assertRaisesRegex(StateError, "no finished model"):
            modeledit.request_model_edit(self.store, "c_mod", MOB, "add a horn")
        self.designed()
        with self.assertRaisesRegex(InputError, "your own words"):
            modeledit.request_model_edit(self.store, "c_mod", MOB, "  ")
        with self.assertRaisesRegex(InputError, "not parts of the current model"):
            modeledit.request_model_edit(self.store, "c_mod", MOB, "longer wings", may_change=["wing"])
        with self.assertRaisesRegex(InputError, "Unknown mob"):
            modeledit.request_model_edit(self.store, "c_mod", "ghost", "x")

    def test_the_designer_gets_the_modification_brief_not_a_new_design(self):
        self.designed()
        out = modeledit.request_model_edit(self.store, "c_mod", MOB, "add a single curved horn on the forehead", may_change=["head"])
        self.assertEqual(next(t for t in self.store.tasks("c_mod") if t["id"] == TASK)["state"], "READY")
        snap = self.ws / modeledit.EDIT_DIR / MOB / out["edit"]
        self.assertEqual({p.name for p in snap.iterdir()}, {"before.geo.json", "before.animation.json", "before.png", "before.bbmodel", "request.json"})
        task = next(t for t in self.store.tasks("c_mod") if t["id"] == TASK)
        brief = build_envelope(self.store, "c_mod", task).extra_instructions
        self.assertIn("MODIFY an existing model", brief); self.assertIn("add a single curved horn on the forehead", brief)
        self.assertIn("Parts the user opened for change: head", brief); self.assertIn("orchestra_check_model_edit", brief)
        self.assertNotIn("Explore before you build", brief); self.assertNotIn("Optional scaffold", brief)
        self.assertEqual(modeledit.pending_edit(self.store, "c_mod", MOB)["may_change"], ["head"])

    def test_a_redesign_or_a_cancel_ends_the_modification(self):
        self.designed()
        modeledit.request_model_edit(self.store, "c_mod", MOB, "add a horn")
        modeledit.cancel_model_edit(self.store, "c_mod", MOB)
        self.assertIsNone(modeledit.pending_edit(self.store, "c_mod", MOB))
        modeledit.request_model_edit(self.store, "c_mod", MOB, "add a horn")
        give_model_feedback(self.store, "c_mod", MOB, "a completely different creature")
        self.assertIsNone(modeledit.pending_edit(self.store, "c_mod", MOB))
        task = next(t for t in self.store.tasks("c_mod") if t["id"] == TASK)
        self.assertIn("Explore before you build", build_envelope(self.store, "c_mod", task).extra_instructions)
        with self.assertRaisesRegex(InputError, "No modification pending"):
            modeledit.cancel_model_edit(self.store, "c_mod", MOB)


class Install(Base):
    def test_an_addition_is_installed_and_everything_else_is_untouched(self):
        self.designed()
        modeledit.request_model_edit(self.store, "c_mod", MOB, "add a horn")
        self.add_horn()
        self.assertEqual(invoke(self.store, "orchestra_check_model_edit", {"project": "c_mod", "mob": MOB})["violations"], [])
        out = dispatch(self.store, "c_mod", task_id=TASK, provider=FakeProvider(handoff()))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        applied = next(e["payload"] for e in self.store.events("c_mod") if e["kind"] == "MODEL_EDIT_APPLIED")
        self.assertEqual((applied["added_bones"], applied["changed_bones"]), (["horn"], []))
        installed = json.loads((self.assets / f"geo/entity/{MOB}.geo.json").read_text())
        self.assertIn("horn", [b["name"] for b in installed["minecraft:geometry"][0]["bones"]])
        self.assertIsNone(modeledit.pending_edit(self.store, "c_mod", MOB))
        self.assertEqual(validate_generated(self.ws)["status"], "PASS")

    def test_touching_a_part_that_was_not_opened_is_refused_and_nothing_is_installed(self):
        self.designed()
        before = sha(self.assets / f"geo/entity/{MOB}.geo.json")
        modeledit.request_model_edit(self.store, "c_mod", MOB, "add a horn")
        self.add_horn()
        g = self.geo(); body = next(b for b in g["minecraft:geometry"][0]["bones"] if b["name"] == "body"); body["pivot"][1] += 1; self.put_geo(g)
        out = dispatch(self.store, "c_mod", task_id=TASK, provider=FakeProvider(handoff()))
        self.assertEqual(out["task_state"], "FAILED")
        self.assertIn("touched what was not asked", out["error"]); self.assertIn("bone body changed", out["error"])
        self.assertEqual(sha(self.assets / f"geo/entity/{MOB}.geo.json"), before, "the game files keep the previous model")
        self.assertIsNotNone(modeledit.pending_edit(self.store, "c_mod", MOB), "the modification is still open for a retry")

    def test_an_opened_part_may_change(self):
        self.designed()
        modeledit.request_model_edit(self.store, "c_mod", MOB, "a bigger head with a horn", may_change=["head"])
        self.add_horn()
        g = self.geo(); head = next(b for b in g["minecraft:geometry"][0]["bones"] if b["name"] == "head"); head["cubes"][0]["inflate"] = 0.5; self.put_geo(g)
        out = dispatch(self.store, "c_mod", task_id=TASK, provider=FakeProvider(handoff()))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        applied = next(e["payload"] for e in self.store.events("c_mod") if e["kind"] == "MODEL_EDIT_APPLIED")
        self.assertEqual(applied["changed_bones"], ["head"])

    def test_a_version_keeps_the_whole_model(self):
        self.designed()
        runs = list((self.ws / ".mod-orchestra/previews").iterdir())
        self.assertEqual({p.name for p in runs[0].iterdir()} >= {f"{MOB}.bbmodel", f"{MOB}.geo.json", f"{MOB}.animation.json", f"{MOB}.png"}, True)


class Check(Base):
    """check_edit on its own, one rule at a time."""
    def setUp(self):
        super().setUp()
        self.designed()
        self.edit = modeledit.request_model_edit(self.store, "c_mod", MOB, "add a horn")
        self.add_horn()

    def violations(self, may=None):
        return modeledit.check_edit(self.ws / modeledit.EDIT_DIR / MOB / self.edit["edit"], self.models, MOB, may)["violations"]

    def test_the_clean_addition_passes(self):
        self.assertEqual(self.violations(), [])

    def test_a_removed_bone(self):
        g = self.geo(); g["minecraft:geometry"][0]["bones"] = [b for b in g["minecraft:geometry"][0]["bones"] if b["name"] != "tail"]; self.put_geo(g)
        self.assertIn("bone tail was removed", self.violations())
        self.assertNotIn("bone tail was removed", self.violations(["tail"]))

    def test_keyframes_and_clips(self):
        a = self.anim(); clip = a["animations"][f"animation.{MOB}.walk"]
        bone = next(iter(clip["bones"])); clip["bones"][bone] = {"rotation": {"0.0": {"vector": [9, 9, 9]}}}
        self.put_anim(a)
        self.assertTrue(any(f"the keyframes of {bone} changed" in v for v in self.violations()))
        a = self.anim(); a["animations"][f"animation.{MOB}.idle"]["animation_length"] = 7; self.put_anim(a)
        self.assertTrue(any("animation_length changed" in v for v in self.violations()))
        a = self.anim(); del a["animations"][f"animation.{MOB}.idle"]; self.put_anim(a)
        self.assertIn(f"clip animation.{MOB}.idle was removed", self.violations())

    def test_pixels_of_existing_parts(self):
        w, h, px = skin.decode_png((self.models / f"{MOB}.png").read_bytes())
        g = self.geo(); body = next(b for b in g["minecraft:geometry"][0]["bones"] if b["name"] == "body")
        (u, v), d = body["cubes"][0]["uv"], int(body["cubes"][0]["size"][2]); i = ((v + d + 1) * 2 * w + (u + d + 1) * 2) * 4   # inside its north face
        px = bytearray(px); px[i:i + 4] = bytes((255, 0, 255, 255))
        (self.models / f"{MOB}.png").write_bytes(skin.encode_png(w, h, bytes(px)))
        self.assertIn("1 texture pixels of body changed but it was not opened for change", self.violations())
        self.assertEqual(self.violations(["body"]), [])

    def test_new_uv_over_old_texture_and_resolution(self):
        g = self.geo(); bones = {b["name"]: b for b in g["minecraft:geometry"][0]["bones"]}; (u, v), d = bones["body"]["cubes"][0]["uv"], int(bones["body"]["cubes"][0]["size"][2])
        bones["horn"]["cubes"][0]["uv"] = [u + d, v + d]; self.put_geo(g)   # on the body's north face
        self.assertTrue(any("overlaps the texture of body" in v for v in self.violations()))
        w, h, px = skin.decode_png((self.models / f"{MOB}.png").read_bytes())
        half = bytearray(); [half.extend(px[(y * 2 * w + x * 2) * 4:(y * 2 * w + x * 2) * 4 + 4]) for y in range(h // 2) for x in range(w // 2)]
        (self.models / f"{MOB}.png").write_bytes(skin.encode_png(w // 2, h // 2, bytes(half)))
        self.assertTrue(any("pixels per UV unit changed" in v for v in self.violations()))


class Tools(Base):
    def test_grow_texture_keeps_every_pixel_and_needs_a_modification(self):
        self.designed()
        with self.assertRaisesRegex(StateError, "for modifications"):
            invoke(self.store, "orchestra_grow_texture", {"project": "c_mod", "mob": MOB})
        modeledit.request_model_edit(self.store, "c_mod", MOB, "add a horn")
        w, h, before = skin.decode_png((self.models / f"{MOB}.png").read_bytes())
        out = invoke(self.store, "orchestra_grow_texture", {"project": "c_mod", "mob": MOB})
        w2, h2, after = skin.decode_png((self.models / f"{MOB}.png").read_bytes())
        self.assertEqual((w2, h2, out["resolution"]), (w, 2 * h, [64, 128]))
        self.assertEqual(after[:len(before)], before); self.assertEqual(set(after[len(before):]), {0})
        model = json.loads((self.models / f"{MOB}.bbmodel").read_text())
        self.assertEqual(model["resolution"], {"width": 64, "height": 128})

    def test_paint_only_new_bones_keeps_the_rest(self):
        self.designed()
        model = json.loads((self.models / f"{MOB}.bbmodel").read_text())
        old = (self.models / f"{MOB}.png").read_bytes()
        png, report = skin.paint_skin(model, palette={"base": "#ff0000"}, scale=2, only_bones=["tail"], base_png=old)
        self.assertEqual(report["only_bones"], ["tail"]); self.assertIsNone(report["face"])
        _, _, a = skin.decode_png(old); w, _, b = skin.decode_png(png)
        tail = [c for c in skin.box_cubes(model) if c["bone"] == "tail"]
        inside = {(x, y) for c in tail for (x0, y0, x1, y1) in skin.face_rects(c).values() for y in range(y0 * 2, y1 * 2) for x in range(x0 * 2, x1 * 2)}
        changed = {((i // 4) % w, (i // 4) // w) for i in range(0, len(a), 4) if a[i:i + 4] != b[i:i + 4]}
        self.assertTrue(changed); self.assertLessEqual(changed, inside)
        with self.assertRaisesRegex(InputError, "needs the current PNG"):
            skin.paint_skin(model, palette={"base": "#ff0000"}, only_bones=["tail"])
        with self.assertRaisesRegex(InputError, "scale must match"):
            skin.paint_skin(model, palette={"base": "#ff0000"}, scale=1, only_bones=["tail"], base_png=old)
        with self.assertRaisesRegex(InputError, "no box-UV cube belongs"):
            skin.paint_skin(model, palette={"base": "#ff0000"}, scale=2, only_bones=["wing"], base_png=old)

    def test_the_designer_may_call_the_new_tools(self):
        for path in (ROOT / "src/mod_orchestra/resources/claude/agents/designer.md", ROOT / ".claude/agents/designer.md"):
            text = path.read_text()
            self.assertIn("mcp__minecraft-orchestra__orchestra_check_model_edit", text); self.assertIn("mcp__minecraft-orchestra__orchestra_grow_texture", text)


class Import(Base):
    def outside_model(self, *, embed=True, short_clips=True, v4=False) -> Path:
        """A model made elsewhere: other identifiers, clips named `idle`, optionally Blockbench 4.x bones, texture embedded."""
        folder = Path(self.tmp.name) / "outside" / "m"; folder.mkdir(parents=True, exist_ok=True)
        make_model(folder, mob="thing", mod="other_mod")
        m = json.loads((folder / "thing.bbmodel").read_text())
        if short_clips:
            for a in m["animations"]:
                a["name"] = a["name"].split(".")[-1]
        if v4:
            groups = {g["uuid"]: g for g in m.pop("groups")}
            def inline(nodes):
                return [n if isinstance(n, str) else {**groups[n["uuid"]], "children": inline(n.get("children"))} for n in nodes]
            m["outliner"] = inline(m["outliner"])
        src = folder / "mine.bbmodel"; src.write_text(json.dumps(m))
        if embed:
            modeledit._embed_texture(src, folder / "thing.png", src)
        return src

    def test_a_model_from_outside_is_exported_validated_and_installed(self):
        for v4 in (False, True):
            with self.subTest(v4=v4):
                src = self.outside_model(v4=v4)
                out = modeledit.import_model(self.store, "c_mod", MOB, {"bbmodel": src.read_bytes()})
                geo = json.loads((self.assets / f"geo/entity/{MOB}.geo.json").read_text())
                self.assertEqual(geo["minecraft:geometry"][0]["description"]["identifier"], f"geometry.{MOB}")
                self.assertIn(f"animation.{MOB}.idle", out["animations"])
                for ext in ("bbmodel", "geo.json", "animation.json", "png"):
                    self.assertTrue((self.models / f"{MOB}.{ext}").is_file())
                self.assertEqual(json.loads((self.models / f"{MOB}.bbmodel").read_text())["model_identifier"], MOB)
                self.assertEqual(validate_generated(self.ws)["status"], "PASS")
                self.assertIn("MODEL_IMPORTED", [e["kind"] for e in self.store.events("c_mod")])
        # and then it can be modified like any model
        modeledit.request_model_edit(self.store, "c_mod", MOB, "add a horn")

    def test_refusals_happen_before_anything_is_installed(self):
        before = sha(self.assets / f"geo/entity/{MOB}.geo.json")
        src = self.outside_model(embed=False)
        with self.assertRaisesRegex(InputError, "no embedded texture"):
            modeledit.import_model(self.store, "c_mod", MOB, {"bbmodel": src.read_bytes()})
        m = json.loads(src.read_text()); m["meta"]["box_uv"] = False
        with self.assertRaisesRegex(InputError, "per-face UV"):
            modeledit.import_model(self.store, "c_mod", MOB, {"bbmodel": json.dumps(m).encode()})
        with self.assertRaisesRegex(InputError, "not a .bbmodel"):
            modeledit.import_model(self.store, "c_mod", MOB, {"bbmodel": b"hello"})
        m = json.loads(src.read_text()); m["animations"] = [a for a in m["animations"] if a["name"] != "walk"]
        with self.assertRaisesRegex(InputError, "lacks animation.sky_critter.walk"):
            modeledit.import_model(self.store, "c_mod", MOB, {"bbmodel": json.dumps(m).encode(), "png": (src.parent / "thing.png").read_bytes()})
        m = json.loads(src.read_text()); m["animations"][0]["animators"][next(iter(m["animations"][0]["animators"]))]["keyframes"][0]["data_points"][0]["x"] = "math.sin(q.anim_time)"
        with self.assertRaisesRegex(InputError, "expression"):
            modeledit.import_model(self.store, "c_mod", MOB, {"bbmodel": json.dumps(m).encode(), "png": (src.parent / "thing.png").read_bytes()})
        self.assertEqual(sha(self.assets / f"geo/entity/{MOB}.geo.json"), before)
        self.assertFalse((self.models / f"{MOB}.geo.json").exists())

    def test_reinstall_my_blockbench_edits(self):
        self.designed()
        m = json.loads((self.models / f"{MOB}.bbmodel").read_text())
        head = next(g for g in m["groups"] if g["name"] == "head"); head["origin"] = [head["origin"][0], head["origin"][1] + 1, head["origin"][2]]
        (self.models / f"{MOB}.bbmodel").write_text(json.dumps(m))   # saved from Blockbench; its texture lives next to it
        out = modeledit.reinstall_from_blockbench(self.store, "c_mod", MOB)
        self.assertIn("head", out["bones"])
        geo = json.loads((self.assets / f"geo/entity/{MOB}.geo.json").read_text())
        self.assertEqual(next(b for b in geo["minecraft:geometry"][0]["bones"] if b["name"] == "head")["pivot"][1], head["origin"][1])

    def test_cli(self):
        src = self.outside_model()
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "import-model", "c_mod", "--mob", MOB, "--bbmodel", str(src)]))
        self.assertIn("installed", out)
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "modify-model", "c_mod", "--mob", MOB, "--request", "add a horn", "--may-change", "head"]))
        self.assertEqual(out["may_change"], ["head"])
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "modify-model", "c_mod", "--mob", MOB, "--cancel"]))
        self.assertEqual(out["mob"], MOB)


if __name__ == "__main__":
    unittest.main()
