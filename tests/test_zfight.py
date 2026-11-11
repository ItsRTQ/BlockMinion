"""Z-fighting: coplanar, same-facing, overlapping faces are found and nudged apart in the installed copy only."""
import json
import unittest

from mod_orchestra import zfight


def geo(cubes):
    return {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": "geometry.t", "texture_width": 16, "texture_height": 16},
                                                                "bones": [{"name": "b", "pivot": [0, 0, 0], "cubes": cubes}]}]}


class Find(unittest.TestCase):
    def test_touching_cubes_are_fine_and_overlapping_faces_are_found(self):
        side_by_side = geo([{"origin": [0, 0, 0], "size": [4, 4, 4], "uv": [0, 0]}, {"origin": [4, 0, 0], "size": [4, 4, 4], "uv": [0, 0]}])
        self.assertEqual(zfight.find(side_by_side), [])
        plate = geo([{"origin": [0, 0, 0], "size": [8, 8, 8], "uv": [0, 0]}, {"origin": [2, 2, 6], "size": [4, 4, 2], "uv": [0, 0]}])   # plate flush with the +z face
        pairs = zfight.find(plate)
        self.assertEqual([(p["a"], p["b"], p["axis"], p["side"], p["overlap_px"]) for p in pairs], [("b#1", "b#0", "z", "+", 16.0)])
        rotated = geo([{"origin": [0, 0, 0], "size": [8, 8, 8], "uv": [0, 0]}, {"origin": [2, 2, 6], "size": [4, 4, 2], "uv": [0, 0], "rotation": [0, 15, 0], "pivot": [4, 4, 7]}])
        self.assertEqual(zfight.find(rotated), [], "a rotated cube's faces are not axis-aligned: left alone")

    def test_fix_nudges_the_smaller_cube_outward_and_leaves_the_input_alone(self):
        g = geo([{"origin": [0, 0, 0], "size": [8, 8, 8], "uv": [0, 0]}, {"origin": [2, 2, 6], "size": [4, 4, 2], "uv": [0, 0]},
                 {"origin": [0, 2, 2], "size": [1, 2, 2], "uv": [0, 0]}])   # a stud whose -x face lies on the body's -x face
        before = json.dumps(g)
        fixed, pairs = zfight.fix(g)
        self.assertEqual(json.dumps(g), before)
        self.assertEqual(len(pairs), 2); self.assertNotIn("_cube", pairs[0])
        cubes = fixed["minecraft:geometry"][0]["bones"][0]["cubes"]
        self.assertAlmostEqual(cubes[1]["size"][2], 2.02, 3)                                  # +z face moved out
        self.assertAlmostEqual(cubes[2]["origin"][0], -0.02, 3); self.assertAlmostEqual(cubes[2]["size"][0], 1.02, 3)   # -x face moved out
        self.assertEqual(zfight.find(fixed), [])
        self.assertIn("2 z-fighting pair(s)", zfight.describe(pairs))
