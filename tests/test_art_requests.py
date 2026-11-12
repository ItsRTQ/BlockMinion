"""Art for what the coder invents: the coder lists it, the designer paints it, the coder wires it in."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import artreq, workflow
from mod_orchestra.cli import dispatch as cli_dispatch, parser
from mod_orchestra.dispatch import build_envelope, dispatch
from mod_orchestra.fabric import validate_generated
from mod_orchestra.modmap import feature_instructions, request_change, request_feature
from mod_orchestra.provider import FakeProvider
from mod_orchestra.skin import encode_png
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError

IDEA = "items: gem; hostile mobs: spitter; tab: Spit. The spitter spits burning green acid"
ASSET = "src/main/resources/assets/s_mod/textures/item/acid_glob.png"


def png(w, h, colours=((60, 200, 60, 255),)):
    px = bytearray()
    for y in range(h):
        for x in range(w):
            px += bytes(colours[(x + y) % len(colours)])
    return encode_png(w, h, bytes(px))


def handoff(task, *, art=None, status="DONE", card=True):
    h = {"task": task, "status": status, "scope": "feature", "changed_files": [], "checks_run": [{"command": "gradlew build", "exit_code": 0}],
         "evidence": {"level": "BUILD_PASS", "pointer": "build"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "designer"}
    if card:
        h["card"] = {"files": ["src/main/java/com/x/s/entity/AcidGlob.java"], "description": "the spitter spits a glob", "produces": ["acid_glob"]}
    if art is not None:
        h["art_needed"] = art
    return "```handoff\n" + json.dumps(h) + "\n```"


GLOB = {"id": "acid_glob", "kind": "projectile", "path": ASSET, "size": [16, 16], "for": ["spitter"], "what": "the glob of acid the spitter spits, seen flying at the player"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.db = base / "state.sqlite"; self.store = Store(self.db)
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        self.ws = Path(workflow.new_project(self.store, name="S", mod_id="s_mod", package="com.x.s", idea=IDEA)["root"])
        workflow.plan_project(self.store, "s_mod"); workflow.approve_spec(self.store, "s_mod"); workflow.generate_project(self.store, "s_mod")
        self.feature = request_feature(self.store, "s_mod", title="Acid spit", description="The spitter spits acid", acceptance=["a hit player burns"])["task"]

    def placeholder(self, path=ASSET, size=(16, 16)):
        f = self.ws / path; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(png(*size)); return f

    def coder_done(self, art, task=None):
        out = dispatch(self.store, "s_mod", task_id=task or self.feature, provider=FakeProvider(handoff(task or self.feature, art=art)))
        self.assertEqual(out["task_state"], "DONE", out.get("error")); return out

    def task(self, tid):
        return next((t for t in self.store.tasks("s_mod") if t["id"] == tid), None)

    def art_tasks(self, kind):
        return [t for t in self.store.tasks("s_mod") if f":{kind}:" in t["id"]]


class CoderSide(Base):
    def test_the_coder_is_told_to_make_its_own_art_and_list_it(self):
        for brief in (feature_instructions({"title": "t", "description": "d", "acceptance": [], "derived_from": []}),
                      self.store.task_instructions(request_change(self.store, "s_mod", "acid_spit", "spit faster")["task"]).splitlines()):
            text = " ".join(brief)
            self.assertIn("never borrows vanilla visuals", text); self.assertIn("art_needed", text); self.assertIn("placeholder PNG", text)

    def test_listed_art_queues_the_designer_then_the_coder(self):
        self.placeholder()
        out = self.coder_done([GLOB])
        art, wire = out["handoff"]["art"]["art_task"], out["handoff"]["art"]["wire_task"]
        self.assertEqual((art, wire), ("s_mod:ART:acid_spit", "s_mod:ARTWIRE:acid_spit"))
        self.assertEqual((self.task(art)["role"], self.task(art)["state"]), ("designer", "READY"))
        self.assertEqual((self.task(wire)["role"], self.task(wire)["state"]), ("coder", "BACKLOG"))
        brief = build_envelope(self.store, "s_mod", self.task(art)).extra_instructions + self.store.task_instructions(art)
        self.assertIn("models/art/acid_glob.png", brief); self.assertIn("16x16", brief)
        self.assertIn("the glob of acid the spitter spits", brief)
        self.assertIn("it belongs to spitter (mob)", brief); self.assertIn("models/spitter.png", brief)
        self.assertIn("burning green acid", brief, "the user's words come with it")
        self.assertIn(ASSET, self.store.task_instructions(wire))

    def test_nothing_listed_nothing_queued(self):
        self.coder_done(None)
        self.assertEqual(self.art_tasks("ART"), [])

    def test_bad_entries_are_dropped_with_the_reason_and_never_fail_the_feature(self):
        self.placeholder(); self.placeholder("src/main/resources/assets/s_mod/textures/item/big.png", (32, 32))
        self.placeholder("src/main/resources/assets/minecraft/textures/item/slime_ball.png")   # real files: the path itself is what is refused
        self.placeholder("src/main/resources/assets/s_mod/textures/../x.png")
        bad = [GLOB | {"id": "out", "path": "src/main/resources/assets/minecraft/textures/item/slime_ball.png"},
               GLOB | {"id": "up", "path": "src/main/resources/assets/s_mod/textures/../x.png"},
               GLOB | {"id": "size", "path": "src/main/resources/assets/s_mod/textures/item/big.png"},
               GLOB | {"id": "none", "path": "src/main/resources/assets/s_mod/textures/item/missing.png"},
               GLOB | {"id": "kind", "kind": "sound"}, GLOB | {"id": "quiet", "what": " "}, GLOB, GLOB]
        self.coder_done(bad)
        dropped = next(e["payload"]["dropped"] for e in self.store.events("s_mod") if e["kind"] == "ART_REQUEST_DROPPED")
        self.assertEqual(set(dropped), {"out", "up", "size", "none", "kind", "quiet", "acid_glob"})
        self.assertIn("32x32", dropped["size"])
        self.assertIn("must be a .png under", dropped["out"]); self.assertIn("must be a .png under", dropped["up"])
        ev = next(e["payload"] for e in self.store.events("s_mod") if e["kind"] == "ART_REQUESTED")
        self.assertEqual([a["id"] for a in ev["assets"]], ["acid_glob"])


class DesignerSide(Base):
    def setUp(self):
        super().setUp()
        self.before = self.placeholder().read_bytes()
        out = self.coder_done([GLOB])
        self.art, self.wire = out["handoff"]["art"]["art_task"], out["handoff"]["art"]["wire_task"]

    def paint(self, raw):
        f = self.ws / "models/art/acid_glob.png"; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(raw)

    def designer_done(self):
        return dispatch(self.store, "s_mod", task_id=self.art, provider=FakeProvider(handoff(self.art, card=False)))

    def test_painted_art_is_installed_and_the_coder_wires_it(self):
        painted = png(16, 16, ((40, 160, 40, 255), (120, 230, 90, 255), (20, 70, 20, 255), (0, 0, 0, 0)))
        self.paint(painted)
        out = self.designer_done()
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        self.assertEqual((self.ws / ASSET).read_bytes(), painted)
        self.assertEqual(self.task(self.wire)["state"], "READY")
        self.assertEqual(validate_generated(self.ws)["status"], "PASS")
        out = dispatch(self.store, "s_mod", task_id=self.wire, provider=FakeProvider(handoff(self.wire, art=[GLOB | {"id": "again"}])))
        self.assertEqual(out["task_state"], "DONE"); self.assertEqual(len(self.art_tasks("ART")), 1, "wiring never asks for more art")

    def test_what_is_not_real_art_is_refused_and_nothing_replaced(self):
        cases = {"missing": None, "16x16": png(32, 32, ((1, 2, 3, 255), (9, 9, 9, 255))), "single flat colour": png(16, 16, ((200, 30, 30, 255),)),
                 "still the placeholder": self.before}
        for why, raw in cases.items():
            with self.subTest(why=why):
                f = self.ws / "models/art/acid_glob.png"
                f.unlink(missing_ok=True)
                if raw is not None:
                    self.paint(raw)
                out = self.designer_done()
                self.assertEqual(out["task_state"], "FAILED"); self.assertIn(why, out["error"])
                self.assertEqual((self.ws / ASSET).read_bytes(), self.before)
                self.store.requeue(self.art, "retry")
        self.assertEqual(self.task(self.wire)["state"], "BACKLOG")


class Contract(Base):
    """The animation contract: the coder declares the moments its code emits; the designer animates exactly those; no wiring task."""

    def declare(self, events, geo=("acid_gun",), task=None):
        tid = task or self.feature
        h = json.loads(handoff(tid).split("```handoff\n")[1].split("\n```")[0]); h["animation_events"] = events; h["geo_items"] = list(geo)
        out = dispatch(self.store, "s_mod", task_id=tid, provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))
        self.assertEqual(out["task_state"], "DONE", out.get("error")); return out

    def test_the_coder_is_told_the_contract(self):
        brief = " ".join(feature_instructions({"title": "t", "description": "d", "acceptance": [], "derived_from": []}))
        self.assertIn("Item3DBase", brief); self.assertIn("Item3DActions.event(stack, holder", brief); self.assertIn("animation_events", brief); self.assertIn("geo_items", brief)

    def test_events_are_kept_and_bad_ones_dropped(self):
        self.declare([{"item": "acid_gun", "name": "fire", "when": "the trigger is pulled"}, {"item": "acid_gun", "name": "aim", "when": "the player holds right click", "loop": True},
                      {"item": "acid_gun", "name": "Bad Name", "when": "x"}, {"item": "acid_gun", "name": "quiet"}])
        ws = self.ws
        ev = artreq.declared_events(ws, "acid_gun")
        self.assertEqual(ev["fire"]["when"], "the trigger is pulled"); self.assertTrue(ev["aim"]["loop"]); self.assertNotIn("quiet", ev)
        self.assertTrue(artreq.is_geo_item(ws, "acid_gun")); self.assertFalse(artreq.is_geo_item(ws, "gem"))
        rec = next(e["payload"] for e in self.store.events("s_mod") if e["kind"] == "ANIM_EVENTS_DECLARED")
        self.assertEqual(set(rec["dropped"]), {"acid_gun.bad name", "acid_gun.quiet"})
        # a later declaration adds to it
        self.declare([{"item": "acid_gun", "name": "reload", "when": "the magazine is swapped"}], geo=(), task=request_change(self.store, "s_mod", "acid_spit", "add reload")["task"])
        self.assertEqual(sorted(artreq.declared_events(ws, "acid_gun")), ["aim", "fire", "reload"])


class ContractOnAnItem(Base):
    """Seen from the 3D item: the brief lists the moments, and a GeoItem whose clips match them needs no coder."""
    def setUp(self):
        super().setUp()
        self.declare = Contract.declare.__get__(self)
        self.declare([{"item": "gem", "name": "fire", "when": "the trigger is pulled"}, {"item": "gem", "name": "reload", "when": "the magazine is swapped"}], geo=("gem",))

    def test_brief_and_install(self):
        from mod_orchestra import model3d
        from test_item3d import PNG
        tid = model3d.request_item3d(self.store, "s_mod", "gem")["task"]
        brief = self.store.task_instructions(tid)
        self.assertIn("animation.gem.fire (once, when the trigger is pulled)", brief); self.assertIn("no wiring needed", brief)
        d = self.ws / model3d.DIR; d.mkdir(parents=True, exist_ok=True)
        geo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": "geometry.gem", "texture_width": 16, "texture_height": 16},
               "bones": [{"name": "body", "pivot": [0, 0, 0], "cubes": [{"origin": [-1, 0, -8], "size": [2, 2, 16], "uv": [0, 0]}]}]}]}
        key = {"rotation": {"0.0": {"vector": [0, 0, 0]}, "0.2": {"vector": [-10, 0, 0]}}}
        (d / "gem.geo.json").write_text(json.dumps(geo)); (d / "gem.png").write_bytes(PNG); (d / "gem_render.png").write_bytes(PNG)
        (d / "gem.bbmodel").write_text(json.dumps({"elements": [{"from": [-1, 0, -8], "to": [1, 2, 8]}], "groups": [{"name": "grip", "origin": [0, 0, 2]}]}))
        (d / "gem.animation.json").write_text(json.dumps({"animations": {"animation.gem.fire": {"bones": {"body": key}}, "animation.gem.reload": {"bones": {"body": key}}}}))
        h = json.loads(handoff(tid).split("```handoff\n")[1].split("\n```")[0]); h["hold"] = {"style": "aim", "front": "-z"}
        out = dispatch(self.store, "s_mod", task_id=tid, provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        self.assertIsNone(out["handoff"]["item3d"]["anim_task"], "an Item3DBase whose code emits every clip needs no coder")
        self.assertEqual(out["handoff"]["item3d"]["events_without_clip"], [])
        # a clip the code never emits still goes to the coder, with the contract's WHEN for the others
        (d / "gem.animation.json").write_text(json.dumps({"animations": {"animation.gem.fire": {"bones": {"body": key}}, "animation.gem.inspect": {"bones": {"body": key}}}}))
        out = model3d.reinstall_item3d(self.store, "s_mod", "gem")
        self.assertIsNotNone(out["anim_task"]); self.assertEqual(out["clips_without_event"], ["inspect"])
        self.assertIn("fire: the user says it plays the trigger is pulled", self.store.task_instructions(out["anim_task"]))


class ArtPass(Base):
    def test_an_existing_feature_gets_its_own_art(self):
        out = artreq.request_art_pass(self.store, "s_mod", "acid_spit")
        brief = self.store.task_instructions(out["task"])
        self.assertIn('"Acid spit"', brief); self.assertIn("not this mod's own", brief); self.assertIn("art_needed", brief)
        self.assertEqual(self.task(out["task"])["role"], "coder")
        self.placeholder()
        self.coder_done([GLOB], task=out["task"])
        self.assertEqual(len(self.art_tasks("ART")), 1)
        with self.assertRaisesRegex(InputError, "Unknown card"):
            artreq.request_art_pass(self.store, "s_mod", "nope")

    def test_cli(self):
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "request-art", "s_mod", "--card", "acid_spit"]))
        self.assertTrue(out["task"].startswith("s_mod:ARTPASS:acid_spit"))


if __name__ == "__main__":
    unittest.main()
