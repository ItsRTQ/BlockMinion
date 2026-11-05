"""Rig library: six original base rigs (body plans) as data, built into .bbmodel files by the vendored
blockbench-mcp-safe server (scripts/regen_rigs.py drives scripts/build_rig.mjs), so the shipped sources are
byte-compatible with what the designer's MCP tools produce.

A *recipe* is plain data: bones (name, parent, origin = pivot), cubes (bone, from, to, optional inflate/mirror)
and clips (idle + walk). UV offsets are not hand-placed: `pack_box_uv` lays every cube's box-UV strip on a shelf
inside the texture (strip = (2d+2w) x (d+h), see knowledge/blockbench/formats-java-1.21.1.md §2).

Coordinates are Blockbench space: 1 unit = 1/16 block, Y up, the creature faces -Z, its left side is +X.
Committed outputs live in resources/blockbench/rigs/<plan>.{bbmodel,geo.json,animation.json}.
"""
from __future__ import annotations

import json
from pathlib import Path

RIG_DIR = Path(__file__).resolve().parent / "resources" / "blockbench" / "rigs"
BODY_PLANS = ("quadruped", "biped", "bird", "fish", "serpent", "insect")
DEFAULT_BODY_PLAN = "quadruped"


# ---------------------------------------------------------------------------------------------------------------
# Box-UV shelf packer

def strip_size(frm: list, to: list) -> tuple[int, int]:
    """Pixels a box-UV cube occupies on the texture: width 2d+2w, height d+h (sizes floored, minimum 1)."""
    w, h, d = (max(1, int(to[i] - frm[i])) for i in range(3))
    return 2 * d + 2 * w, d + h


def pack_box_uv(cubes: list[dict], width: int, height: int) -> list[dict]:
    """Assign `uv_offset` to each cube (in list order, larger strips first) on shelves inside width x height.
    Raises ValueError when the texture is too small; returns new dicts, input untouched."""
    order = sorted(range(len(cubes)), key=lambda i: (-strip_size(cubes[i]["from"], cubes[i]["to"])[1], i))
    out = [dict(c) for c in cubes]
    x = y = shelf_h = 0
    for i in order:
        sw, sh = strip_size(cubes[i]["from"], cubes[i]["to"])
        if sw > width or sh > height:
            raise ValueError(f"cube {cubes[i]['name']} strip {sw}x{sh} exceeds texture {width}x{height}")
        if x + sw > width:                      # next shelf
            x, y, shelf_h = 0, y + shelf_h, 0
        if y + sh > height:
            raise ValueError(f"texture {width}x{height} too small for all cubes (at {cubes[i]['name']})")
        out[i]["uv_offset"] = [x, y]
        x += sw
        shelf_h = max(shelf_h, sh)
    return out


# ---------------------------------------------------------------------------------------------------------------
# Clip helpers (times are multiples of 0.05 so they land on 20/s snapping)

def swing(bone: str, length: float, amplitude: float, phase: int = 1, axis: int = 0, interpolation: str = "catmullrom") -> dict:
    """Rotation channel going +amp -> -amp -> +amp (phase=-1 inverts) over `length` seconds; loop-seamed."""
    v = [0.0, 0.0, 0.0]
    hi, lo = list(v), list(v)
    hi[axis], lo[axis] = amplitude * phase, -amplitude * phase
    return {"bone": bone, "channel": "rotation", "keyframes": [
        {"time": 0.0, "value": hi, "interpolation": interpolation},
        {"time": round(length / 2, 2), "value": lo, "interpolation": interpolation},
        {"time": length, "value": hi, "interpolation": interpolation}]}


def bob(bone: str, length: float, amplitude: float, channel: str = "position", axis: int = 1) -> dict:
    """Soft 0 -> amp -> 0 on one axis (position bob or small rotation nod); loop-seamed."""
    v, peak = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    peak[axis] = amplitude
    return {"bone": bone, "channel": channel, "keyframes": [
        {"time": 0.0, "value": v, "interpolation": "easeInOutSine"},
        {"time": round(length / 2, 2), "value": peak, "interpolation": "easeInOutSine"},
        {"time": length, "value": v, "interpolation": "easeInOutSine"}]}


def knee(bone: str, length: float, amplitude: float, phase: int = 1, axis: int = 0) -> dict:
    """A joint that bends one way only (knee, elbow, hock): -amp * max(0, sin) over the cycle, 5 samples, loop-seamed.
    phase=1 bends during the first half, phase=-1 during the second (the opposite leg)."""
    def v(x):
        out = [0.0, 0.0, 0.0]; out[axis] = -amplitude * x; return out
    pat = [0, 1, 0, 0, 0] if phase == 1 else [0, 0, 0, 1, 0]
    return {"bone": bone, "channel": "rotation", "keyframes": [
        {"time": round(length * i / 4, 2), "value": v(pat[i]), "interpolation": "catmullrom"} for i in range(5)]}


def jointed_limb(prefix: str, parent: str, joints: list[tuple[str, list, list, list]]) -> tuple[list[dict], list[dict]]:
    """Chain bones proximal -> distal. joints = [(suffix, pivot, from, to), ...]; the first bone is `prefix`, the
    others `prefix_<suffix>` (e.g. left_leg, left_leg_shin). Returns (bones, cubes)."""
    bones, cubes, last = [], [], parent
    for i, (suffix, pivot, frm, to) in enumerate(joints):
        name = prefix if i == 0 else f"{prefix}_{suffix}"
        bones.append({"name": name, "parent": last, "origin": list(pivot)})
        cubes.append({"name": f"{name}_cube", "bone": name, "from": list(frm), "to": list(to)})
        last = name
    return bones, cubes


def curve(bone: str, channel: str, points: list[tuple[float, list]], delay: float = 0.0, interpolation: str = "catmullrom") -> dict:
    """A one-shot channel from (time, value) points: windup -> impact -> recovery -> rest. `delay` shifts every inner
    point later (follow-through on a child bone) while the first and last points stay at 0 and the clip end."""
    keys = []
    for i, (t, v) in enumerate(points):
        tt = t if i in (0, len(points) - 1) else round(t + delay, 2)
        keys.append({"time": round(tt, 2), "value": list(v), "interpolation": interpolation})
    return {"bone": bone, "channel": channel, "keyframes": keys}


def _clips(ident: str, idle: list[dict], walk: list[dict], attack: list[dict] | None = None, attack_length: float = 1.0) -> list[dict]:
    clips = [{"name": f"animation.{ident}.idle", "length": 2.0, "loop": "loop", "channels": idle},
             {"name": f"animation.{ident}.walk", "length": 1.0, "loop": "loop", "channels": walk}]
    if attack:
        clips.append({"name": f"animation.{ident}.attack", "length": attack_length, "loop": "once", "channels": attack})
    return clips


# ---------------------------------------------------------------------------------------------------------------
# Anatomy table. Each recipe builder returns the data the node driver feeds to the server.

def _recipe(plan: str, *, texture: tuple[int, int], visible_box: list, bones: list[dict], cubes: list[dict],
            idle: list[dict], walk: list[dict], notes: str, attack: list[dict] | None = None, attack_length: float = 1.0) -> dict:
    return {
        "plan": plan, "name": plan, "identifier": plan, "modid": "rigs", "model_type": "Entity",
        "texture_width": texture[0], "texture_height": texture[1], "visible_box": visible_box,
        "bones": bones, "cubes": pack_box_uv(cubes, *texture),
        "animations": _clips(plan, idle, walk, attack, attack_length), "notes": notes,
    }


def quadruped() -> dict:
    """Cow/wolf/deer family: empty root, body with a neck-hinged head and tail, four two-joint legs. 64x64."""
    bones = [
        {"name": "root", "origin": [0, 0, 0]},
        {"name": "body", "parent": "root", "origin": [0, 8, 0]},
        {"name": "head", "parent": "body", "origin": [0, 11, -6]},
        {"name": "tail", "parent": "body", "origin": [0, 11, 6]},
    ]
    cubes = [
        {"name": "body_cube", "bone": "body", "from": [-4, 6, -6], "to": [4, 12, 6]},
        {"name": "head_cube", "bone": "head", "from": [-3, 8, -11], "to": [3, 14, -6]},
        {"name": "snout", "bone": "head", "from": [-2, 8, -13], "to": [2, 11, -11]},
        {"name": "tail_cube", "bone": "tail", "from": [-1, 10, 6], "to": [1, 12, 10]},
    ]
    for side, x in (("left", 3), ("right", -3)):
        for pos, z in (("front", -4), ("back", 4)):
            b, c = jointed_limb(f"{side}_{pos}_leg", "body", [
                ("", [x, 6, z], [x - 1, 3, z - 1], [x + 1, 6, z + 1]),           # upper leg, hip pivot
                ("lower", [x, 3, z], [x - 1, 0, z - 1], [x + 1, 3, z + 1]),      # lower leg, knee/hock pivot
            ])
            bones += b; cubes += c
    idle = [bob("head", 2.0, 3.0, channel="rotation", axis=0), bob("tail", 2.0, 8.0, channel="rotation", axis=1)]
    walk = [swing("left_front_leg", 1.0, 25, 1), swing("right_back_leg", 1.0, 25, 1),
            swing("right_front_leg", 1.0, 25, -1), swing("left_back_leg", 1.0, 25, -1),
            knee("left_front_leg_lower", 1.0, 30, 1), knee("right_back_leg_lower", 1.0, 30, 1),
            knee("right_front_leg_lower", 1.0, 30, -1), knee("left_back_leg_lower", 1.0, 30, -1),
            bob("body", 1.0, 0.5)]
    attack = [curve("body", "position", [(0, [0, 0, 0]), (0.3, [0, 1, 1]), (0.5, [0, -0.5, -3]), (0.7, [0, 0, -1]), (1.0, [0, 0, 0])]),
              curve("head", "rotation", [(0, [0, 0, 0]), (0.3, [-20, 0, 0]), (0.5, [25, 0, 0]), (0.7, [5, 0, 0]), (1.0, [0, 0, 0])]),
              curve("left_front_leg", "rotation", [(0, [0, 0, 0]), (0.3, [-45, 0, 0]), (0.5, [20, 0, 0]), (1.0, [0, 0, 0])]),
              curve("right_front_leg", "rotation", [(0, [0, 0, 0]), (0.3, [-45, 0, 0]), (0.5, [20, 0, 0]), (1.0, [0, 0, 0])]),
              curve("left_front_leg_lower", "rotation", [(0, [0, 0, 0]), (0.3, [-30, 0, 0]), (0.5, [0, 0, 0]), (1.0, [0, 0, 0])], delay=0.05),
              curve("right_front_leg_lower", "rotation", [(0, [0, 0, 0]), (0.3, [-30, 0, 0]), (0.5, [0, 0, 0]), (1.0, [0, 0, 0])], delay=0.05)]
    return _recipe("quadruped", texture=(64, 64), visible_box=[2, 2, 1], bones=bones, cubes=cubes, idle=idle, walk=walk, attack=attack, attack_length=1.0,
                   notes="Diagonal gait: left_front with right_back, right_front with left_back; the *_lower joints bend one way "
                         "(knee/hock). `root` is empty: animate it for whole-body moves (slam, collapse) and keep `body` for the "
                         "torso. Head pivot is the neck, tail pivot the rump. Longer lower legs for deer, longer body for dachshund. Attack: Lunge: rear up (windup 0.3), bite forward with the front legs down (impact 0.5), settle.")


def biped() -> dict:
    """Villager/zombie family on the vanilla 32-high skeleton: empty root, hip body, head, two-joint arms and legs. 64x64."""
    bones = [
        {"name": "root", "origin": [0, 0, 0]},
        {"name": "body", "parent": "root", "origin": [0, 12, 0]},
        {"name": "head", "parent": "body", "origin": [0, 24, 0]},
    ]
    cubes = [
        {"name": "torso", "bone": "body", "from": [-4, 12, -2], "to": [4, 24, 2]},
        {"name": "head_cube", "bone": "head", "from": [-4, 24, -4], "to": [4, 32, 4]},
    ]
    for side, sx in (("left", 1), ("right", -1)):
        ax = 4 if sx > 0 else -8                                           # arm cube x range: 4..8 or -8..-4
        b, c = jointed_limb(f"{side}_arm", "body", [
            ("", [5 * sx, 22, 0], [ax, 18, -2], [ax + 4, 24, 2]),         # upper arm, shoulder pivot
            ("forearm", [5 * sx, 18, 0], [ax, 12, -2], [ax + 4, 18, 2]),  # forearm, elbow pivot
        ])
        bones += b; cubes += c
        lx = 0 if sx > 0 else -4                                           # leg cube x range: 0..4 or -4..0
        b, c = jointed_limb(f"{side}_leg", "body", [
            ("", [2 * sx, 12, 0], [lx, 6, -2], [lx + 4, 12, 2]),          # thigh, hip pivot
            ("shin", [2 * sx, 6, 0], [lx, 0, -2], [lx + 4, 6, 2]),        # shin, knee pivot
        ])
        bones += b; cubes += c
    idle = [bob("head", 2.0, 2.0, channel="rotation", axis=0), bob("left_arm", 2.0, 2.5, channel="rotation", axis=2),
            bob("right_arm", 2.0, -2.5, channel="rotation", axis=2), bob("body", 2.0, 0.3)]
    walk = [swing("left_leg", 1.0, 30, 1), swing("right_leg", 1.0, 30, -1),
            knee("left_leg_shin", 1.0, 28, 1), knee("right_leg_shin", 1.0, 28, -1),
            swing("left_arm", 1.0, 30, -1), swing("right_arm", 1.0, 30, 1),
            bob("left_arm_forearm", 1.0, -10, channel="rotation", axis=0), bob("right_arm_forearm", 1.0, -10, channel="rotation", axis=0),
            bob("body", 1.0, 0.4)]
    attack = [curve("right_arm", "rotation", [(0, [0, 0, 0]), (0.3, [-110, 0, -15]), (0.5, [20, 0, 0]), (0.65, [-10, 0, 0]), (1.0, [0, 0, 0])]),
              curve("right_arm_forearm", "rotation", [(0, [0, 0, 0]), (0.3, [-35, 0, 0]), (0.5, [10, 0, 0]), (0.65, [-5, 0, 0]), (1.0, [0, 0, 0])], delay=0.05),
              curve("body", "rotation", [(0, [0, 0, 0]), (0.3, [0, -12, 0]), (0.5, [5, 12, 0]), (1.0, [0, 0, 0])]),
              curve("head", "rotation", [(0, [0, 0, 0]), (0.3, [-5, 10, 0]), (0.5, [8, -8, 0]), (1.0, [0, 0, 0])], delay=0.05),
              curve("left_arm", "rotation", [(0, [0, 0, 0]), (0.3, [25, 0, 10]), (0.5, [-15, 0, 10]), (1.0, [0, 0, 0])])]
    return _recipe("biped", texture=(64, 64), visible_box=[1.5, 2.5, 1.25], bones=bones, cubes=cubes, idle=idle, walk=walk, attack=attack, attack_length=1.0,
                   notes="Vanilla humanoid pivots (head 24, shoulders ±5/22, hips ±2/12): armor and held items line up. Elbows "
                         "at y 18, knees at y 6. Arms swing opposite to the leg on the same side; forearms follow through. "
                         "Shrink to 3/4 for a child, widen torso for a brute, add a third joint (hand) for a boss. Attack: Overhead right-arm swing: windup 0.3 (arm back, torso twists), impact 0.5 (arm down, torso follows), recovery 0.65, rest 1.0.")


def bird() -> dict:
    """Chicken/parrot family: compact body, head on a neck pivot, beak, two flapping wings, tail, thin legs. 64x64."""
    bones = [
        {"name": "root", "origin": [0, 0, 0]},
        {"name": "body", "parent": "root", "origin": [0, 6, 0]},
        {"name": "head", "parent": "body", "origin": [0, 10, -3]},
        {"name": "left_wing", "parent": "body", "origin": [3, 9, 0]},
        {"name": "right_wing", "parent": "body", "origin": [-3, 9, 0]},
        {"name": "tail", "parent": "body", "origin": [0, 6, 4]},
        {"name": "left_leg", "parent": "body", "origin": [1.5, 4, 0]},
        {"name": "right_leg", "parent": "body", "origin": [-1.5, 4, 0]},
    ]
    cubes = [
        {"name": "body_cube", "bone": "body", "from": [-3, 4, -4], "to": [3, 10, 4]},
        {"name": "head_cube", "bone": "head", "from": [-2, 10, -6], "to": [2, 14, -2]},
        {"name": "beak", "bone": "head", "from": [-1, 11, -8], "to": [1, 12, -6]},
        {"name": "left_wing_cube", "bone": "left_wing", "from": [3, 5, -3], "to": [4, 9, 3]},
        {"name": "right_wing_cube", "bone": "right_wing", "from": [-4, 5, -3], "to": [-3, 9, 3]},
        {"name": "tail_cube", "bone": "tail", "from": [-2, 5, 4], "to": [2, 6, 7]},
        {"name": "left_leg_cube", "bone": "left_leg", "from": [1, 0, -1], "to": [2, 4, 0]},
        {"name": "right_leg_cube", "bone": "right_leg", "from": [-2, 0, -1], "to": [-1, 4, 0]},
    ]
    idle = [bob("head", 2.0, 4.0, channel="rotation", axis=0), bob("left_wing", 2.0, -6.0, channel="rotation", axis=2),
            bob("right_wing", 2.0, 6.0, channel="rotation", axis=2), bob("tail", 2.0, 5.0, channel="rotation", axis=0)]
    walk = [swing("left_leg", 1.0, 25, 1), swing("right_leg", 1.0, 25, -1), bob("body", 1.0, 0.8),
            swing("head", 1.0, 6, 1), swing("left_wing", 1.0, 8, -1, axis=2), swing("right_wing", 1.0, 8, 1, axis=2)]
    attack = [curve("head", "rotation", [(0, [0, 0, 0]), (0.2, [-25, 0, 0]), (0.4, [40, 0, 0]), (0.55, [10, 0, 0]), (0.8, [0, 0, 0])]),
              curve("body", "position", [(0, [0, 0, 0]), (0.2, [0, 0.5, 1]), (0.4, [0, 0, -1.5]), (0.8, [0, 0, 0])]),
              curve("left_wing", "rotation", [(0, [0, 0, 0]), (0.2, [0, 0, -20]), (0.4, [0, 0, 10]), (0.8, [0, 0, 0])], delay=0.05),
              curve("right_wing", "rotation", [(0, [0, 0, 0]), (0.2, [0, 0, 20]), (0.4, [0, 0, -10]), (0.8, [0, 0, 0])], delay=0.05)]
    return _recipe("bird", texture=(64, 64), visible_box=[1, 1.5, 1], bones=bones, cubes=cubes, idle=idle, walk=walk, attack=attack, attack_length=0.8,
                   notes="Wings pivot at the shoulder on the body's side and flap on Z. Head bobs with each step. For flight, "
                         "add a fly clip with wings at ±40 on Z; for a big bird scale the body and lengthen the legs. Attack: Peck: head back 0.2, strike down-forward 0.4 with a wing flick, settle by 0.8.")


def fish() -> dict:
    """Cod/salmon family: body with head, tail and tail fin chained behind, dorsal fin, two pectoral fins. 64x64."""
    bones = [
        {"name": "root", "origin": [0, 0, 0]},
        {"name": "body", "parent": "root", "origin": [0, 5, 0]},
        {"name": "head", "parent": "body", "origin": [0, 5, -5]},
        {"name": "top_fin", "parent": "body", "origin": [0, 8, -1]},
        {"name": "left_fin", "parent": "body", "origin": [2, 4, -2]},
        {"name": "right_fin", "parent": "body", "origin": [-2, 4, -2]},
        {"name": "tail", "parent": "body", "origin": [0, 5, 3]},
        {"name": "tail_fin", "parent": "tail", "origin": [0, 5, 6]},
    ]
    cubes = [
        {"name": "body_cube", "bone": "body", "from": [-2, 2, -5], "to": [2, 8, 3]},
        {"name": "head_cube", "bone": "head", "from": [-1.5, 3, -8], "to": [1.5, 7, -5]},
        {"name": "top_fin_cube", "bone": "top_fin", "from": [-0.5, 8, -2], "to": [0.5, 11, 1]},
        {"name": "left_fin_cube", "bone": "left_fin", "from": [2, 3.5, -3], "to": [4, 4.5, -1]},
        {"name": "right_fin_cube", "bone": "right_fin", "from": [-4, 3.5, -3], "to": [-2, 4.5, -1]},
        {"name": "tail_cube", "bone": "tail", "from": [-1, 3, 3], "to": [1, 7, 6]},
        {"name": "tail_fin_cube", "bone": "tail_fin", "from": [-0.5, 2, 6], "to": [0.5, 8, 9]},
    ]
    idle = [swing("tail", 2.0, 8, 1, axis=1), swing("tail_fin", 2.0, 12, 1, axis=1), bob("body", 2.0, 0.5)]
    walk = [swing("body", 1.0, 5, -1, axis=1), swing("tail", 1.0, 20, 1, axis=1), swing("tail_fin", 1.0, 30, 1, axis=1),
            swing("left_fin", 1.0, 15, 1, axis=1), swing("right_fin", 1.0, 15, -1, axis=1)]
    attack = [curve("head", "rotation", [(0, [0, 0, 0]), (0.2, [-12, 0, 0]), (0.4, [15, 0, 0]), (0.8, [0, 0, 0])]),
              curve("body", "position", [(0, [0, 0, 0]), (0.2, [0, 0, 1]), (0.4, [0, 0, -2]), (0.8, [0, 0, 0])]),
              curve("tail", "rotation", [(0, [0, 0, 0]), (0.2, [0, 25, 0]), (0.4, [0, -25, 0]), (0.6, [0, 10, 0]), (0.8, [0, 0, 0])]),
              curve("tail_fin", "rotation", [(0, [0, 0, 0]), (0.2, [0, 35, 0]), (0.4, [0, -35, 0]), (0.6, [0, 15, 0]), (0.8, [0, 0, 0])], delay=0.05)]
    return _recipe("fish", texture=(64, 64), visible_box=[1, 1, 1.5], bones=bones, cubes=cubes, idle=idle, walk=walk, attack=attack, attack_length=0.8,
                   notes="walk = swim: tail and tail_fin wag on Y with the fin leading more than the tail; body counter-wags. "
                         "Floats at Y 2-11; the entity hitbox height should match (~0.6). Flatten for a ray, lengthen for an eel. Attack: Bite: a hard tail beat throws the body forward (0.4) as the head snaps down.")


def serpent() -> dict:
    """Snake/worm family: head and four body segments chained so a Y-wag on each one slithers. 64x64."""
    bones = [
        {"name": "root", "origin": [0, 0, 0]},
        {"name": "body", "parent": "root", "origin": [0, 2, 0]},
        {"name": "head", "parent": "body", "origin": [0, 2, -4]},
        {"name": "segment_2", "parent": "body", "origin": [0, 2, 0]},
        {"name": "segment_3", "parent": "segment_2", "origin": [0, 2, 4]},
        {"name": "tail", "parent": "segment_3", "origin": [0, 2, 8]},
    ]
    cubes = [
        {"name": "segment_1", "bone": "body", "from": [-2, 0, -4], "to": [2, 4, 0]},
        {"name": "head_cube", "bone": "head", "from": [-2.5, 0, -9], "to": [2.5, 4, -4]},
        {"name": "segment_2_cube", "bone": "segment_2", "from": [-2, 0, 0], "to": [2, 4, 4]},
        {"name": "segment_3_cube", "bone": "segment_3", "from": [-2, 0, 4], "to": [2, 4, 8]},
        {"name": "tail_cube", "bone": "tail", "from": [-1, 0.5, 8], "to": [1, 3.5, 13]},
    ]
    idle = [bob("head", 2.0, 3.0, channel="rotation", axis=0), swing("tail", 2.0, 6, 1, axis=1)]
    walk = [swing("body", 1.0, 12, 1, axis=1), swing("segment_2", 1.0, 20, -1, axis=1),
            swing("segment_3", 1.0, 20, 1, axis=1), swing("tail", 1.0, 25, -1, axis=1), swing("head", 1.0, 8, -1, axis=1)]
    attack = [curve("body", "rotation", [(0, [0, 0, 0]), (0.3, [-25, 0, 0]), (0.5, [10, 0, 0]), (0.7, [2, 0, 0]), (1.0, [0, 0, 0])]),
              curve("head", "rotation", [(0, [0, 0, 0]), (0.3, [-30, 0, 0]), (0.5, [20, 0, 0]), (0.7, [5, 0, 0]), (1.0, [0, 0, 0])], delay=0.05),
              curve("body", "position", [(0, [0, 0, 0]), (0.3, [0, 1, 2]), (0.5, [0, 0, -4]), (0.7, [0, 0, -2]), (1.0, [0, 0, 0])]),
              curve("segment_2", "rotation", [(0, [0, 0, 0]), (0.3, [15, 0, 0]), (0.5, [-10, 0, 0]), (1.0, [0, 0, 0])], delay=0.05)]
    return _recipe("serpent", texture=(64, 64), visible_box=[1, 0.5, 2], bones=bones, cubes=cubes, idle=idle, walk=walk, attack=attack, attack_length=1.0,
                   notes="Alternating Y-rotation signs down the chain make the S-curve; each segment pivots at its front joint. "
                         "Add segments by chaining more bones with the same 4-unit step. Raise the head bone for a cobra. Attack: Strike: coil back and rear the head (0.3), lunge forward and down (0.5), recover.")


def insect() -> dict:
    """Beetle/spider family: empty root, thorax body with head and abdomen, six two-segment legs in a tripod gait. 64x64."""
    bones = [
        {"name": "root", "origin": [0, 0, 0]},
        {"name": "body", "parent": "root", "origin": [0, 4, 0]},
        {"name": "head", "parent": "body", "origin": [0, 4.5, -3]},
        {"name": "abdomen", "parent": "body", "origin": [0, 4, 0]},
    ]
    cubes = [
        {"name": "thorax", "bone": "body", "from": [-2, 3, -3], "to": [2, 6, 0]},
        {"name": "head_cube", "bone": "head", "from": [-1.5, 3, -6], "to": [1.5, 6, -3]},
        {"name": "abdomen_cube", "bone": "abdomen", "from": [-3, 2, 0], "to": [3, 6, 6]},
    ]
    for side, sx in (("left", 1), ("right", -1)):
        for pos, z in (("front", -3), ("mid", -2), ("back", -1)):
            x0 = 2 if sx > 0 else -3                                        # leg cube x range: 2..3 or -3..-2
            b, c = jointed_limb(f"{side}_{pos}_leg", "body", [
                ("", [2 * sx, 4, z + 0.5], [x0, 2, z], [x0 + 1, 4, z + 1]),          # coxa/femur, hip pivot
                ("lower", [2 * sx, 2, z + 0.5], [x0, 0, z], [x0 + 1, 2, z + 1]),     # tibia, knee pivot
            ])
            bones += b; cubes += c
    idle = [bob("head", 2.0, 4.0, channel="rotation", axis=1), bob("abdomen", 2.0, 3.0, channel="rotation", axis=0)]
    gait = (("left", "front", 1), ("left", "mid", -1), ("left", "back", 1), ("right", "front", -1), ("right", "mid", 1), ("right", "back", -1))
    walk = [swing(f"{s_}_{p}_leg", 1.0, 25, ph) for s_, p, ph in gait] + \
           [knee(f"{s_}_{p}_leg_lower", 1.0, 25, ph) for s_, p, ph in gait] + [bob("body", 1.0, 0.3)]
    attack = [curve("head", "rotation", [(0, [0, 0, 0]), (0.2, [-25, 0, 0]), (0.4, [30, 0, 0]), (0.55, [8, 0, 0]), (0.8, [0, 0, 0])]),
              curve("body", "rotation", [(0, [0, 0, 0]), (0.2, [10, 0, 0]), (0.4, [-8, 0, 0]), (0.8, [0, 0, 0])]),
              curve("abdomen", "rotation", [(0, [0, 0, 0]), (0.2, [-8, 0, 0]), (0.4, [6, 0, 0]), (0.8, [0, 0, 0])], delay=0.05),
              curve("left_front_leg", "rotation", [(0, [0, 0, 0]), (0.2, [-50, 0, 0]), (0.4, [10, 0, 0]), (0.8, [0, 0, 0])]),
              curve("right_front_leg", "rotation", [(0, [0, 0, 0]), (0.2, [-50, 0, 0]), (0.4, [10, 0, 0]), (0.8, [0, 0, 0])])]
    return _recipe("insect", texture=(64, 64), visible_box=[1, 0.75, 1.5], bones=bones, cubes=cubes, idle=idle, walk=walk, attack=attack, attack_length=0.8,
                   notes="Tripod gait: front+back of one side move with the middle leg of the other; *_lower joints bend like "
                         "knees. Legs are 1x2x1 + 1x2x1 under the thorax; splay the upper bones outward (rotation Z ±30) for a "
                         "spider, drop two legs for a beetle, lengthen the lower segments for a mantis. Attack: Bite: rear up with the front legs raised (0.2), snap the head down (0.4), settle.")


RECIPES = {"quadruped": quadruped, "biped": biped, "bird": bird, "fish": fish, "serpent": serpent, "insect": insect}


def recipe(plan: str) -> dict:
    if plan not in RECIPES:
        raise ValueError(f"unknown body plan {plan!r}; known: {', '.join(RECIPES)}")
    return RECIPES[plan]()


# ---------------------------------------------------------------------------------------------------------------
# Committed outputs

def rig_path(plan: str, kind: str) -> Path:
    ext = {"bbmodel": "bbmodel", "geo": "geo.json", "anim": "animation.json", "recipe": "recipe.json"}[kind]
    return RIG_DIR / f"{plan}.{ext}"


def load_rig(plan: str, kind: str) -> dict:
    return json.loads(rig_path(plan, kind).read_text(encoding="utf8"))


def rig_geo_for(plan: str, identifier: str) -> dict:
    """The committed geo export with the geometry identifier renamed to the mob's."""
    geo = load_rig(plan, "geo")
    geo["minecraft:geometry"][0]["description"]["identifier"] = f"geometry.{identifier}"
    return geo


def rig_animation_for(plan: str, identifier: str) -> dict:
    """The committed animation export with clips renamed animation.<identifier>.<clip>."""
    anim = load_rig(plan, "anim")
    anim["animations"] = {name.replace(f"animation.{plan}.", f"animation.{identifier}."): clip
                          for name, clip in anim["animations"].items()}
    return anim


def rig_texture_size(plan: str) -> tuple[int, int]:
    rec = load_rig(plan, "recipe")
    return rec["texture_width"], rec["texture_height"]


def rig_bbmodel_for(plan: str, identifier: str, mod_id: str) -> dict:
    """The committed .bbmodel renamed to the mob (model identifier, mod id, clip names) so the designer edits it in place."""
    m = load_rig(plan, "bbmodel")
    m["name"] = identifier
    m["model_identifier"] = identifier
    m["mod_id"] = mod_id
    for a in m.get("animations", []):
        a["name"] = a["name"].replace(f"animation.{plan}.", f"animation.{identifier}.")
    return m


def stage_rig(workspace: Path, plan: str, identifier: str, mod_id: str, models_dir: str = "models") -> dict:
    """Place the base rig as models/<identifier>.bbmodel unless the designer already has a source there."""
    target = workspace / models_dir / f"{identifier}.bbmodel"
    if target.is_file():
        return {"staged": False, "path": str(target.relative_to(workspace)), "plan": plan}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rig_bbmodel_for(plan, identifier, mod_id), indent=2) + "\n", encoding="utf8")
    return {"staged": True, "path": str(target.relative_to(workspace)), "plan": plan}
