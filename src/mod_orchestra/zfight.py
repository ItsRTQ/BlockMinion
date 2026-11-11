"""Z-fighting: two cubes whose faces lie on the same plane, face the same way and overlap flicker in the game.

A rendered face is one of the six sides of a box; two faces fight when they are coplanar (same axis, same coordinate), point the
same way (both the +X side, say) and their rectangles overlap on the other two axes. Cubes that merely touch (one's +X side
against the other's -X side) are fine. `fix` nudges the smaller cube's face 0.02 px outward along the normal, so the detail
renders above the body without a visible change; it is applied to the installed copy of a geo, never to the designer's delivery.
Cubes with a rotation are left alone (their faces are not axis-aligned)."""
from __future__ import annotations

import json

NUDGE = 0.02
EPS = 1e-6


def _boxes(geo: dict) -> list[tuple[str, int, list[float], list[float], dict]]:
    out = []
    for b in geo["minecraft:geometry"][0]["bones"]:
        for i, c in enumerate(b.get("cubes") or []):
            o, s = c.get("origin"), c.get("size")
            if not (isinstance(o, list) and isinstance(s, list) and len(o) == 3 and len(s) == 3):
                continue
            if c.get("rotation") and any(abs(float(v)) > EPS for v in c["rotation"]):
                continue
            lo = [float(o[k]) for k in range(3)]; hi = [lo[k] + float(s[k]) for k in range(3)]
            out.append((b["name"], i, lo, hi, c))
    return out


def _overlap(lo_a, hi_a, lo_b, hi_b, axes) -> bool:
    return all(min(hi_a[k], hi_b[k]) - max(lo_a[k], lo_b[k]) > EPS for k in axes)


def find(geo: dict) -> list[dict]:
    """Every fighting pair: {a, b, axis, side, overlap_px}. a is the smaller cube (by volume)."""
    boxes = _boxes(geo)
    pairs = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            na, ia, lo_a, hi_a, ca = boxes[i]; nb, ib, lo_b, hi_b, cb = boxes[j]
            for axis in range(3):
                others = [k for k in range(3) if k != axis]
                for side, pa, pb in (("+", hi_a[axis], hi_b[axis]), ("-", lo_a[axis], lo_b[axis])):
                    if abs(pa - pb) < EPS and _overlap(lo_a, hi_a, lo_b, hi_b, others):
                        va = (hi_a[0] - lo_a[0]) * (hi_a[1] - lo_a[1]) * (hi_a[2] - lo_a[2])
                        vb = (hi_b[0] - lo_b[0]) * (hi_b[1] - lo_b[1]) * (hi_b[2] - lo_b[2])
                        small, big = ((na, ia, ca), (nb, ib, cb)) if va <= vb else ((nb, ib, cb), (na, ia, ca))
                        area = 1.0
                        for k in others:
                            area *= min(hi_a[k], hi_b[k]) - max(lo_a[k], lo_b[k])
                        pairs.append({"a": f"{small[0]}#{small[1]}", "b": f"{big[0]}#{big[1]}", "axis": "xyz"[axis], "side": side,
                                      "overlap_px": round(area, 2), "_cube": small[2]})
    return pairs


def fix(geo: dict) -> tuple[dict, list[dict]]:
    """A copy of the geo with the smaller cube of every fighting pair nudged outward; the pairs found (without internals)."""
    geo = json.loads(json.dumps(geo))
    pairs = find(geo)
    for p in pairs:
        c = p["_cube"]; axis = "xyz".index(p["axis"])
        if p["side"] == "+":
            c["size"][axis] = round(float(c["size"][axis]) + NUDGE, 4)
        else:
            c["origin"][axis] = round(float(c["origin"][axis]) - NUDGE, 4)
            c["size"][axis] = round(float(c["size"][axis]) + NUDGE, 4)
    return geo, [{k: v for k, v in p.items() if k != "_cube"} for p in pairs]


def describe(pairs: list[dict]) -> str:
    if not pairs:
        return ""
    shown = "; ".join(f"{p['a']} over {p['b']} ({p['side']}{p['axis']} face, {p['overlap_px']} px²)" for p in pairs[:6])
    more = f" (+{len(pairs) - 6} more)" if len(pairs) > 6 else ""
    return f"{len(pairs)} z-fighting pair(s): {shown}{more}"
