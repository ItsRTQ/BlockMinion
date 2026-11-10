"""3D and animated blocks: the block's cube is replaced by a GeckoLib model through a block entity."""
import json
import unittest

from mod_orchestra import animate, blocks3d, model3d
from mod_orchestra.cli import dispatch as cli_dispatch, parser
from mod_orchestra.content import list_features
from mod_orchestra.dispatch import dispatch
from mod_orchestra.fabric import validate_generated
from mod_orchestra.provider import FakeProvider
from mod_orchestra.validation import InputError

from test_item3d import Base, PNG, handoff

KEY = {"rotation": {"0.0": {"vector": [0, 0, 0]}, "0.5": {"vector": [0, 20, 0]}}}
MAIN = "src/main/java/com/x/m/ModMain.java"


class Blocks(Base):
    def deliver_block(self, *, anims=None, cubes=None):
        d = self.ws / blocks3d.BDIR; d.mkdir(parents=True, exist_ok=True)
        geo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": "geometry.moon_ore", "texture_width": 16, "texture_height": 16},
               "bones": [{"name": "rock", "pivot": [0, 0, 0], "cubes": cubes or [{"origin": [-6, 0, -6], "size": [12, 10, 12], "uv": [0, 0]}]}]}]}
        (d / "moon_ore.geo.json").write_text(json.dumps(geo))
        (d / "moon_ore.animation.json").write_text(json.dumps({"format_version": "1.8.0", "animations": anims or {}}))
        for n in ("moon_ore.png", "moon_ore_render.png"):
            (d / n).write_bytes(PNG)
        (d / "moon_ore.bbmodel").write_text("{}")

    def done(self, tid):
        return dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))

    def test_what_can_be_3d_and_the_brief(self):
        rows = {r["identifier"]: r for r in list_features(self.store, "m_mod")}
        self.assertTrue(rows["moon_ore"]["can3d"]); self.assertFalse(rows["moon_ore"]["model3d"])
        with self.assertRaisesRegex(InputError, "not a block"):
            blocks3d.request_block3d(self.store, "m_mod", "moon_gem")
        tid = blocks3d.request_block3d(self.store, "m_mod", "moon_ore", "a cracked geode")["task"]
        brief = self.store.task_instructions(tid)
        self.assertIn("models/blocks3d/moon_ore.bbmodel", brief); self.assertIn("textures/block/moon_ore.png", brief)
        self.assertIn("y from 0 (the floor it stands on) to 16", brief); self.assertIn("a cracked geode", brief)

    def test_installed_and_wired_with_one_line_of_modmain(self):
        before = (self.ws / MAIN).read_text()
        tid = blocks3d.request_block3d(self.store, "m_mod", "moon_ore")["task"]
        self.deliver_block(anims={"animation.moon_ore.idle": {"loop": True, "bones": {"rock": KEY}}, "animation.moon_ore.crack": {"bones": {"rock": KEY}}})
        out = self.done(tid)
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        after = (self.ws / MAIN).read_text()
        self.assertIn('id("moon_ore"), new com.x.m.model3d.Block3DBlock(', after)
        self.assertEqual(sum(1 for a, b in zip(before.splitlines(), after.splitlines()) if a != b), 1, "only the block's own line changed")
        self.assertEqual(json.loads((self.assets / "model3d/index.json").read_text())["blocks"], [{"id": "moon_ore", "idle": True, "actions": ["crack"]}])
        for f in ("model3d/Block3DBlock.java", "model3d/Block3DEntity.java", "model3d/Block3DInit.java", "client/Block3DRenderer.java", "client/Block3DClient.java"):
            self.assertTrue((self.ws / "src/main/java/com/x/m" / f).is_file(), f)
        fmj = json.loads((self.res / "fabric.mod.json").read_text())
        self.assertIn("com.x.m.model3d.Block3DInit", fmj["entrypoints"]["main"]); self.assertIn("com.x.m.client.Block3DClient", fmj["entrypoints"]["client"])
        self.assertTrue((self.assets / "geo/block/model3d/moon_ore.geo.json").is_file())
        self.assertIsNone(out["handoff"]["block3d"]["wire_task"])
        brief = self.store.task_instructions(out["handoff"]["block3d"]["anim_task"])
        self.assertIn('Block3DEntity.trigger(level, pos, "<action>")', brief); self.assertIn("- crack: at the moment its name describes", brief)
        self.assertEqual(validate_generated(self.ws)["status"], "PASS")
        self.assertTrue({r["identifier"]: r for r in list_features(self.store, "m_mod")}["moon_ore"]["model3d"])

    def test_an_unreported_edit_of_modmain_goes_to_the_coder_first(self):
        main = self.ws / MAIN; edited = main.read_text() + "\n// hand edit\n"; main.write_text(edited)
        tid = blocks3d.request_block3d(self.store, "m_mod", "moon_ore")["task"]
        self.deliver_block(anims={"animation.moon_ore.crack": {"bones": {"rock": KEY}}})
        out = self.done(tid)
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        self.assertEqual(main.read_text(), edited)
        wire, anim = out["handoff"]["block3d"]["wire_task"], out["handoff"]["block3d"]["anim_task"]
        self.assertIn("new com.x.m.model3d.Block3DBlock(<the same properties>)", self.store.task_instructions(wire))
        states = {t["id"]: t["state"] for t in self.store.tasks("m_mod")}
        self.assertEqual((states[wire], states[anim]), ("READY", "BACKLOG"), "the actions wait for the block to be a Block3DBlock")

    def test_bounds(self):
        tid = blocks3d.request_block3d(self.store, "m_mod", "moon_ore")["task"]
        self.deliver_block(cubes=[{"origin": [-4, 0, -4], "size": [8, 30, 8], "uv": [0, 0]}])
        out = self.done(tid)
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("keep it within", out["error"])
        self.assertNotIn("Block3DBlock", (self.ws / MAIN).read_text())

    def test_patch_main(self):
        java = (self.ws / MAIN).read_text()
        once = blocks3d.patch_main(java, "moon_ore", "com.x.m")
        self.assertEqual(blocks3d.patch_main(once, "moon_ore", "com.x.m"), once, "idempotent")
        self.assertIsNone(blocks3d.patch_main(java, "nope", "com.x.m"))
        self.assertIsNone(blocks3d.patch_main(java + java, "moon_ore", "com.x.m"), "ambiguous: two registrations")

    def test_animate_a_3d_block_with_the_users_when(self):
        tid = blocks3d.request_block3d(self.store, "m_mod", "moon_ore")["task"]
        self.deliver_block(); self.assertEqual(self.done(tid)["task_state"], "DONE")
        with self.assertRaisesRegex(InputError, "Make it 3D first"):
            animate.request_animate(self.store, "m_mod", "block", "moon_gem", [{"name": "a", "what": "x", "when": "y"}])
        tid = animate.request_animate(self.store, "m_mod", "block", "moon_ore", [{"name": "open", "what": "the top lifts", "when": "when a player right-clicks it"}])["task"]
        (self.ws / blocks3d.BDIR / "moon_ore.animation.json").write_text(json.dumps({"animations": {"animation.moon_ore.open": {"bones": {"rock": KEY}}}}))
        out = self.done(tid)
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        brief = self.store.task_instructions(out["handoff"]["animate"]["coder_task"])
        self.assertIn("- open: the user says it plays when a player right-clicks it", brief)

    def test_open_in_blockbench_and_cli(self):
        from unittest.mock import patch
        import os as _os
        import mod_orchestra.feedback as fb
        with self.assertRaisesRegex(InputError, "Make it 3D first"):
            fb.open_in_blockbench(self.store, "m_mod", "moon_ore", "block")
        self.deliver_block()
        with patch("subprocess.Popen", lambda cmd, **k: None), patch.object(fb, "find_blockbench", return_value=None), patch("sys.platform", "linux"), \
             patch.object(_os, "startfile", lambda path: None, create=True):
            self.assertTrue(fb.open_in_blockbench(self.store, "m_mod", "moon_ore", "block")["opened"].replace("\\", "/").endswith("models/blocks3d/moon_ore.bbmodel"))
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "make-3d", "m_mod", "--block", "moon_ore"]))
        self.assertTrue(out["task"].startswith("m_mod:BLOCK3D:moon_ore"))


if __name__ == "__main__":
    unittest.main()
