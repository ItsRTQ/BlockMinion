"""How a 3D item is held: computed, never guessed.

A model is described in Blockbench coordinates (pixels; +Y up; -Z is the front) by three technical facts the designer (or the
user) declares: the hold STYLE (`aim`: pointed at something, like a gun or a wand; `wield`: swung or carried upright, like a
sword or a staff; `carry`: anything else), the axis its FRONT points to (`-z`, `+x`, ...), the axis its TOP points to, and
the GRIP point (the origin of a bone named `grip`, or a style default). From those the controller derives every display
transform (first/third person, ground, frame, head) by canonicalising the model (front -> +Y, top -> style side, grip ->
origin), fitting its length, and then applying a vanilla transform set that is known to hold a sprite correctly:
`item/handheld` for wield (how a sword sits), `crossbow` firing for aim (how a charged crossbow points), `item/generated`
for carry. The sprite those transforms were made for lies on the diagonal of its 16x16 icon with the handle bottom-left,
so the canonical model is rotated onto that diagonal and its grip moved to the sprite's handle first.

Everything is plain matrices here; `display()` returns the JSON `display` block. The user can tweak a style for the whole
project (rotation offsets, translation offsets, a scale factor per context) and the tweaks are applied last.
"""
from __future__ import annotations

import math

STYLES = ("aim", "wield", "carry")
AXES = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
CONTEXTS = ("thirdperson_righthand", "thirdperson_lefthand", "firstperson_righthand", "firstperson_lefthand", "ground", "fixed", "head", "gui")

# vanilla display sets (rotation degrees, translation px, scale), from the game's assets
GENERATED = {"ground": ([0, 0, 0], [0, 2, 0], 0.5), "head": ([0, 180, 0], [0, 13, 7], 1.0),
             "thirdperson_righthand": ([0, 0, 0], [0, 3, 1], 0.55), "thirdperson_lefthand": ([0, 0, 0], [0, 3, 1], 0.55),
             "firstperson_righthand": ([0, -90, 25], [1.13, 3.2, 1.13], 0.68), "firstperson_lefthand": ([0, 90, -25], [1.13, 3.2, 1.13], 0.68),
             "fixed": ([0, 180, 0], [0, 0, 0], 1.0)}
HANDHELD = {**GENERATED, "thirdperson_righthand": ([0, -90, 55], [0, 4.0, 0.5], 0.85), "thirdperson_lefthand": ([0, 90, -55], [0, 4.0, 0.5], 0.85),
            "firstperson_righthand": ([0, -90, 25], [1.13, 3.2, 1.13], 0.68), "firstperson_lefthand": ([0, 90, -25], [1.13, 3.2, 1.13], 0.68)}
CROSSBOW_FIRING = {**GENERATED, "thirdperson_righthand": ([-90, 0, -60], [2, 0.1, -3], 0.9), "thirdperson_lefthand": ([-90, 0, 30], [2, 0.1, -3], 0.9),
                   "firstperson_righthand": ([-90, 0, -55], [1.13, 3.2, 1.13], 0.68), "firstperson_lefthand": ([-90, 0, 35], [1.13, 3.2, 1.13], 0.68)}
BASE = {"wield": HANDHELD, "aim": CROSSBOW_FIRING, "carry": GENERATED}
# where the sprite those sets hold has its handle (px from the icon centre), and how long it is along its diagonal
HANDLE = {"wield": (-5.0, -5.0, 0.0), "aim": (-3.5, -3.5, 0.0), "carry": (0.0, 0.0, 0.0)}
LENGTH = {"wield": 16.0, "aim": 16.0, "carry": 12.0}
AIM_FP_YAW, AIM_FP_SCALE, AIM_FP_GRIP = 12.0, 1.0, (1.5, -2.5, -3.0)   # first-person aim: turn toward the centre (deg), base scale, grip position (px)
TOP_TARGET = (-1, 0, 0)   # canonical: front +Y, top to the sprite's upper-left (after the 45° turn onto the diagonal)

Vec = tuple[float, float, float]
Mat = tuple[Vec, Vec, Vec]


def _rx(d: float) -> Mat:
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    return ((1, 0, 0), (0, c, -s), (0, s, c))


def _ry(d: float) -> Mat:
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    return ((c, 0, s), (0, 1, 0), (-s, 0, c))


def _rz(d: float) -> Mat:
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def mul(a: Mat, b: Mat) -> Mat:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore[return-value]


def apply(m: Mat, v: Vec) -> Vec:
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))  # type: ignore[return-value]


def euler_to_matrix(rx: float, ry: float, rz: float) -> Mat:
    """Minecraft's ItemTransform rotation: JOML rotationXYZ = Rx * Ry * Rz (Z is applied to the vector first)."""
    return mul(mul(_rx(rx), _ry(ry)), _rz(rz))


def matrix_to_euler(m: Mat) -> tuple[float, float, float]:
    """Inverse of euler_to_matrix (degrees). For Rx*Ry*Rz: m[0][2] = sin(ry)."""
    sy = max(-1.0, min(1.0, m[0][2]))
    ry = math.degrees(math.asin(sy))
    if abs(sy) < 0.999999:
        rx = math.degrees(math.atan2(-m[1][2], m[2][2]))
        rz = math.degrees(math.atan2(-m[0][1], m[0][0]))
    else:   # gimbal lock: put everything into rx
        rx = math.degrees(math.atan2(m[2][1], m[1][1]))
        rz = 0.0
    return (_clean(rx), _clean(ry), _clean(rz))


def _clean(d: float) -> float:
    d = round(d, 2)
    if d == -0.0:
        d = 0.0
    return d


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def frame_rotation(front: Vec, top: Vec, front_to: Vec, top_to: Vec) -> Mat:
    """The rotation taking the orthonormal frame (front, top, front x top) onto (front_to, top_to, front_to x top_to)."""
    src = (front, top, cross(front, top)); dst = (front_to, top_to, cross(front_to, top_to))
    # R = Dst * Src^T  (columns of Dst against rows of Src)
    return tuple(tuple(sum(dst[k][i] * src[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore[return-value]


def bbox(model: dict) -> tuple[Vec, Vec]:
    lo, hi = [1e9] * 3, [-1e9] * 3
    for e in model.get("elements") or []:
        f, t = e.get("from"), e.get("to")
        if not (isinstance(f, list) and isinstance(t, list) and len(f) == 3 and len(t) == 3):
            continue
        for i in range(3):
            lo[i] = min(lo[i], float(f[i]), float(t[i])); hi[i] = max(hi[i], float(f[i]), float(t[i]))
    if lo[0] > hi[0]:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    return tuple(lo), tuple(hi)  # type: ignore[return-value]


def grip_point(model: dict, style: str, front: str) -> tuple[Vec, str]:
    """The grip: a bone named `grip` (its origin), else a style default on the bounding box. Returns (point, how)."""
    for g in model.get("groups") or []:
        if str(g.get("name", "")).lower() == "grip" and isinstance(g.get("origin"), list):
            return tuple(float(v) for v in g["origin"]), "bone grip"  # type: ignore[return-value]
    lo, hi = bbox(model)
    c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    if style == "wield":   # the end opposite the front
        f = AXES[front]; back = tuple(hi[i] if f[i] < 0 else lo[i] if f[i] > 0 else c[i] for i in range(3))
        return back, "bounding box, the end opposite the front"  # type: ignore[return-value]
    if style == "aim":   # a third of the way from the back (where a stock meets a receiver)
        f = AXES[front]; back = tuple(hi[i] if f[i] < 0 else lo[i] if f[i] > 0 else c[i] for i in range(3))
        return tuple(back[i] + (c[i] - back[i]) * 0.66 for i in range(3)), "bounding box, a third from the back"  # type: ignore[return-value]
    return c, "bounding box centre"  # type: ignore[return-value]


def length_along(model: dict, front: str) -> float:
    lo, hi = bbox(model); i = [k for k in range(3) if AXES[front][k] != 0][0]
    return hi[i] - lo[i]


def _default_top(front: str, model: dict | None = None) -> str:
    """Where the item's top points. Upright items (front along Y) have no top: their thin side goes to ±Z like the sprite's."""
    if front not in ("+y", "-y"):
        return "+y"
    lo, hi = bbox(model or {})
    return "+x" if (hi[0] - lo[0]) <= (hi[2] - lo[2]) else "+z"   # the thinner of x/z is the flat side


def display(model: dict, *, style: str, front: str, top: str | None = None, tweaks: dict | None = None, size: float = 1.0) -> dict:
    """The item model JSON `display` block for this model held in this style. tweaks: {context: {rotation: [dx,dy,dz], translation: [..], scale: f}};
    size: this item's own factor on top (the "Size in hand" control), applied everywhere but the inventory."""
    size = max(0.3, min(3.0, float(size or 1.0)))
    if style not in STYLES:
        raise ValueError(f"style must be one of {STYLES}")
    if front not in AXES:
        raise ValueError(f"front must be one of {sorted(AXES)}")
    top = top or _default_top(front, model)
    if top not in AXES or AXES[top] == AXES[front] or AXES[top] == tuple(-v for v in AXES[front]):
        raise ValueError("top must be an axis perpendicular to front")
    g, _ = grip_point(model, style, front)
    upright = front in ("+y", "-y")
    if style == "carry":
        canon = frame_rotation(AXES[front], AXES[top], (0, 0, -1), (0, 1, 0))      # a plain item: front to -Z, top up (as its icon)
    elif upright:   # no top: the thin side (declared as `top`) goes to +Z, so the flat faces show like the sprite's
        canon = frame_rotation(AXES[front], AXES[top], (0, 1, 0), (0, 0, 1))
    else:
        canon = frame_rotation(AXES[front], AXES[top], (0, 1, 0), TOP_TARGET)      # front -> +Y, top -> the sprite's upper-left
    length = max(1.0, length_along(model, front))
    s = max(0.3, min(2.0, LENGTH[style] / length))
    m = mul(_rz(-45.0), canon) if style != "carry" else canon                      # onto the sprite's diagonal
    handle = HANDLE[style]
    k = tuple(s * v + handle[i] for i, v in enumerate(apply(m, (0 - g[0], 8 - g[1], 0 - g[2]))))   # model origin sits at the icon's bottom centre
    out = {}
    tw = tweaks or {}
    for ctx, (rot, tr, sc) in BASE[style].items():
        if style == "aim" and ctx.startswith("firstperson"):
            # a shooter's hold, defined straight in the camera's frame (camera looks down -Z): barrel forward with a slight turn toward
            # the centre, top up, grip low and to the side; no sprite in between
            left = ctx.endswith("lefthand"); side = -1 if left else 1
            yaw = math.radians(AIM_FP_YAW) * side
            rv = frame_rotation((0, 1, 0), TOP_TARGET, (-math.sin(yaw), 0, -math.cos(yaw)), (0, 1, 0))
            rt = mul(rv, canon); sc = AIM_FP_SCALE
            kk = apply(canon, (0 - g[0], 8 - g[1], 0 - g[2]))   # grip -> origin, then the hold's position
            tt = tuple(AIM_FP_GRIP[i] * (side if i == 0 else 1) + sc * s * sum(rv[i][j] * kk[j] for j in range(3)) for i in range(3))
            rot_e = list(matrix_to_euler(rt)); scale = sc * s
        else:
            rv = euler_to_matrix(*rot)
            rt = mul(rv, m)
            tt = tuple(tr[i] + sc * sum(rv[i][j] * k[j] for j in range(3)) for i in range(3))
            rot_e = list(matrix_to_euler(rt)); scale = sc * s
        t = tw.get(ctx) or {}
        rot_e = [_clean(rot_e[i] + float((t.get("rotation") or [0, 0, 0])[i])) for i in range(3)]
        tt = [_clean(tt[i] + float((t.get("translation") or [0, 0, 0])[i])) for i in range(3)]
        scale = _clean(scale * float(t.get("scale") or 1.0) * size)
        tt = [max(-80.0, min(80.0, v)) for v in tt]
        out[ctx] = {"rotation": rot_e, "translation": tt, "scale": [scale, scale, scale]}
    out["gui"] = {"rotation": [0, 0, 0], "translation": [0, 0, 0], "scale": [1, 1, 1]}   # the renderer draws the 2D icon there
    return out


def describe(model: dict, style: str, front: str, top: str | None = None) -> dict:
    g, how = grip_point(model, style, front)
    lo, hi = bbox(model)
    return {"style": style, "front": front, "top": top or _default_top(front, model), "grip": [round(v, 2) for v in g], "grip_from": how,
            "length_px": round(length_along(model, front), 2), "bbox": [[round(v, 2) for v in lo], [round(v, 2) for v in hi]]}
