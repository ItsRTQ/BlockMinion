import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import rigs, skin
from mod_orchestra.validation import InputError

BIPED = rigs.load_rig("biped", "bbmodel")
PALETTE = {"base": "#5c7f3a", "cloth": "#6b3a22", "metal": "#3b3f42", "rust": "#8c2d19"}
ZONES = [{"bones": ["body"], "color": "cloth", "bands": {"color": "rust", "every": 4, "thickness": 1}}, {"bones": ["*_leg*"], "color": "metal"}]


def raw_png(width, height, color_type, rows_by_filter, palette=None):
    """A PNG built by hand with a different row filter per row, to exercise the decoder."""
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    stride = width * channels
    out, prev = bytearray(), bytes(stride)
    for y, (f, row) in enumerate(rows_by_filter):
        filt = bytearray()
        for i in range(stride):
            a = row[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            pred = {0: 0, 1: a, 2: b, 3: (a + b) // 2, 4: (a if abs(b - c) <= abs(a - c) and abs(b - c) <= abs(a + b - 2 * c) else b if abs(a - c) <= abs(a + b - 2 * c) else c)}[f]
            filt.append((row[i] - pred) & 255)
        out += bytes([f]) + filt
        prev = row
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
    if palette:
        png += chunk(b"PLTE", palette)
    return png + chunk(b"IDAT", zlib.compress(bytes(out))) + chunk(b"IEND", b"")


class TestPng(unittest.TestCase):
    def test_roundtrip(self):
        rgba = bytes((x * 7 + y * 3 + k * 50) & 255 for y in range(5) for x in range(6) for k in range(4))
        w, h, back = skin.decode_png(skin.encode_png(6, 5, rgba))
        self.assertEqual((w, h, back), (6, 5, rgba))

    def test_every_filter_and_colour_type(self):
        rows = [bytes((x * 31 + y * 17) & 255 for x in range(4 * 4)) for y in range(5)]       # 4 wide RGBA
        png = raw_png(4, 5, 6, [(y, rows[y]) for y in range(5)])                                 # filters 0,1,2,3,4 on consecutive rows
        w, h, back = skin.decode_png(png)
        self.assertEqual(back, b"".join(rows))
        rgb = [bytes((x * 13 + y) & 255 for x in range(3 * 2)) for y in range(2)]
        _, _, back = skin.decode_png(raw_png(2, 2, 2, [(4, rgb[0]), (2, rgb[1])]))
        self.assertEqual(back, b"".join(r[i:i + 3] + b"\xff" for r in rgb for i in (0, 3)))
        _, _, back = skin.decode_png(raw_png(2, 1, 3, [(0, bytes([1, 0]))], palette=bytes([10, 20, 30, 40, 50, 60])))
        self.assertEqual(back, bytes([40, 50, 60, 255, 10, 20, 30, 255]))
        _, _, back = skin.decode_png(raw_png(2, 1, 0, [(1, bytes([5, 9]))]))
        self.assertEqual(back, bytes([5, 5, 5, 255, 9, 9, 9, 255]))

    def test_rejects_what_it_cannot_read(self):
        with self.assertRaises(ValueError):
            skin.decode_png(b"nope")
        with self.assertRaises(ValueError):
            skin.decode_png(raw_png(1, 1, 6, [(0, bytes(4))]).replace(b"\x08\x06", b"\x10\x06", 1))   # 16-bit


class TestGeometry(unittest.TestCase):
    def test_face_rects_follow_the_box_uv_layout(self):
        r = skin.face_rects({"u": 10, "v": 20, "w": 8, "h": 6, "d": 4})
        self.assertEqual(r["north"], (14, 24, 22, 30)); self.assertEqual(r["south"], (26, 24, 34, 30))
        self.assertEqual(r["east"], (10, 24, 14, 30)); self.assertEqual(r["west"], (22, 24, 26, 30))
        self.assertEqual(r["up"], (14, 20, 22, 24)); self.assertEqual(r["down"], (22, 20, 30, 24))

    def test_cubes_know_their_bone_and_the_head_is_found(self):
        cubes = skin.box_cubes(BIPED)
        self.assertEqual({c["bone"] for c in cubes}, {"body", "head", "left_arm", "left_arm_forearm", "left_leg", "left_leg_shin", "right_arm", "right_arm_forearm", "right_leg", "right_leg_shin"})
        head = skin.head_cube(cubes)
        self.assertEqual((head["bone"], head["w"], head["h"], head["d"]), ("head", 8, 8, 8))


class TestPainter(unittest.TestCase):
    def paint(self, **kw):
        kw.setdefault("palette", PALETTE); kw.setdefault("zones", ZONES); kw.setdefault("seed", "x")
        return skin.paint_skin(BIPED, **kw)

    def pixels(self, png):
        w, h, rgba = skin.decode_png(png)
        return w, h, lambda x, y: tuple(rgba[(y * w + x) * 4:(y * w + x) * 4 + 3])

    def test_size_follows_scale_and_the_paint_is_deterministic(self):
        for scale in (1, 2, 4):
            png, report = self.paint(scale=scale)
            self.assertEqual(skin.decode_png(png)[:2], (64 * scale, 64 * scale)); self.assertEqual(report["scale"], scale)
        self.assertEqual(self.paint()[0], self.paint()[0])
        self.assertNotEqual(self.paint(seed="other")[0], self.paint()[0])

    def test_zones_and_bands_colour_the_right_bones(self):
        png, report = self.paint()
        w, h, px = self.pixels(png)
        cubes = skin.box_cubes(BIPED)
        torso = next(c for c in cubes if c["bone"] == "body"); leg = next(c for c in cubes if c["bone"] == "left_leg")
        tx0, ty0, tx1, ty1 = (n * 2 for n in skin.face_rects(torso)["north"])
        lx0, ly0, lx1, ly1 = (n * 2 for n in skin.face_rects(leg)["north"])
        cloth, metal = skin.parse_color("#6b3a22"), skin.parse_color("#3b3f42")
        near = lambda a, b, tol=55: all(abs(a[i] - b[i]) <= tol for i in range(3))
        self.assertTrue(near(px((tx0 + tx1) // 2, ty0 + 5), cloth), px((tx0 + tx1) // 2, ty0 + 5))
        self.assertTrue(near(px((lx0 + lx1) // 2, ly0 + 5), metal))
        band_rows = {y for y in range(ty0, ty1) if skin.luminance(px((tx0 + tx1) // 2, y)) != skin.luminance(px(tx0 + 3, y)) and near(px(tx0 + 3, y), skin.parse_color("#8c2d19"), 70)}
        self.assertGreaterEqual(len(band_rows), 2)                                                  # rust bands every 4 units cross the torso
        self.assertEqual(report["zones"], 2)

    def face_pixels(self, **face):
        png, report = self.paint(face=face)
        w, h, px = self.pixels(png)
        x0, y0, x1, y1 = (n * 2 for n in skin.face_rects(skin.head_cube(skin.box_cubes(BIPED)))["north"])
        return report, px, (x0, y0, x1, y1)

    def test_the_face_is_upright_and_reads(self):
        report, px, (x0, y0, x1, y1) = self.face_pixels()
        self.assertTrue(report["face_check"]["ok"], report["face_check"]); self.assertGreaterEqual(report["face_check"]["features"], 3)
        fh = y1 - y0
        bright = lambda lo, hi: sum(skin.luminance(px(x, y)) > 0.8 for y in range(y0 + int(fh * lo), y0 + int(fh * hi)) for x in range(x0, x1))
        dark = lambda lo, hi: sum(skin.luminance(px(x, y)) < 0.1 for y in range(y0 + int(fh * lo), y0 + int(fh * hi)) for x in range(x0, x1))
        self.assertGreaterEqual(bright(0.2, 0.55), 10)                                               # the eyes are in the upper half...
        self.assertLessEqual(bright(0.6, 1.0), 6)                                                    # ...and only a few teeth below
        self.assertGreaterEqual(dark(0.75, 1.0), 8)                                                  # the mouth is in the lower quarter
        self.assertLess(dark(0.0, 0.2), 4)                                                           # nothing dark at the very top: it would be flipped

    def test_tusks_rise_from_the_ends_of_the_mouth_in_the_lower_half(self):
        report, px, (x0, y0, x1, y1) = self.face_pixels(tusks=True)
        fh = y1 - y0
        bright = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if skin.luminance(px(x, y)) > 0.8 and y > y0 + fh * 0.6]
        self.assertTrue(bright)
        self.assertTrue(any(x < x0 + 5 for x, _ in bright) and any(x > x1 - 6 for x, _ in bright))   # one on each side
        self.assertTrue(report["face_check"]["ok"])

    def test_feature_colours_are_pushed_away_from_what_surrounds_them(self):
        png, report = self.paint(face={"eyes": "#5c8040", "mouth": "#5a7a3c"})                      # both almost the skin colour
        self.assertIn("eyes", report["adjusted"]); self.assertIn("mouth", report["adjusted"])
        self.assertTrue(report["face_check"]["ok"], report["face_check"])
        socket = skin.scale_color(skin.parse_color(report["face"]["mouth"]), 0.9)                    # the eyes sit in a dark socket made of the mouth colour
        self.assertGreaterEqual(skin.luminance(skin.parse_color(report["face"]["eyes"])) - skin.luminance(socket), 0.44)

    def test_face_can_be_skipped_and_calm_works(self):
        self.assertIsNone(self.paint(face=False)[1]["face"])
        self.assertEqual(self.paint(face={"style": "calm", "nose": False})[1]["face"]["style"], "calm")
        with self.assertRaises(InputError):
            self.paint(face={"style": "sleepy"})

    def test_bad_input_is_rejected(self):
        for kw in ({"palette": {"cloth": "#000000"}}, {"palette": {"base": "green"}}, {"scale": 9}, {"scale": 0}, {"zones": [{"bones": "body", "color": "base"}]}):
            with self.assertRaises(InputError, msg=str(kw)):
                self.paint(**kw)
        with self.assertRaises(InputError):
            skin.paint_skin({"resolution": {"width": 64, "height": 64}, "elements": [], "groups": [], "outliner": []}, palette=PALETTE)

    def test_ensure_contrast_goes_where_the_feature_belongs(self):
        mid = (92, 127, 58)                                                                              # a mid-tone skin: both directions have room
        mouth, _ = skin.ensure_contrast((90, 122, 60), mid, 0.35, "dark"); eyes, _ = skin.ensure_contrast((90, 122, 60), mid, 0.35, "light")
        self.assertLess(skin.luminance(mouth), skin.luminance(mid) - 0.34); self.assertGreater(skin.luminance(eyes), skin.luminance(mid) + 0.34)
        very_dark = (20, 16, 18)                                                                         # no room to go darker: a "dark" request falls back to light
        self.assertGreater(skin.luminance(skin.ensure_contrast((22, 18, 20), very_dark, 0.35, "dark")[0]), 0.35)
        self.assertEqual(skin.ensure_contrast((10, 10, 10), (240, 240, 240), 0.35, "light")[0][0] < 100, True)  # and the same for a very light background

    def test_ensure_contrast(self):
        col, changed = skin.ensure_contrast((90, 128, 60), (92, 127, 58), 0.4)
        self.assertTrue(changed); self.assertGreaterEqual(abs(skin.luminance(col) - skin.luminance((92, 127, 58))), 0.4)
        self.assertEqual(skin.ensure_contrast((255, 255, 255), (10, 10, 10), 0.4), ((255, 255, 255), False))


class TestFaceReport(unittest.TestCase):
    def flat(self, color, scale=2):
        return skin.encode_png(64 * scale, 64 * scale, bytes(color + (255,)) * (64 * scale) ** 2)

    def test_a_flat_face_is_flat(self):
        r = skin.face_report(BIPED, self.flat((92, 127, 58)))
        self.assertTrue(r["flat"]); self.assertFalse(r["ok"]); self.assertEqual(r["features"], 0); self.assertIn("orchestra_paint_skin", r["advice"])

    def test_hand_painted_features_are_measured_like_painted_ones(self):
        w = 128; rgba = bytearray(bytes((92, 127, 58, 255)) * w * w)
        x0, y0, x1, y1 = (n * 2 for n in skin.face_rects(skin.head_cube(skin.box_cubes(BIPED)))["north"])
        def box(x, y, bw, bh, c):
            for yy in range(y, y + bh):
                for xx in range(x, x + bw):
                    rgba[(yy * w + xx) * 4:(yy * w + xx) * 4 + 3] = bytes(c)
        box(x0 + 3, y0 + 6, 3, 2, (250, 230, 120)); box(x1 - 6, y0 + 6, 3, 2, (250, 230, 120)); box(x0 + 4, y0 + 12, 8, 2, (15, 8, 8))
        r = skin.face_report(BIPED, skin.encode_png(w, w, bytes(rgba)))
        self.assertTrue(r["ok"], r); self.assertEqual(r["features"], 3)

    def test_nothing_to_judge(self):
        self.assertIsNone(skin.face_report(BIPED, self.flat((1, 2, 3), scale=3)[:20]))             # truncated PNG
        self.assertIsNone(skin.face_report(BIPED, skin.encode_png(100, 100, bytes(100 * 100 * 4))))   # not a multiple of 64
        quad = rigs.load_rig("fish", "bbmodel"); self.assertIsNotNone(skin.face_report(quad, skin.encode_png(128, 128, bytes(128 * 128 * 4))))


class TestOrchestraTools(unittest.TestCase):
    def setUp(self):
        from mod_orchestra import workflow
        from mod_orchestra.state import Store
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "s.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop); (base / "projects").mkdir()
        self.project = workflow.new_project(self.store, name="G", mod_id="g_mod", package="com.x.g", idea="hostile mobs: brute")
        self.root = Path(self.project["root"])
        self.mob = "brute"
        rigs.stage_rig(self.root, "biped", self.mob, "g_mod")

    def call(self, name, **a):
        from mod_orchestra.mcp import invoke
        return invoke(self.store, name, {"project": "g_mod", "mob": self.mob} | a)

    def test_paint_writes_only_the_mobs_png_and_reports(self):
        before = {p for p in self.root.rglob("*") if p.is_file()}
        out = self.call("orchestra_paint_skin", palette=PALETTE, zones=ZONES, face={"tusks": True})
        png = self.root / "models/brute.png"
        self.assertTrue(png.is_file()); self.assertEqual(skin.decode_png(png.read_bytes())[:2], (128, 128))
        self.assertEqual({p for p in self.root.rglob("*") if p.is_file()} - before, {png})
        self.assertTrue(out["face_check"]["ok"]); self.assertEqual(out["file"], "models/brute.png"); self.assertIn("bbmodel_geckolib_set_texture", out["next"])
        self.assertEqual(self.call("orchestra_check_skin")["ok"], True)

    def test_check_before_paint_and_bad_ids(self):
        from mod_orchestra.state import StateError
        with self.assertRaises(StateError):
            self.call("orchestra_check_skin")
        with self.assertRaises(InputError):
            self.call("orchestra_paint_skin", palette=PALETTE, mob="../etc/passwd")
        with self.assertRaises(StateError):
            self.call("orchestra_paint_skin", palette=PALETTE, mob="ghost")
        with self.assertRaises(InputError):
            self.call("orchestra_paint_skin", palette=PALETTE, zones=[{"bones": ["*"], "color": "base"}] * 40)

    def test_only_the_designer_may_use_the_tools(self):
        from mod_orchestra.mcp import TOOLS
        names = {t["name"] for t in TOOLS}
        self.assertTrue({"orchestra_paint_skin", "orchestra_check_skin"} <= names)
        agents = Path(__file__).resolve().parents[1] / "src/mod_orchestra/resources/claude/agents"
        for md in agents.glob("*.md"):
            has = "orchestra_paint_skin" in md.read_text(encoding="utf8").split("---")[1]
            self.assertEqual(has, md.stem == "designer", md.name)


class TestInstallReportsTheFace(unittest.TestCase):
    def test_validate_model_files_carries_the_face_report(self):
        from mod_orchestra.models import validate_model_files
        with tempfile.TemporaryDirectory() as tmp:
            models = Path(tmp) / "models"; models.mkdir()
            model = rigs.rig_bbmodel_for("biped", "my_mob", "g_mod")
            (models / "my_mob.bbmodel").write_text(json.dumps(model))
            (models / "my_mob.geo.json").write_text(json.dumps(rigs.rig_geo_for("biped", "my_mob")))
            (models / "my_mob.animation.json").write_text(json.dumps(rigs.rig_animation_for("biped", "my_mob")))
            png, _ = skin.paint_skin(model, palette=PALETTE, zones=ZONES)
            (models / "my_mob.png").write_bytes(png)
            info = validate_model_files(Path(tmp), "my_mob", needs_held_item=True)
            self.assertEqual(info["texture"], [128, 128]); self.assertTrue(info["face"]["ok"])
            (models / "my_mob.png").write_bytes(skin.encode_png(128, 128, bytes((92, 127, 58, 255)) * 128 * 128))
            info = validate_model_files(Path(tmp), "my_mob", needs_held_item=True)
            self.assertTrue(info["face"]["flat"])                                                   # reported, never blocking


if __name__ == "__main__":
    unittest.main()


class TestOrganicSurfaces(unittest.TestCase):
    """Skin that looks like skin: mottling, veins, growths, scars, grime and a tone ramp, derived from each zone's own colour."""
    FLESH = {"base": "#9d8878", "rags": "#4b4944"}

    def paint(self, **kw):
        kw.setdefault("palette", self.FLESH); kw.setdefault("seed", "x")
        return skin.paint_skin(BIPED, **kw)

    def hue(self, rgb):
        import colorsys
        return colorsys.rgb_to_hsv(*(c / 255 for c in rgb))

    def zone_pixels(self, png, bone, report=None):
        w, h, rgba = skin.decode_png(png)
        out = []
        for c in [c for c in skin.box_cubes(BIPED) if c["bone"] == bone]:
            for (x0, y0, x1, y1) in (tuple(n * 2 for n in r) for r in skin.face_rects(c).values()):
                out += [tuple(rgba[(y * w + x) * 4:(y * w + x) * 4 + 3]) for y in range(y0, y1) for x in range(x0, x1)]
        return out

    def test_without_a_surface_nothing_changes_and_with_one_only_its_zone_does(self):
        plain, _ = self.paint(face=False)
        again, _ = self.paint(face=False)
        self.assertEqual(plain, again)
        organic, report = self.paint(face=False, zones=[{"bones": ["body"], "color": "base", "surface": "rotten"}])
        self.assertNotEqual(plain, organic)
        self.assertEqual(self.zone_pixels(plain, "left_leg"), self.zone_pixels(organic, "left_leg"))        # other zones are untouched
        self.assertNotEqual(self.zone_pixels(plain, "body"), self.zone_pixels(organic, "body"))

    def test_a_surface_brings_no_hue_of_its_own(self):
        """Veins, undertones and growths come from the zone's colour: pale flesh stays flesh, green stays green."""
        for base in ("#9d8878", "#5c7f3a", "#8a6f9c"):
            png, _ = self.paint(palette={"base": base}, face=False, zones=[{"bones": ["body"], "color": "base", "surface": {"preset": "rotten", "blotches": 0.4}}])
            hues = [self.hue(p) for p in self.zone_pixels(png, "body") if self.hue(p)[1] > 0.12]
            want = self.hue(skin.parse_color(base))[0]
            drift = sorted(min(abs(h[0] - want), 1 - abs(h[0] - want)) * 360 for h in hues)
            self.assertLess(drift[len(drift) // 2], 40, f"{base}: the median hue moved {drift[len(drift) // 2]:.0f} degrees")

    def test_the_surface_is_uneven_not_flat(self):
        png, _ = self.paint(face=False, zones=[{"bones": ["body"], "color": "base", "surface": "flesh"}])
        flat, _ = self.paint(face=False)
        self.assertGreater(len(set(self.zone_pixels(png, "body"))), len(set(self.zone_pixels(flat, "body"))) * 2)

    def test_the_ramp_shades_toward_violet_instead_of_plain_black(self):
        ramp, _ = self.paint(face=False, zones=[{"bones": ["body"], "color": "base", "surface": {"ramp": True}}])
        plain, _ = self.paint(face=False)
        lean = lambda px: sum(p[2] / max(1, p[0]) for p in px) / len(px)                                   # blue against red
        dark = lambda png: [p for p in self.zone_pixels(png, "body") if skin.luminance(p) < 0.38]
        self.assertGreater(lean(dark(ramp)), lean(dark(plain)))

    def test_deterministic_per_seed(self):
        zones = [{"bones": ["body"], "color": "base", "surface": "rotten"}]
        a, _ = self.paint(zones=zones); b, _ = self.paint(zones=zones); c, _ = self.paint(zones=zones, seed="other")
        self.assertEqual(a, b); self.assertNotEqual(a, c)

    def test_the_global_surface_and_the_per_zone_one(self):
        png, _ = self.paint(face=False, surface="flesh", zones=[{"bones": ["*_leg*"], "color": "rags", "surface": "cloth"}])
        plain, _ = self.paint(face=False)
        self.assertNotEqual(self.zone_pixels(png, "head"), self.zone_pixels(plain, "head"))                  # head: no zone, the global default applies
        self.assertNotEqual(self.zone_pixels(png, "left_leg"), self.zone_pixels(plain, "left_leg"))

    def test_bad_surfaces_are_refused_with_the_options(self):
        for bad, why in (("granite", "preset must be one of"), ({"mottle": 3}, "0 to 1"), ({"scars": 20}, "0 to 8"), ({"scars": 1.5}, "whole number"),
                         ({"sparkle": 1}, "unknown option"), (42, "preset name"), ({"vein_color": "nope"}, "hex colour")):
            with self.assertRaisesRegex(InputError, why, msg=str(bad)):
                self.paint(face=False, surface=bad)

    def test_a_grim_face_keeps_its_eyes_visible_on_pale_skin(self):
        """Regression: eyes were compared with the skin, which pushed them toward black on pale flesh and swallowed them in their own sockets."""
        png, report = self.paint(zones=[{"bones": ["body", "head"], "color": "base", "surface": "flesh"}], face={"style": "grim", "eyes": "#d6c46a", "mouth": "#1c1012"})
        asked, got = skin.parse_color("#d6c46a"), skin.parse_color(report["face"]["eyes"])
        self.assertGreaterEqual(skin.luminance(got), skin.luminance(asked) - 0.001)                                # lightened where there is room, never darkened
        self.assertGreaterEqual(skin.luminance(got) - skin.luminance(skin.parse_color("#9d8878")), 0.29)           # and clear of the skin as well as of the socket
        self.assertTrue(report["face_check"]["ok"], report["face_check"]); self.assertGreaterEqual(report["face_check"]["features"], 5)
        self.assertEqual(report["face"]["style"], "grim")

    def test_the_default_eyes_are_bright_on_any_skin(self):
        for base in ("#f0d9c8", "#9d8878", "#2a2024"):
            _, report = self.paint(palette={"base": base}, zones=[{"bones": ["head"], "color": "base"}], face={"style": "angry"})
            eyes = skin.parse_color(report["face"]["eyes"]); socket = skin.scale_color(skin.parse_color(report["face"]["mouth"]), 0.9)
            self.assertGreaterEqual(skin.luminance(eyes) - skin.luminance(socket), 0.4, base)

    def test_the_tool_passes_surfaces_and_the_grim_face_through(self):
        from mod_orchestra.mcp import TOOLS
        props = next(t for t in TOOLS if t["name"] == "orchestra_paint_skin")["inputSchema"]["properties"]
        self.assertIn("surface", props); self.assertIn("grim", props["face"]["description"])
