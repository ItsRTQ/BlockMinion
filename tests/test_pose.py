"""How a 3D item is held: derived from the model's own facts and vanilla's known-good poses."""
import math
import unittest

from mod_orchestra import pose


def model(elements, groups=()):
    return {"elements": [{"from": list(f), "to": list(t)} for f, t in elements], "groups": [dict(g) for g in groups]}


def place(disp, ctx, p):
    """Where model point p (px, Blockbench) lands in display space (px) for a context: T + R (S q), q = p - (0,8,0)."""
    d = disp[ctx]; r = pose.euler_to_matrix(*d["rotation"]); s = d["scale"][0]
    q = (p[0], p[1] - 8, p[2])
    v = pose.apply(r, tuple(s * c for c in q))
    return tuple(d["translation"][i] + v[i] for i in range(3))


def vanilla(ctx, base, p):
    rot, tr, sc = base[ctx]; r = pose.euler_to_matrix(*rot)
    v = pose.apply(r, tuple(sc * c for c in p))
    return tuple(tr[i] + v[i] for i in range(3))


def close(a, b, tol=0.05):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


SWORD = model([((-0.5, 0, -0.5), (0.5, 16, 0.5)), ((-2, 4, -0.5), (2, 5, 0.5))], [{"name": "grip", "origin": [0, 0, 0]}])      # blade up, grip at origin
GUN = model([((-1, 1, -8), (1, 3, 8)), ((-1, 3, -2), (1, 4, 0)), ((-1, -3, 1), (1, 1, 3))], [{"name": "grip", "origin": [0, 0, 2]}])  # barrel -Z, sight +Y, grip


class Euler(unittest.TestCase):
    def test_roundtrip(self):
        for angles in ([0, -90, 55], [0, 0, 0], [-90, 0, -60], [10, 20, 30], [0, -90, 25], [-90, 0, -55]):
            back = pose.matrix_to_euler(pose.euler_to_matrix(*angles))
            m1, m2 = pose.euler_to_matrix(*angles), pose.euler_to_matrix(*back)
            self.assertTrue(all(abs(m1[i][j] - m2[i][j]) < 1e-6 for i in range(3) for j in range(3)), (angles, back))

    def test_vanilla_set_is_reproduced_for_a_sprite_shaped_model(self):
        # an upright sword with its grip at the origin is the sprite stood up: the grip must land where the sprite's handle lands
        disp = pose.display(SWORD, style="wield", front="+y")
        for ctx in ("thirdperson_righthand", "firstperson_righthand", "ground", "fixed"):
            self.assertTrue(close(place(disp, ctx, (0, 0, 0)), vanilla(ctx, pose.HANDHELD, pose.HANDLE["wield"])), ctx)
            # and the blade points along the sprite's diagonal, the same length as the icon's blade
            tip, grip = place(disp, ctx, (0, 16, 0)), place(disp, ctx, (0, 0, 0))
            want = vanilla(ctx, pose.HANDHELD, (pose.HANDLE["wield"][0] + 16 / math.sqrt(2), pose.HANDLE["wield"][1] + 16 / math.sqrt(2), 0))
            self.assertTrue(close(tip, want, 0.1), (ctx, tip, want))
        self.assertEqual(disp["gui"]["scale"], [1, 1, 1])


class Styles(unittest.TestCase):
    def test_a_gun_points_along_the_crossbow_diagonal_with_its_sight_up(self):
        disp = pose.display(GUN, style="aim", front="-z")
        # first person: a shooter's hold defined in the camera's frame (looking down -Z): grip low right, barrel forward turned toward the centre, sight up
        fp = "firstperson_righthand"
        grip, muzzle, rear, sight = (place(disp, fp, p) for p in ((0, 0, 2), (0, 2, -8), (0, 2, 8), (0, 4, -1)))
        self.assertTrue(close(grip, pose.AIM_FP_GRIP, 0.05), grip)
        axis = tuple(muzzle[i] - rear[i] for i in range(3)); n = math.sqrt(sum(a * a for a in axis)); axis = tuple(a / n for a in axis)
        self.assertTrue(close(axis, (-math.sin(math.radians(pose.AIM_FP_YAW)), 0, -math.cos(math.radians(pose.AIM_FP_YAW))), 0.02), axis)
        self.assertGreater(sight[1] - grip[1], 0, "the sight is above the grip")
        # left hand mirrors the turn and the side
        lg = place(disp, "firstperson_lefthand", (0, 0, 2)); self.assertTrue(close(lg, (-pose.AIM_FP_GRIP[0], pose.AIM_FP_GRIP[1], pose.AIM_FP_GRIP[2]), 0.05))
        for ctx in ("thirdperson_righthand",):
            grip, muzzle, sight = (place(disp, ctx, p) for p in ((0, 0, 2), (0, 2, -8), (0, 4, -1)))
            # the grip is where the crossbow's handle is held...
            self.assertTrue(close(grip, vanilla(ctx, pose.CROSSBOW_FIRING, pose.HANDLE["aim"]), 0.1), ctx)
            # ...the muzzle goes along the sprite's up-right diagonal (front), the sight toward its upper-left (top)
            rot, _, sc = pose.CROSSBOW_FIRING[ctx]; r = pose.euler_to_matrix(*rot)
            front_dir = pose.apply(r, (1, 1, 0)); top_dir = pose.apply(r, (-1, 1, 0))
            dm = tuple(muzzle[i] - grip[i] for i in range(3)); ds = tuple(sight[i] - grip[i] for i in range(3))
            self.assertGreater(sum(dm[i] * front_dir[i] for i in range(3)), 0, ctx)
            self.assertGreater(sum(ds[i] * top_dir[i] for i in range(3)), 0, ctx)
            rear = place(disp, ctx, (0, 2, 8)); axis = tuple(muzzle[i] - rear[i] for i in range(3))
            self.assertLess(abs(sum(axis[i] * top_dir[i] for i in range(3))), 0.05, "the barrel's own axis is not tilted toward the sight")

    def test_the_same_gun_modelled_along_x_gets_the_same_hold(self):
        # GUN turned so its barrel runs along +X: point (x, y, z) -> (-z, y, x)
        gun_x = model([((-8, 1, -1), (8, 3, 1)), ((0, 3, -1), (2, 4, 1)), ((-3, -3, -1), (-1, 1, 1))], [{"name": "grip", "origin": [-2, 0, 0]}])
        a, b = pose.display(GUN, style="aim", front="-z"), pose.display(gun_x, style="aim", front="+x")
        for ctx in ("thirdperson_righthand", "firstperson_righthand", "ground"):
            for p in ((0, 2, -8), (0, 4, -1), (0, 0, 2)):   # the same hold whatever axis the designer modelled along
                self.assertTrue(close(place(a, ctx, p), place(b, ctx, (-p[2], p[1], p[0])), 0.1), (ctx, p))

    def test_scale_fits_the_length(self):
        long = model([((-1, 0, -16), (1, 2, 16))]); short = model([((-1, 0, -4), (1, 2, 4))])
        self.assertAlmostEqual(pose.display(long, style="aim", front="-z")["thirdperson_righthand"]["scale"][0], 0.9 * 0.5, 2)
        self.assertAlmostEqual(pose.display(short, style="aim", front="-z")["thirdperson_righthand"]["scale"][0], 0.9 * 2.0, 2)

    def test_grip_defaults_and_tweaks(self):
        g, how = pose.grip_point(model([((-1, 0, -8), (1, 2, 8))]), "aim", "-z")
        self.assertEqual(how, "bounding box, a third from the back"); self.assertGreater(g[2], 0)
        g, how = pose.grip_point(model([((-1, 0, -8), (1, 2, 8))]), "wield", "-z")
        self.assertEqual((how, g[2]), ("bounding box, the end opposite the front", 8))
        plain = pose.display(GUN, style="aim", front="-z")
        tweaked = pose.display(GUN, style="aim", front="-z", tweaks={"firstperson_righthand": {"rotation": [0, 10, 0], "translation": [1, -2, 0], "scale": 1.5}})
        fp, tp = plain["firstperson_righthand"], tweaked["firstperson_righthand"]
        self.assertAlmostEqual(tp["rotation"][1], fp["rotation"][1] + 10, 1); self.assertAlmostEqual(tp["translation"][1], fp["translation"][1] - 2, 1)
        self.assertAlmostEqual(tp["scale"][0], fp["scale"][0] * 1.5, 2)
        self.assertEqual(tweaked["thirdperson_righthand"], plain["thirdperson_righthand"])
        with self.assertRaises(ValueError):
            pose.display(GUN, style="aim", front="-z", top="+z")
        with self.assertRaises(ValueError):
            pose.display(GUN, style="hold", front="-z")


if __name__ == "__main__":
    unittest.main()
