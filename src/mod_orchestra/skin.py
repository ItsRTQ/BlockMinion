"""Deterministic skin painter and face-contrast check for box-UV GeckoLib mob models (pure stdlib).

The designer used to paint `models/<mob>.png` by hand, pixel by pixel, and the eyes, mouth and nose came out at one or two pixels
with no contrast. `paint_skin` builds the skin from the model itself instead: every cube's six faces are located with the box-UV
formulas, filled with the colour of the zone its bone belongs to, shaded by face direction, edged and lightly noised, and the head's
front face gets a face (brows, eyes with pupils, nose, mouth, optional tusks) whose colours are adjusted until they stand out from the
skin around them. The PNG is written at `scale` pixels per UV unit (2 = a 128x128 skin over a 64x64 layout), which is what lets the
face read in game. `face_report` measures how much the head's front face stands out, for any PNG, painted by this module or by hand.

Coordinates: UV units are the model's resolution; a cube of size (w, h, d) at uv_offset (u, v) occupies a (2d+2w) x (d+h) strip:
up [u+d, v, u+d+w, v+d], down [u+d+w, v, u+d+2w, v+d], east [u, v+d, u+d, v+d+h], north [u+d, v+d, u+d+w, v+d+h],
west [u+d+w, v+d, u+2d+w, v+d+h], south [u+2d+w, v+d, u+2d+2w, v+d+h]. North is the creature's front (it faces -Z).
"""
from __future__ import annotations

import fnmatch
import hashlib
import re
import struct
import zlib

from .validation import InputError

HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
FACE_SHADE = {"up": 1.12, "north": 1.0, "south": 0.94, "east": 0.88, "west": 0.88, "down": 0.70}
MAX_SCALE = 4


# ---------------------------------------------------------------------------------------------------------- colours

def parse_color(value, label: str = "colour") -> tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(c, int) and 0 <= c <= 255 for c in value):
        return tuple(value)
    m = HEX.match(str(value).strip())
    if not m:
        raise InputError(f"{label} must be a #RRGGBB hex colour, got {value!r}")
    h = m.group(1)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(c)))) for c in rgb)


def luminance(rgb) -> float:
    """Perceptual lightness 0..1 (Rec. 709 weights on the gamma-encoded values: cheap, monotone and good enough to rank contrast)."""
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


def mix(a, b, t: float):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def scale_color(rgb, f: float):
    return tuple(max(0.0, min(255.0, c * f)) for c in rgb)


def ensure_contrast(color, against, min_delta: float):
    """Push `color` toward white or black (whichever is farther from `against`) until the lightness differs by >= min_delta."""
    delta = luminance(color) - luminance(against)
    if abs(delta) >= min_delta:
        return tuple(color), False
    target = (255, 255, 255) if luminance(against) < 0.5 else (12, 8, 8)
    for step in range(1, 21):
        candidate = mix(color, target, step / 20)
        if abs(luminance(candidate) - luminance(against)) >= min_delta:
            return tuple(candidate), True
    return target, True


# ------------------------------------------------------------------------------------------------------------- PNG

def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    """8-bit grey, grey+alpha, RGB, RGBA and palette PNGs, non-interlaced -> (width, height, RGBA bytes). Raises ValueError otherwise."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, plte, width, height, depth, color, interlace = 8, [], None, 0, 0, 0, 0, 0
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    if depth != 8 or interlace != 0 or color not in (0, 2, 3, 4, 6) or not width or not height or width * height > 4096 * 4096:
        raise ValueError("unsupported PNG (need 8-bit, non-interlaced)")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    raw = zlib.decompress(b"".join(idat))
    stride = width * channels
    if len(raw) != (stride + 1) * height:
        raise ValueError("PNG data length mismatch")
    out, prev = bytearray(), bytearray(stride)
    for y in range(height):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            elif f != 0:
                raise ValueError("bad PNG filter")
        prev = line
        for x in range(width):
            px = line[x * channels:(x + 1) * channels]
            if color == 6:
                out += px
            elif color == 2:
                out += px + b"\xff"
            elif color == 0:
                out += bytes((px[0], px[0], px[0], 255))
            elif color == 4:
                out += bytes((px[0], px[0], px[0], px[1]))
            else:
                if plte is None or px[0] * 3 + 2 >= len(plte):
                    raise ValueError("bad palette index")
                out += plte[px[0] * 3:px[0] * 3 + 3] + b"\xff"
    return width, height, bytes(out)


# --------------------------------------------------------------------------------------------------- model geometry

def box_cubes(model: dict) -> list[dict]:
    """Box-UV cubes of a .bbmodel with the bone each belongs to: name, bone, w/h/d (floored, >= 1), u, v."""
    bone_of: dict[str, str] = {}
    groups = {g["uuid"]: g["name"] for g in model.get("groups", [])}

    def walk(nodes, bone):
        for n in nodes or []:
            if isinstance(n, str):
                bone_of[n] = bone
            else:
                walk(n.get("children"), groups.get(n.get("uuid"), bone))
    walk(model.get("outliner"), "")
    cubes = []
    for e in model.get("elements", []):
        if e.get("type") != "cube" or e.get("box_uv") is False or not isinstance(e.get("uv_offset"), list):
            continue
        w, h, d = (max(1, int(e["to"][i] - e["from"][i])) for i in (0, 1, 2))
        cubes.append({"name": e.get("name", ""), "bone": bone_of.get(e["uuid"], ""), "w": w, "h": h, "d": d, "u": e["uv_offset"][0], "v": e["uv_offset"][1]})
    return cubes


def face_rects(c: dict) -> dict[str, tuple[int, int, int, int]]:
    u, v, w, h, d = c["u"], c["v"], c["w"], c["h"], c["d"]
    return {"up": (u + d, v, u + d + w, v + d), "down": (u + d + w, v, u + d + 2 * w, v + d),
            "east": (u, v + d, u + d, v + d + h), "north": (u + d, v + d, u + d + w, v + d + h),
            "west": (u + d + w, v + d, u + 2 * d + w, v + d + h), "south": (u + 2 * d + w, v + d, u + 2 * d + 2 * w, v + d + h)}


def head_cube(cubes: list[dict]) -> dict | None:
    """The cube whose north face is the creature's face: the largest north face among the cubes of the bone called head."""
    heads = [c for c in cubes if c["bone"] == "head"]
    return max(heads, key=lambda c: c["w"] * c["h"]) if heads else None


# ------------------------------------------------------------------------------------------------------ face check

def face_report(model: dict, png: bytes) -> dict | None:
    """How much the head's front face stands out: lightness spread, share of feature pixels (those far from the median lightness) and
    how many separate features there are (two eyes and a mouth make three). None when there is nothing to judge."""
    resolution = model.get("resolution") or {}
    cube = head_cube(box_cubes(model))
    if not cube or not resolution.get("width"):
        return None
    try:
        width, height, rgba = decode_png(png)
    except (ValueError, zlib.error, struct.error):
        return None
    scale = width / resolution["width"]
    if scale < 1 or height != resolution["height"] * scale or scale != int(scale):
        return None
    scale = int(scale)
    x0, y0, x1, y1 = (c * scale for c in face_rects(cube)["north"])
    lum = []
    for y in range(y0, y1):
        row = []
        for x in range(x0, x1):
            i = (y * width + x) * 4
            row.append(luminance(rgba[i:i + 3]) if rgba[i + 3] > 20 else 0.0)
        lum.append(row)
    flat = sorted(v for row in lum for v in row)
    if not flat:
        return None
    median = flat[len(flat) // 2]
    spread = flat[int(len(flat) * 0.95) - 1] - flat[int(len(flat) * 0.05)]
    feature = [[abs(v - median) >= 0.20 for v in row] for row in lum]
    fh, fw = len(feature), len(feature[0])
    seen, clusters = set(), 0
    for sy in range(fh):
        for sx in range(fw):
            if not feature[sy][sx] or (sy, sx) in seen:
                continue
            stack, area = [(sy, sx)], 0
            seen.add((sy, sx))
            while stack:
                cy, cx = stack.pop(); area += 1
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < fh and 0 <= nx < fw and feature[ny][nx] and (ny, nx) not in seen:
                        seen.add((ny, nx)); stack.append((ny, nx))
            if area >= 2:
                clusters += 1
    fraction = sum(sum(r) for r in feature) / (fw * fh)
    ok = clusters >= 3 and 0.04 <= fraction <= 0.55 and spread >= 0.45
    flat_face = clusters < 2 or spread < 0.25 or fraction < 0.015
    return {"face_px": [fw, fh], "scale": scale, "spread": round(spread, 2), "feature_fraction": round(fraction, 3), "features": clusters, "ok": ok, "flat": flat_face,
            "advice": None if ok else ("the head's front face is nearly flat: eyes and mouth cannot be told from the skin; use orchestra_paint_skin (it paints "
                                       "them with guaranteed contrast) or paint features with a much lighter or darker colour than the skin" if flat_face else
                                       "the face is readable but weak: make the eyes brighter than the skin, the mouth and brows darker, and give each feature at least 2x2 pixels")}


# --------------------------------------------------------------------------------------------------------- painter

def _noise(seed: str, *key) -> float:
    """Deterministic value in [-1, 1] for a (seed, key) pair."""
    h = hashlib.blake2b(("|".join(map(str, (seed,) + key))).encode(), digest_size=4).digest()
    return int.from_bytes(h, "big") / 0x7FFFFFFF - 1.0


class Canvas:
    def __init__(self, width: int, height: int):
        self.w, self.h = width, height
        self.px = bytearray(width * height * 4)

    def set(self, x: int, y: int, rgb) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 4
            self.px[i:i + 4] = bytes((int(max(0, min(255, round(rgb[0])))), int(max(0, min(255, round(rgb[1])))), int(max(0, min(255, round(rgb[2])))), 255))

    def get(self, x: int, y: int):
        i = (y * self.w + x) * 4
        return tuple(self.px[i:i + 3])

    def rect(self, x0: int, y0: int, x1: int, y1: int, rgb) -> None:
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.set(x, y, rgb)


def _palette(palette: dict) -> dict[str, tuple]:
    if not isinstance(palette, dict) or "base" not in palette:
        raise InputError("palette needs at least a `base` colour, e.g. {\"base\": \"#4a6b3b\", \"cloth\": \"#6b3a22\", \"metal\": \"#3b3f42\"}")
    if len(palette) > 24:
        raise InputError("palette: at most 24 colours")
    return {str(k): parse_color(v, f"palette.{k}") for k, v in palette.items()}


def _zone_color(zones: list, pal: dict, bone: str):
    for z in zones:
        if any(fnmatch.fnmatchcase(bone, pat) for pat in z["bones"]):
            return z
    return None


def _resolve(pal: dict, value, label: str):
    return pal[value] if isinstance(value, str) and value in pal else parse_color(value, label)


def paint_skin(model: dict, *, palette: dict, zones: list | None = None, face: dict | None = None, scale: int = 2, seed: str = "") -> tuple[bytes, dict]:
    """Paint a skin for the model's box-UV cubes. Returns (PNG bytes, report).

    palette: {"base": "#hex", ...named colours}; zones: [{"bones": ["torso", "*_arm*"], "color": "cloth", "bands": {"color": "metal", "every": 4, "thickness": 1}}]
    (first matching zone wins, unmatched bones use `base`); face: {"eyes": "#hex", "pupil", "mouth", "brow", "teeth", "nose": true, "tusks": false, "style": "angry"|"calm"}."""
    if not isinstance(scale, int) or not 1 <= scale <= MAX_SCALE:
        raise InputError(f"scale must be an integer 1-{MAX_SCALE} (2 = a 128x128 skin over a 64x64 layout)")
    res = model.get("resolution") or {}
    rw, rh = int(res.get("width", 0)), int(res.get("height", 0))
    if not rw or not rh:
        raise InputError("the model has no resolution")
    pal = _palette(palette)
    zone_list = []
    for z in zones or []:
        if not isinstance(z, dict) or not isinstance(z.get("bones"), list) or "color" not in z:
            raise InputError("each zone needs `bones` (a list of names or * patterns) and `color`")
        zone_list.append({"bones": [str(b) for b in z["bones"]], "color": _resolve(pal, z["color"], "zone colour"),
                          "bands": z.get("bands")})
    cubes = box_cubes(model)
    if not cubes:
        raise InputError("the model has no box-UV cubes to paint")
    canvas = Canvas(rw * scale, rh * scale)
    base = pal["base"]
    for ci, c in enumerate(cubes):
        zone = _zone_color(zone_list, pal, c["bone"])
        color = zone["color"] if zone else base
        bands = zone["bands"] if zone else None
        band_color = _resolve(pal, bands["color"], "band colour") if bands else None
        for side, (ux0, uy0, ux1, uy1) in face_rects(c).items():
            shade = FACE_SHADE[side]
            x0, y0, x1, y1 = ux0 * scale, uy0 * scale, ux1 * scale, uy1 * scale
            for y in range(y0, y1):
                for x in range(x0, x1):
                    ux, uy = (x - x0) // scale, (y - y0) // scale
                    px_color = color
                    if bands and side in ("north", "south", "east", "west") and (uy % max(1, int(bands.get("every", 4)))) < max(1, int(bands.get("thickness", 1))):
                        px_color = band_color
                    n = _noise(seed, ci, side, ux, uy) * 0.055 + _noise(seed, ci, side, "fine", x, y) * 0.02
                    f = shade * (1.0 + n)
                    edge = min(x - x0, x1 - 1 - x, y - y0, y1 - 1 - y)
                    if edge == 0:
                        f *= 0.84
                    elif side in ("north", "south", "east", "west") and y - y0 < max(1, scale // 2) and edge > 0:
                        f *= 1.07          # a lit lip along the top of every side face
                    canvas.set(x, y, scale_color(px_color, f))
    report = {"size": [canvas.w, canvas.h], "scale": scale, "cubes": len(cubes), "zones": len(zone_list), "face": None, "adjusted": []}
    head = head_cube(cubes)
    if head and face is not False:
        report["face"], report["adjusted"] = _paint_face(canvas, head, pal, face or {}, scale, zone_list)
    png = encode_png(canvas.w, canvas.h, bytes(canvas.px))
    check = face_report({"resolution": res, "groups": model.get("groups"), "outliner": model.get("outliner"), "elements": model.get("elements")}, png)
    report["face_check"] = check
    return png, report


def _paint_face(canvas: Canvas, head: dict, pal: dict, face: dict, scale: int, zones: list):
    ux0, uy0, ux1, uy1 = face_rects(head)["north"]
    x0, y0, x1, y1 = ux0 * scale, uy0 * scale, ux1 * scale, uy1 * scale
    fw, fh = x1 - x0, y1 - y0
    zone = _zone_color(zones, pal, "head")
    skin = zone["color"] if zone else pal["base"]
    adjusted = []

    def pick(key, default, against, delta):
        raw = _resolve(pal, face[key], f"face.{key}") if key in face else parse_color(default)
        col, changed = ensure_contrast(raw, against, delta)
        if changed:
            adjusted.append(key)
        return col
    eyes = pick("eyes", "#ffd23f", skin, 0.45)
    dark = pick("mouth", "#140a0a", skin, 0.35)
    brow = pick("brow", "#140a0a", skin, 0.30)
    pupil = _resolve(pal, face["pupil"], "face.pupil") if "pupil" in face else (16, 8, 8)
    teeth = pick("teeth", "#ece4cf", dark, 0.45)
    style = face.get("style", "angry")
    if style not in ("angry", "calm"):
        raise InputError("face.style must be angry or calm")
    ew, eh = max(3, round(fw * 0.22)), max(2, round(fh * 0.15))
    ey = y0 + round(fh * 0.40) - eh // 2
    for side, cx in (("left", 0.28), ("right", 0.72)):
        ex = x0 + round(fw * cx) - ew // 2
        canvas.rect(ex - 1, ey - 1, ex + ew + 1, ey + eh + 1, scale_color(dark, 0.9))        # socket: a dark ring so the eye pops
        canvas.rect(ex, ey, ex + ew, ey + eh, eyes)
        px = ex + ew - max(1, scale // 2 + 1) if side == "left" else ex                       # pupils look toward the nose
        canvas.rect(px, ey, px + max(1, scale // 2 + 1), ey + eh, pupil)
        for i in range(ew + 2):                                                               # brow: one row, one step lower toward the nose when angry
            inner = (i > (ew + 1) // 2) if side == "left" else (i < (ew + 1) // 2)
            drop = 1 if style == "angry" and inner else 0
            canvas.rect(ex - 1 + i, ey - 2 + drop - (scale // 2 if scale > 1 else 0), ex + i, ey - 1 + drop, brow)
    if face.get("nose", True):
        ny, nw = y0 + round(fh * 0.60), max(1, scale // 2 + 1)
        for dx in (-scale, scale - nw + 1):
            canvas.rect(x0 + fw // 2 + dx - (0 if dx > 0 else nw - 1), ny, x0 + fw // 2 + dx + (nw if dx > 0 else 1), ny + max(2, scale + 1), scale_color(dark, 1.4))
    mw, mh = max(4, round(fw * 0.52)), max(2, round(fh * 0.10))
    mx, my = x0 + (fw - mw) // 2, y0 + round(fh * 0.76)
    canvas.rect(mx, my, mx + mw, my + mh, dark)
    for i in range(1, mw - 1, max(2, scale + 1)):                                             # teeth along the top edge of the mouth
        canvas.set(mx + i, my, teeth)
    if face.get("tusks"):
        for tx in (mx, mx + mw - max(1, scale // 2 + 1)):
            canvas.rect(tx, my - max(2, round(fh * 0.12)), tx + max(1, scale // 2 + 1), my + mh, teeth)
    return {"face_px": [fw, fh], "eyes": to_hex(eyes), "mouth": to_hex(dark), "style": style, "tusks": bool(face.get("tusks"))}, adjusted
