"""A picture of the item in the player's hand before anything is installed.

The game's own chain, reproduced (Minecraft 1.21.1, model space in pixels, y down, as the player model is defined):
third person: `ItemInHandLayer` goes to the arm pivot, applies the arm's pose, turns X -90 and Y 180, moves (1, 2, -10) px,
then `ItemRenderer` applies the item's display transform (translation, rotation XYZ, scale) and the -8 px centring; our
renderer then puts the model's origin at the icon's bottom centre (+8, 0, +8). The player model is drawn with
`scale(-1, -1, 1)` and `translate(0, -1.501, 0)`, so a model-space point (x, y, z) is the world point (-x, 24 - y, z):
that is exactly the space of the PAL player rig (right arm pivot (5, 22, 0)), so the item can be composed into that rig.
First person: `ItemInHandRenderer` holds the right-hand item at (0.56, -0.52, -0.72) blocks in front of a camera that looks
down -Z, then the same display transform.

`compose()` writes one .bbmodel with the rig (arm raised) and the item baked in place (scale into the cubes, rotation as
three nested single-axis groups, translation into the cubes), and `render()` turns it into a PNG with the vendored
Blockbench renderer (Node, no network).
"""
from __future__ import annotations

import copy
import json
import math
import subprocess
import uuid
from pathlib import Path

from . import pose
from .validation import InputError

RENDER_SCRIPT = Path(__file__).resolve().parent / "resources" / "blockbench" / "render_bbmodel.mjs"

Affine = tuple[pose.Mat, pose.Vec]   # (rotation*scale matrix, translation)


def _t(v: pose.Vec) -> Affine:
    return (((1, 0, 0), (0, 1, 0), (0, 0, 1)), tuple(float(c) for c in v))  # type: ignore[return-value]


def _r(m: pose.Mat) -> Affine:
    return (m, (0.0, 0.0, 0.0))


def _s(f: float) -> Affine:
    return (((f, 0, 0), (0, f, 0), (0, 0, f)), (0.0, 0.0, 0.0))


def _chain(*ops: Affine) -> Affine:
    """ops applied left to right to a point: result = op1 ∘ op2 ∘ ... (op_last acts on the point first)."""
    m, t = ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.0, 0.0, 0.0)
    for om, ot in ops:
        t = tuple(t[i] + sum(m[i][k] * ot[k] for k in range(3)) for i in range(3))
        m = pose.mul(m, om)
    return m, t  # type: ignore[return-value]


def _apply(a: Affine, p: pose.Vec) -> pose.Vec:
    m, t = a
    return tuple(t[i] + sum(m[i][k] * p[k] for k in range(3)) for i in range(3))  # type: ignore[return-value]


def _item_transform(d: dict) -> Affine:
    rot, tr, sc = d["rotation"], d["translation"], d["scale"][0]
    return _chain(_t(tuple(tr)), _r(pose.euler_to_matrix(*rot)), _s(sc))


def third_person_right(display: dict, arm_x_rot: float = -90.0) -> Affine:
    """Item model point (px, Blockbench) -> world px in the PAL rig's space, held in the raised right hand."""
    model_space = _chain(_t((-5, 2, 0)), _r(pose._rx(arm_x_rot)), _r(pose._rx(-90)), _r(pose._ry(180)), _t((1, 2, -10)),
                         _item_transform(display["thirdperson_righthand"]), _t((-8, -8, -8)), _t((8, 0, 8)))
    flip = (((-1, 0, 0), (0, -1, 0), (0, 0, 1)), (0.0, 24.0, 0.0))
    return _chain(flip, model_space)


def first_person_right(display: dict) -> Affine:
    """Item model point -> camera-space px (camera at the origin looking down -Z, y up)."""
    return _chain(_t((0.56 * 16, -0.52 * 16, -0.72 * 16)), _item_transform(display["firstperson_righthand"]), _t((-8, -8, -8)), _t((8, 0, 8)))


def _euler_groups(m: pose.Mat, origin: pose.Vec, prefix: str) -> tuple[list[dict], str]:
    """Three nested single-axis groups realising rotation m about origin (outer X, then Y, inner Z: m = Rx*Ry*Rz)."""
    rx, ry, rz = pose.matrix_to_euler(m)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    groups = [{"name": f"{prefix}_rx", "uuid": ids[0], "origin": list(origin), "rotation": [rx, 0, 0]},
              {"name": f"{prefix}_ry", "uuid": ids[1], "origin": list(origin), "rotation": [0, ry, 0], "parent": ids[0]},
              {"name": f"{prefix}_rz", "uuid": ids[2], "origin": list(origin), "rotation": [0, 0, rz], "parent": ids[1]}]
    return groups, ids[2]


def _bake_item(item: dict, a: Affine, prefix: str) -> tuple[list[dict], list[dict], list]:
    """Item elements placed by affine a: scale+translation into the cubes, rotation as nested groups. Returns (groups, elements, outliner node)."""
    m, t = a
    # polar split: m = R * s (uniform scale)
    s = math.sqrt(sum(m[i][0] ** 2 for i in range(3)))
    r = tuple(tuple(m[i][j] / s for j in range(3)) for i in range(3))
    groups, inner = _euler_groups(r, t, prefix)  # type: ignore[arg-type]
    elements = []
    for e in item.get("elements") or []:
        if not (isinstance(e.get("from"), list) and isinstance(e.get("to"), list)):
            continue
        ne = copy.deepcopy(e)
        ne["uuid"] = str(uuid.uuid4())
        ne["from"] = [s * float(v) + t[i] for i, v in enumerate(e["from"])]
        ne["to"] = [s * float(v) + t[i] for i, v in enumerate(e["to"])]
        if isinstance(e.get("origin"), list):
            ne["origin"] = [s * float(v) + t[i] for i, v in enumerate(e["origin"])]
        ne.pop("parent", None)
        elements.append(ne)
    # the item's own bone rotations are rest-pose zero in a GeckoLib export; cubes carry their own rotation, kept as is
    node = {"uuid": groups[0]["uuid"], "isOpen": True, "children": [{"uuid": groups[1]["uuid"], "isOpen": True,
            "children": [{"uuid": groups[2]["uuid"], "isOpen": True, "children": [el["uuid"] for el in elements]}]}]}
    for g in groups:
        g.setdefault("rotation", [0, 0, 0])
    return groups, elements, node


ARM_POSE = {"aim": -80.0, "wield": -18.0, "carry": -18.0}   # vanilla: ArmPose.CROSSBOW_HOLD raises the arm ~80°, ArmPose.ITEM ~18° (model xRot, degrees)


def compose(rig: dict, item: dict, display: dict, *, context: str = "thirdperson_righthand", arm_x_rot: float = -18.0) -> dict:
    """The rig (arm posed as vanilla poses it for a held item) holding the item, or the item alone in camera space for first person."""
    if context not in ("thirdperson_righthand", "firstperson_righthand"):
        raise InputError("context must be thirdperson_righthand or firstperson_righthand")
    out = copy.deepcopy(rig)
    out["name"] = f"preview_{context}"
    if context == "firstperson_righthand":   # the item alone where the camera sees it; a marker cube stands for the camera
        out["elements"], out["groups"], out["outliner"] = [], [], []
        out["textures"] = []
        a = first_person_right(display)
        groups, elements, node = _bake_item(item, a, "item")
        marker = {"name": "camera", "uuid": str(uuid.uuid4()), "from": [-0.5, -0.5, -0.5], "to": [0.5, 0.5, 0.5], "color": 2}
        out["groups"] = groups; out["elements"] = elements + [marker]; out["outliner"] = [node, marker["uuid"]]
    else:
        for g in out.get("groups") or []:   # raise the right arm (world rotation +90 about X == model xRot -90)
            if g.get("name") == "right_arm":
                g["rotation"] = [-arm_x_rot, 0, 0]
        a = third_person_right(display, arm_x_rot)
        groups, elements, node = _bake_item(item, a, "item")
        out["groups"] = (out.get("groups") or []) + groups
        out["elements"] = (out.get("elements") or []) + elements
        out["outliner"] = (out.get("outliner") or []) + [node]
    out["resolution"] = out.get("resolution") or {"width": 64, "height": 64}
    return out


def render(bbmodel_path: Path, out_png: Path, views: list[str] = ("front", "right", "iso"), size: int = 200) -> dict:
    """PNG contact sheet of a .bbmodel with the vendored renderer."""
    try:
        r = subprocess.run(["node", str(RENDER_SCRIPT), str(bbmodel_path), str(out_png), ",".join(views), str(size)], capture_output=True, text=True, timeout=90)
    except FileNotFoundError:
        raise InputError("Node.js is needed to render the preview") from None
    if r.returncode != 0:
        raise InputError("preview render failed: " + (r.stderr.strip().splitlines() or ["unknown"])[-1][:300])
    return json.loads(r.stdout)
