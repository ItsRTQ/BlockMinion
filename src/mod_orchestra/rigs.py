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


def _clips(ident: str, idle: list[dict], walk: list[dict]) -> list[dict]:
    return [{"name": f"animation.{ident}.idle", "length": 2.0, "loop": "loop", "channels": idle},
            {"name": f"animation.{ident}.walk", "length": 1.0, "loop": "loop", "channels": walk}]


# ---------------------------------------------------------------------------------------------------------------
# Anatomy table. Each recipe builder returns the data the node driver feeds to the server.

def _recipe(plan: str, *, texture: tuple[int, int], visible_box: list, bones: list[dict], cubes: list[dict],
            idle: list[dict], walk: list[dict], notes: str) -> dict:
    return {
        "plan": plan, "name": plan, "identifier": plan, "modid": "rigs", "model_type": "Entity",
        "texture_width": texture[0], "texture_height": texture[1], "visible_box": visible_box,
        "bones": bones, "cubes": pack_box_uv(cubes, *texture),
        "animations": _clips(plan, idle, walk), "notes": notes,
    }


def quadruped() -> dict:
    """Cow/wolf/deer family: body root with a neck-hinged head, four hip-pivoted legs and a tail. 64x32."""
    bones = [
        {"name": "body", "origin": [0, 8, 0]},
        {"name": "head", "parent": "body", "origin": [0, 11, -6]},
        {"name": "tail", "parent": "body", "origin": [0, 11, 6]},
        {"name": "left_front_leg", "parent": "body", "origin": [3, 6, -4]},
        {"name": "right_front_leg", "parent": "body", "origin": [-3, 6, -4]},
        {"name": "left_back_leg", "parent": "body", "origin": [3, 6, 4]},
        {"name": "right_back_leg", "parent": "body", "origin": [-3, 6, 4]},
    ]
    cubes = [
        {"name": "body_cube", "bone": "body", "from": [-4, 6, -6], "to": [4, 12, 6]},
        {"name": "head_cube", "bone": "head", "from": [-3, 8, -11], "to": [3, 14, -6]},
        {"name": "snout", "bone": "head", "from": [-2, 8, -13], "to": [2, 11, -11]},
        {"name": "tail_cube", "bone": "tail", "from": [-1, 10, 6], "to": [1, 12, 10]},
        {"name": "left_front_leg_cube", "bone": "left_front_leg", "from": [2, 0, -5], "to": [4, 6, -3]},
        {"name": "right_front_leg_cube", "bone": "right_front_leg", "from": [-4, 0, -5], "to": [-2, 6, -3]},
        {"name": "left_back_leg_cube", "bone": "left_back_leg", "from": [2, 0, 3], "to": [4, 6, 5]},
        {"name": "right_back_leg_cube", "bone": "right_back_leg", "from": [-4, 0, 3], "to": [-2, 6, 5]},
    ]
    idle = [bob("head", 2.0, 3.0, channel="rotation", axis=0), bob("tail", 2.0, 8.0, channel="rotation", axis=1)]
    walk = [swing("left_front_leg", 1.0, 25, 1), swing("right_back_leg", 1.0, 25, 1),
            swing("right_front_leg", 1.0, 25, -1), swing("left_back_leg", 1.0, 25, -1),
            bob("body", 1.0, 0.5)]
    return _recipe("quadruped", texture=(64, 32), visible_box=[2, 2, 1], bones=bones, cubes=cubes, idle=idle, walk=walk,
                   notes="Diagonal gait: left_front with right_back, right_front with left_back. Head pivot is the neck "
                         "(top-front of body), tail pivot the rump. Scale legs taller for deer, body longer for dachshund.")


def biped() -> dict:
    """Villager/zombie family on the vanilla 32-high skeleton: hip root, head, two arms, two legs. 64x64."""
    bones = [
        {"name": "body", "origin": [0, 12, 0]},
        {"name": "head", "parent": "body", "origin": [0, 24, 0]},
        {"name": "left_arm", "parent": "body", "origin": [5, 22, 0]},
        {"name": "right_arm", "parent": "body", "origin": [-5, 22, 0]},
        {"name": "left_leg", "parent": "body", "origin": [2, 12, 0]},
        {"name": "right_leg", "parent": "body", "origin": [-2, 12, 0]},
    ]
    cubes = [
        {"name": "torso", "bone": "body", "from": [-4, 12, -2], "to": [4, 24, 2]},
        {"name": "head_cube", "bone": "head", "from": [-4, 24, -4], "to": [4, 32, 4]},
        {"name": "left_arm_cube", "bone": "left_arm", "from": [4, 12, -2], "to": [8, 24, 2]},
        {"name": "right_arm_cube", "bone": "right_arm", "from": [-8, 12, -2], "to": [-4, 24, 2]},
        {"name": "left_leg_cube", "bone": "left_leg", "from": [0, 0, -2], "to": [4, 12, 2]},
        {"name": "right_leg_cube", "bone": "right_leg", "from": [-4, 0, -2], "to": [0, 12, 2]},
    ]
    idle = [bob("head", 2.0, 2.0, channel="rotation", axis=0), bob("left_arm", 2.0, 2.5, channel="rotation", axis=2),
            bob("right_arm", 2.0, -2.5, channel="rotation", axis=2), bob("body", 2.0, 0.3)]
    walk = [swing("left_leg", 1.0, 30, 1), swing("right_leg", 1.0, 30, -1),
            swing("left_arm", 1.0, 30, -1), swing("right_arm", 1.0, 30, 1), bob("body", 1.0, 0.4)]
    return _recipe("biped", texture=(64, 64), visible_box=[1.5, 2.5, 1.25], bones=bones, cubes=cubes, idle=idle, walk=walk,
                   notes="Vanilla humanoid pivots (head 24, arms ±5/22, legs ±2/12): armor and held items line up. Arms swing "
                         "opposite to the leg on the same side. Shrink to 3/4 for a child, widen torso for a brute.")


def bird() -> dict:
    """Chicken/parrot family: compact body, head on a neck pivot, beak, two flapping wings, tail, thin legs. 64x32."""
    bones = [
        {"name": "body", "origin": [0, 6, 0]},
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
    return _recipe("bird", texture=(64, 32), visible_box=[1, 1.5, 1], bones=bones, cubes=cubes, idle=idle, walk=walk,
                   notes="Wings pivot at the shoulder on the body's side and flap on Z. Head bobs with each step. For flight, "
                         "add a fly clip with wings at ±40 on Z; for a big bird scale the body and lengthen the legs.")


def fish() -> dict:
    """Cod/salmon family: body with head, tail and tail fin chained behind, dorsal fin, two pectoral fins. 64x32."""
    bones = [
        {"name": "body", "origin": [0, 5, 0]},
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
    return _recipe("fish", texture=(64, 32), visible_box=[1, 1, 1.5], bones=bones, cubes=cubes, idle=idle, walk=walk,
                   notes="walk = swim: tail and tail_fin wag on Y with the fin leading more than the tail; body counter-wags. "
                         "Floats at Y 2-11; the entity hitbox height should match (~0.6). Flatten for a ray, lengthen for an eel.")


def serpent() -> dict:
    """Snake/worm family: head and four body segments chained so a Y-wag on each one slithers. 64x32."""
    bones = [
        {"name": "body", "origin": [0, 2, 0]},
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
    return _recipe("serpent", texture=(64, 32), visible_box=[1, 0.5, 2], bones=bones, cubes=cubes, idle=idle, walk=walk,
                   notes="Alternating Y-rotation signs down the chain make the S-curve; each segment pivots at its front joint. "
                         "Add segments by chaining more bones with the same 4-unit step. Raise the head bone for a cobra.")


def insect() -> dict:
    """Beetle/spider family: thorax root with head and abdomen, six legs in a tripod gait. 64x32."""
    bones = [
        {"name": "body", "origin": [0, 4, 0]},
        {"name": "head", "parent": "body", "origin": [0, 4.5, -3]},
        {"name": "abdomen", "parent": "body", "origin": [0, 4, 0]},
        {"name": "left_front_leg", "parent": "body", "origin": [2, 4, -2.5]},
        {"name": "left_mid_leg", "parent": "body", "origin": [2, 4, -1.5]},
        {"name": "left_back_leg", "parent": "body", "origin": [2, 4, -0.5]},
        {"name": "right_front_leg", "parent": "body", "origin": [-2, 4, -2.5]},
        {"name": "right_mid_leg", "parent": "body", "origin": [-2, 4, -1.5]},
        {"name": "right_back_leg", "parent": "body", "origin": [-2, 4, -0.5]},
    ]
    legs = []
    for side, sx in (("left", 1), ("right", -1)):
        for pos, z in (("front", -3), ("mid", -2), ("back", -1)):
            x0, x1 = (2, 3) if sx > 0 else (-3, -2)
            legs.append({"name": f"{side}_{pos}_leg_cube", "bone": f"{side}_{pos}_leg", "from": [x0, 0, z], "to": [x1, 4, z + 1]})
    cubes = [
        {"name": "thorax", "bone": "body", "from": [-2, 3, -3], "to": [2, 6, 0]},
        {"name": "head_cube", "bone": "head", "from": [-1.5, 3, -6], "to": [1.5, 6, -3]},
        {"name": "abdomen_cube", "bone": "abdomen", "from": [-3, 2, 0], "to": [3, 6, 6]},
    ] + legs
    idle = [bob("head", 2.0, 4.0, channel="rotation", axis=1), bob("abdomen", 2.0, 3.0, channel="rotation", axis=0)]
    walk = [swing(f"{s}_{p}_leg", 1.0, 25, ph) for s, p, ph in (
        ("left", "front", 1), ("left", "mid", -1), ("left", "back", 1),
        ("right", "front", -1), ("right", "mid", 1), ("right", "back", -1))] + [bob("body", 1.0, 0.3)]
    return _recipe("insect", texture=(64, 32), visible_box=[1, 0.75, 1.5], bones=bones, cubes=cubes, idle=idle, walk=walk,
                   notes="Tripod gait: front+back of one side move with the middle leg of the other. Legs are 1x4x1 under the "
                         "thorax; splay them outward (rotation Z ±30 on the bones) for a spider, drop two for a beetle.")


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
