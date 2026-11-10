"""Animate: what it does (designer), when it plays (coder), the model's shape and texture locked."""
import json
import unittest

from mod_orchestra import animate, model3d
from mod_orchestra.cli import dispatch as cli_dispatch, parser
from mod_orchestra.dispatch import dispatch
from mod_orchestra.provider import FakeProvider
from mod_orchestra.skin import decode_png, encode_png
from mod_orchestra.validation import InputError

from test_item3d import Base as ItemBase, PNG, handoff
from test_model_edit import Base as MobBase, MOB, TASK as MOB_TASK, handoff as mob_handoff

KEY = {"rotation": {"0.0": {"vector": [0, 0, 0]}, "0.3": {"vector": [-15, 0, 0]}}}


class Item(ItemBase):
    def setUp(self):
        super().setUp()
        tid = self.task(); self.deliver(animated=False)
        self.assertEqual(dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))["task_state"], "DONE")
        self.dir = self.ws / model3d.DIR

    def ask(self, anims, remove=None):
        return animate.request_animate(self.store, "m_mod", "item", "moon_sword", anims, remove)

    def anims(self):
        return json.loads((self.dir / "moon_sword.animation.json").read_text())

    def put_anims(self, a):
        (self.dir / "moon_sword.animation.json").write_text(json.dumps(a))

    def geo(self):
        return json.loads((self.dir / "moon_sword.geo.json").read_text())

    def put_geo(self, g):
        (self.dir / "moon_sword.geo.json").write_text(json.dumps(g))

    def done(self, tid):
        return dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))

    def test_the_request(self):
        with self.assertRaisesRegex(InputError, "say when"):
            self.ask([{"name": "reload", "what": "the blade slides back"}])
        with self.assertRaisesRegex(InputError, "say what"):
            self.ask([{"name": "reload", "when": "when it reloads"}])
        with self.assertRaisesRegex(InputError, "two animations"):
            self.ask([{"name": "a", "what": "x", "when": "y"}, {"name": "a", "what": "x", "when": "y"}])
        with self.assertRaisesRegex(InputError, "Make it 3D first"):
            animate.request_animate(self.store, "m_mod", "item", "moon_gem", [{"name": "a", "what": "x", "when": "y"}])
        out = self.ask([{"name": "Reload", "what": "the blade slides back and snaps forward", "when": "when the player reloads it"},
                        {"name": "glow", "what": "the edge pulses", "when": "while it is held", "loop": True}], remove=["idle"])
        brief = self.store.task_instructions(out["task"])
        self.assertIn("animation.moon_sword.reload (plays once); what it does: the blade slides back and snaps forward; it plays: when the player reloads it", brief)
        self.assertIn("animation.moon_sword.glow (loops)", brief); self.assertIn("Remove these clips: animation.moon_sword.idle", brief)
        self.assertIn("shape, UV and texture are locked", brief)
        self.assertEqual(next(t for t in self.store.tasks("m_mod") if t["id"] == out["task"])["role"], "designer")

    def test_a_delivery_that_only_animates_is_installed_and_the_coder_gets_the_users_when(self):
        tid = self.ask([{"name": "reload", "what": "the guard drops", "when": "when the player reloads it"},
                        {"name": "glow", "what": "pulse", "when": "while it is held", "loop": True}])["task"]
        g = self.geo(); bones = g["minecraft:geometry"][0]["bones"]
        moved = bones[0]["cubes"].pop()   # regroup: the cube goes, unchanged, into a new bone so it can move alone
        bones.append({"name": "guard", "parent": bones[0]["name"], "pivot": [0, 2, 0], "cubes": [moved]})
        self.put_geo(g)
        self.put_anims({"animations": {"animation.moon_sword.reload": {"animation_length": 0.5, "bones": {"guard": KEY}},
                                       "animation.moon_sword.glow": {"loop": True, "animation_length": 1, "bones": {"guard": KEY}}}})
        out = self.done(tid)
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        coder = out["handoff"]["animate"]["coder_task"]
        brief = self.store.task_instructions(coder)
        self.assertIn('reload: the user says it plays when the player reloads it: Item3DActions.trigger(this, holder, stack, "reload")', brief)
        self.assertIn('glow (loops): while while it is held', brief.replace("while while", "while while")); self.assertIn('Item3DActions.stop(this, holder, stack, "glow")', brief)
        self.assertIn("ANIMATE_APPLIED", [e["kind"] for e in self.store.events("m_mod")])

    def test_what_the_lock_refuses(self):
        cases = {"shape changed": lambda: self._move_cube(), "texture pixels changed": lambda: self._repaint(),
                 "missing or has no keyframes": lambda: None, "must play once": lambda: self._loop_wrong()}
        for why, act in cases.items():
            with self.subTest(why=why):
                tid = self.ask([{"name": "reload", "what": "x", "when": "when it reloads"}])["task"]
                if why != "missing or has no keyframes":
                    self.put_anims({"animations": {"animation.moon_sword.reload": {"bones": {"blade": KEY}}}})
                before = (self.ws / "src/main/resources/assets/m_mod/geo/item/model3d/moon_sword.geo.json").read_text()
                act()
                out = self.done(tid)
                self.assertEqual(out["task_state"], "FAILED"); self.assertIn(why, out["error"])
                self.assertEqual((self.ws / "src/main/resources/assets/m_mod/geo/item/model3d/moon_sword.geo.json").read_text(), before)
                self.deliver(animated=False)   # back to the installed model for the next case

    def _move_cube(self):
        g = self.geo(); g["minecraft:geometry"][0]["bones"][0]["cubes"][0]["origin"][1] += 1; self.put_geo(g)

    def _repaint(self):
        w, h, px = decode_png(PNG); px = bytearray(px); px[0:4] = bytes((255, 0, 0, 255))
        (self.dir / "moon_sword.png").write_bytes(encode_png(w, h, bytes(px)))

    def _loop_wrong(self):
        self.put_anims({"animations": {"animation.moon_sword.reload": {"loop": True, "bones": {"blade": KEY}}}})

    def test_first_person_arms_may_be_added_and_painted(self):
        tid = self.ask([{"name": "reload", "what": "a hand pulls the guard", "when": "when it reloads"}])["task"]
        g = self.geo(); g["minecraft:geometry"][0]["bones"].append(
            {"name": "fp_right_arm", "pivot": [0, 0, 0], "cubes": [{"origin": [2, 0, -2], "size": [3, 6, 3], "uv": [8, 0]}]})
        self.put_geo(g)
        self.put_anims({"animations": {"animation.moon_sword.reload": {"animation_length": 0.5, "bones": {"fp_right_arm": KEY}}}})

        def paint(x, y):
            w, h, px = decode_png(PNG); px = bytearray(px); i = (y * w + x) * 4
            self.assertLess(i, len(px)); px[i:i + 4] = bytes((220, 170, 140, 255))
            (self.dir / "moon_sword.png").write_bytes(encode_png(w, h, bytes(px)))
        paint(14, 14)   # outside the arm's strip and outside the blade's: locked
        out = self.done(tid)
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("texture pixels changed (1)", out["error"])
        self.store.requeue(tid, "retry")
        paint(10, 5)    # inside the arm's strip (u 8..20, v 3..9): free
        out = self.done(tid)
        self.assertEqual(out["task_state"], "DONE", out.get("error"))

    def test_the_snapshot_is_recorded_relative_to_the_project(self):
        out = self.ask([{"name": "reload", "what": "x", "when": "when it reloads"}])
        snap = animate.latest_request(self.store, "m_mod", out["task"])["snapshot"]
        self.assertTrue(snap.startswith(".mod-orchestra/animate/item/moon_sword/"), snap)   # never an absolute path (the home dir is hidden in events)
        self.assertTrue((self.ws / snap / "before.geo.json").is_file())

    def test_a_removed_clip_must_be_gone(self):
        tid = self.ask([], remove=["idle"])["task"]
        self.put_anims({"animations": {"animation.moon_sword.idle": {"loop": True, "bones": {"blade": KEY}}}})
        out = self.done(tid)
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("should have been removed", out["error"])

    def test_reinstall_wires_actions_of_an_older_install(self):
        self.put_anims({"animations": {"animation.moon_sword.fire": {"animation_length": 0.4, "bones": {"blade": KEY}}}})
        self.assertEqual(self.tasks("ITEM3DANIM"), [])
        out = model3d.reinstall_item3d(self.store, "m_mod", "moon_sword")
        self.assertEqual(out["actions"], ["fire"]); self.assertEqual(len(self.tasks("ITEM3DANIM")), 1)
        with self.assertRaisesRegex(InputError, "not a 3D item"):
            model3d.reinstall_item3d(self.store, "m_mod", "moon_gem")
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "reinstall-3d", "m_mod", "--item", "moon_sword"]))
        self.assertEqual(out["actions"], ["fire"])

    def test_cli(self):
        out = cli_dispatch(parser().parse_args(["--state-db", str(self.db), "animate", "m_mod", "--item", "moon_sword",
                                                "--anim", "reload|the guard drops|when it reloads", "--anim", "glow|pulse|while held|loop"]))
        self.assertEqual(out["anims"], ["reload", "glow"])
        req = animate.latest_request(self.store, "m_mod", out["task"])
        self.assertEqual([a["loop"] for a in req["anims"]], [False, True])


class Projectile(ItemBase):
    def test_one_flight_animation_and_no_second_renderer_switch(self):
        self.store.add_event("m_mod", "controller", "ART_REQUESTED", {"task": "t", "card": "c", "assets": [
            {"id": "acid_glob", "kind": "projectile", "path": "x.png", "size": [16, 16], "for": [], "what": "a glob"}]})
        d = self.ws / model3d.PDIR; d.mkdir(parents=True, exist_ok=True)
        geo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": "geometry.acid_glob", "texture_width": 16, "texture_height": 16},
                                                                    "bones": [{"name": "glob", "pivot": [0, 0, 0], "cubes": [{"origin": [-2, -2, -2], "size": [4, 4, 4], "uv": [0, 0]}]}]}]}
        (d / "acid_glob.geo.json").write_text(json.dumps(geo)); (d / "acid_glob.animation.json").write_text('{"animations": {}}')
        for n in ("acid_glob.png", "acid_glob_render.png"):
            (d / n).write_bytes(PNG)
        (d / "acid_glob.bbmodel").write_text("{}")
        tid = model3d.request_proj3d(self.store, "m_mod", "acid_glob")["task"]
        dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        with self.assertRaisesRegex(InputError, "one animation"):
            animate.request_animate(self.store, "m_mod", "projectile", "acid_glob", [{"name": "a", "what": "x"}, {"name": "b", "what": "y"}])
        tid = animate.request_animate(self.store, "m_mod", "projectile", "acid_glob", [{"name": "spin", "what": "it tumbles"}])["task"]
        self.assertIn("animation.acid_glob.idle (loops)", self.store.task_instructions(tid))
        (d / "acid_glob.animation.json").write_text(json.dumps({"animations": {"animation.acid_glob.idle": {"loop": True, "bones": {"glob": KEY}}}}))
        out = dispatch(self.store, "m_mod", task_id=tid, provider=FakeProvider(handoff(tid)))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        self.assertEqual(len(self.tasks("PROJ3DWIRE")), 1, "the renderer was switched once, by the first model")


class Mob(MobBase):
    def test_new_one_shots_and_movement_states_go_into_the_entity(self):
        self.designed()
        with self.assertRaisesRegex(InputError, "always needs idle"):
            animate.request_animate(self.store, "c_mod", "mob", MOB, [], remove=["walk"])
        out = animate.request_animate(self.store, "c_mod", "mob", MOB, [
            {"name": "roar", "what": "head back, jaw open", "when": "when it first sees a player"},
            {"name": "swim", "what": "legs paddle", "when": "it is in water", "loop": True},
            {"name": "walk", "what": "a limp"}])
        a = self.anim()
        clip = {"animation_length": 1, "bones": {"head": KEY}}
        a["animations"].update({f"animation.{MOB}.roar": clip, f"animation.{MOB}.swim": {**clip, "loop": True}})
        a["animations"][f"animation.{MOB}.walk"]["bones"] = {"head": KEY}
        self.put_anim(a)
        res = dispatch(self.store, "c_mod", task_id=out["task"], provider=FakeProvider(mob_handoff()))
        self.assertEqual(res["task_state"], "DONE", res.get("error"))
        coder = res["handoff"]["animate"]["coder_task"]
        brief = self.store.task_instructions(coder)
        self.assertIn('.triggerableAnim("roar", RawAnimation.begin().thenPlay("animation.sky_critter.roar"))', brief)
        self.assertIn("- roar: when it first sees a player", brief); self.assertIn("- swim: while it is in water", brief)
        self.assertNotIn("- walk", brief)

    def test_only_builtin_ones_need_no_coder(self):
        self.designed()
        out = animate.request_animate(self.store, "c_mod", "mob", MOB, [{"name": "walk", "what": "a limp"}])
        a = self.anim(); a["animations"][f"animation.{MOB}.walk"]["bones"] = {"head": KEY}; self.put_anim(a)
        res = dispatch(self.store, "c_mod", task_id=out["task"], provider=FakeProvider(mob_handoff()))
        self.assertEqual(res["task_state"], "DONE", res.get("error")); self.assertIsNone(res["handoff"]["animate"]["coder_task"])


if __name__ == "__main__":
    unittest.main()


class Player(Item):
    """An item action can move the player's body too (Player Animation Library)."""

    def player_clip(self, key, bones=None):
        f = self.ws / "models/player/player.animation.json"
        a = json.loads(f.read_text()) if f.is_file() else {"format_version": "1.8.0", "animations": {}}
        a["animations"][key] = {"animation_length": 0.5, "bones": bones or {"right_arm": KEY}}
        f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(a))

    def ask_reload(self):
        return self.ask([{"name": "reload", "what": "the guard drops", "when": "when it reloads", "player": "the left arm swaps the guard"}])["task"]

    def test_the_brief_and_the_rig(self):
        tid = self.ask_reload()
        brief = self.store.task_instructions(tid)
        self.assertIn("- moon_sword_reload: the left arm swaps the guard", brief); self.assertIn("models/player/player.bbmodel", brief)
        rig = json.loads((self.ws / "models/player/player.bbmodel").read_text())
        names = {g["name"]: g["origin"] for g in rig.get("groups", [])}
        self.assertEqual(names["right_arm"], [5, 22, 0]); self.assertEqual(names["left_item"], [-6, 12, -2])

    def test_installed_with_pal_and_the_coder_plays_both(self):
        tid = self.ask_reload()
        self.put_anims({"animations": {"animation.moon_sword.reload": {"animation_length": 0.5, "bones": {"blade": KEY}}}})
        self.player_clip("moon_sword_reload")
        out = self.done(tid)
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        res = self.ws / "src/main/resources"
        self.assertIn("moon_sword_reload", json.loads((res / "assets/m_mod/player_animations/player.json").read_text())["animations"])
        self.assertIn('PlayerAnimationLibFabric:${project.pal_version}', (self.ws / "build.gradle").read_text())
        fmj = json.loads((res / "fabric.mod.json").read_text())
        self.assertIn("com.x.m.playeranim.PlayerAnims", fmj["entrypoints"]["main"]); self.assertIn("com.x.m.client.PlayerAnimsClient", fmj["entrypoints"]["client"])
        self.assertIn("player_animation_library", fmj["depends"])
        for f in ("playeranim/PlayerAnims.java", "playeranim/PlayerAnimPayload.java", "client/PlayerAnimsClient.java"):
            self.assertTrue((self.ws / "src/main/java/com/x/m" / f).is_file(), f)
        brief = self.store.task_instructions(out["handoff"]["animate"]["coder_task"])
        self.assertIn('reload: PlayerAnims.play(player, \\"moon_sword_reload\\")'.replace('\\"', '"'), brief)

    def test_refusals_before_anything_is_installed(self):
        for why, setup in (("is missing or has no keyframes", lambda: None),
                           ("moves bones the player does not have", lambda: self.player_clip("moon_sword_reload", {"tail": KEY}))):
            with self.subTest(why=why):
                (self.ws / "models/player/player.animation.json").unlink(missing_ok=True)
                tid = self.ask_reload()
                self.put_anims({"animations": {"animation.moon_sword.reload": {"bones": {"blade": KEY}}}})
                setup()
                if why.startswith("is missing"):
                    self.player_clip("other_clip")
                out = self.done(tid)
                self.assertEqual(out["task_state"], "FAILED"); self.assertIn(why, out["error"])
                self.assertFalse((self.ws / "src/main/resources/assets/m_mod/player_animations/player.json").exists())

    def test_the_committed_rig_is_its_recipe(self):
        from mod_orchestra import playeranim
        self.assertEqual(json.loads((playeranim.RIG / "player.recipe.json").read_text()), playeranim.rig_recipe(),
                         "recipe changed: rebuild with node scripts/build_rig.mjs")
