"""Deterministic tinted textures for tool/armor sets and simple items — stdlib only, no Mojang assets.

Silhouettes are our own 16x16 pixel masks (sword, pickaxe, axe, shovel, hoe, gem, ingot, food) and
our own armor-layer masks on the 64x32 player-model layout (helmet/chestplate/boots on layer 1,
leggings on layer 2). Each mask cell is a shade: 0 transparent, 1 outline, 2 shadow, 3 base,
4 highlight, 5 handle/wood. Colours come from the material (base + accent) and handles are brown.
"""
from __future__ import annotations
import hashlib
import struct
import zlib

# ---- 16x16 masks: rows of 16 chars; '.' transparent ----
SWORD = [
    "..............13", ".............134", "............1343", "...........1343.", "..........1343..", ".........1343...", "........1343....",
    ".......1343.....", "..2...1343......", "...2.1343.......", "....2343........", ".....22.........", "....522.........", "...56.2.........",
    "..56............", ".56.............",
]
PICKAXE = [
    "................", "......12222.....", "....12344432....", "...1344333432...", "..13433...1343..", "..1343....1343..", "..134......13...",
    "..13...5........", "......56........", ".....56.........", "....56..........", "...56...........", "..56............", ".56.............",
    "56..............", "................",
]
AXE = [
    "................", "......1221......", ".....134432.....", "....13444432....", "....13444432....", "....13444432....", "....1343332.....",
    ".....13365......", "......156.......", ".....56.........", "....56..........", "...56...........", "..56............", ".56.............",
    "56..............", "................",
]
SHOVEL = [
    "................", "........12221...", ".......134432...", ".......134432...", ".......134432...", ".......133332...", "........1565....",
    ".........56.....", "........56......", ".......56.......", "......56........", ".....56.........", "....56..........", "...56...........",
    "..56............", ".56.............",
]
HOE = [
    "................", "......122221....", ".....13444321...", ".....12333321...", "......11..56....", ".........56.....", "........56......",
    ".......56.......", "......56........", ".....56.........", "....56..........", "...56...........", "..56............", ".56.............",
    "56..............", "................",
]
GEM = [
    "................", "................", "......1111......", ".....144431.....", "....14444431....", "...1444333331...", "...1443333321...",
    "...1433333221...", "....13332221....", ".....132221.....", "......1221......", ".......11.......", "................", "................",
    "................", "................",
]
INGOT = [
    "................", "................", "................", "................", "....11111111....", "...14444443331..", "..1444433333321.",
    ".13333333333221.", ".13333322222221.", ".12222222222221.", "..111111111111..", "................", "................", "................",
    "................", "................",
]
FOOD = [
    "................", "................", ".......55.......", "......5.........", "....1111111.....", "...144443331....", "..14444333331...",
    "..14443333321...", "..13333333221...", "..13333322221...", "...1332222221...", "....11222211....", ".....111111.....", "................",
    "................", "................",
]
BLOCK = [
    "3333333333333333", "3444444444444443", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343",
    "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343",
    "3222222222222223", "3333333333333333",
]
ITEM_MASKS = {"sword": SWORD, "pickaxe": PICKAXE, "axe": AXE, "shovel": SHOVEL, "hoe": HOE, "gem": GEM, "ingot": INGOT, "food": FOOD, "block": BLOCK}


def material_colors(identifier: str, color: str | None = None, accent: str | None = None) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Base and accent RGB. Explicit hex wins; otherwise a stable hue from the identifier."""
    if color:
        base = _hex(color)
    else:
        d = hashlib.sha256(identifier.encode()).digest()
        base = _hsv(d[0] / 255, 0.55 + d[1] / 255 * 0.3, 0.55 + d[2] / 255 * 0.3)
    acc = _hex(accent) if accent else _lighten(base, 0.35)
    return base, acc


def _hex(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6) % 6; f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
    return int(r * 255), int(g * 255), int(b * 255)


def _lighten(c, k):
    return tuple(min(255, int(x + (255 - x) * k)) for x in c)


def _darken(c, k):
    return tuple(max(0, int(x * (1 - k))) for x in c)


def shade_palette(base, accent) -> dict[str, tuple]:
    return {"1": (*_darken(base, 0.65), 255), "2": (*_darken(base, 0.3), 255), "3": (*base, 255), "4": (*accent, 255), "5": (92, 64, 36, 255), "6": (120, 86, 50, 255)}


def png_from_pixels(width: int, height: int, pixels: list[list[tuple]]) -> bytes:
    rows = []
    for y in range(height):
        rows.append(b"\x00" + b"".join(bytes(px) for px in pixels[y]))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


def tinted_item_png(mask_name: str, base, accent) -> bytes:
    mask = ITEM_MASKS[mask_name]
    pal = shade_palette(base, accent)
    pixels = [[pal.get(ch, (0, 0, 0, 0)) for ch in row.ljust(16, ".")] for row in mask]
    return png_from_pixels(16, 16, pixels)


# ---- armor layers (64x32, classic player-model layout) ----
# Each body part is a cube net: top, bottom, right, front, left, back faces. Faces are shaded separately so the
# worn armor reads as a shape, and the helmet leaves the face open like vanilla helmets do.
def _cube_net(x, y, w, h, d):
    """Face boxes (x0, y0, width, height) of a cube net whose top-left is (x, y): size w×h×d."""
    return {"top": (x + d, y, w, d), "bottom": (x + d + w, y, w, d), "right": (x, y + d, d, h), "front": (x + d, y + d, w, h),
            "left": (x + d + w, y + d, d, h), "back": (x + 2 * d + w, y + d, w, h)}


HEAD_NET = _cube_net(0, 0, 8, 8, 8)
BODY_NET = _cube_net(16, 16, 8, 12, 4)
ARM_NET = _cube_net(40, 16, 4, 12, 4)
LEG_NET = _cube_net(0, 16, 4, 12, 4)
FACE_SHADE = {"top": "4", "front": "3", "left": "3", "right": "3", "back": "3", "bottom": "2"}


def armor_layer_png(layer: int, base, accent, pieces: tuple) -> bytes:
    pal = shade_palette(base, accent)
    px = [[(0, 0, 0, 0)] * 64 for _ in range(32)]

    def fill_face(box, shade, rows=None, cols=None, cutout=None):
        x0, y0, w, h = box
        for y in range(y0, y0 + h):
            if rows and not (rows[0] <= y - y0 <= rows[1]):
                continue
            for x in range(x0, x0 + w):
                if cols and not (cols[0] <= x - x0 <= cols[1]):
                    continue
                if cutout and cutout[0] <= x - x0 <= cutout[1] and cutout[2] <= y - y0 <= cutout[3]:
                    continue
                sh = shade
                if y == y0 or x == x0 or y == y0 + h - 1 or x == x0 + w - 1:
                    sh = "1" if sh != "4" else "2"   # outline on every face edge
                px[y][x] = pal[sh]

    def fill_cube(net, rows=None, cutout_front=None):
        for face, box in net.items():
            fill_face(box, FACE_SHADE[face], rows=rows if face not in ("top", "bottom") else None, cutout=cutout_front if face == "front" else None)

    if layer == 1:
        if "helmet" in pieces:
            fill_cube(HEAD_NET, cutout_front=(1, 6, 3, 7))         # open visor: eyes and mouth stay visible
        if "chestplate" in pieces:
            fill_cube(BODY_NET); fill_cube(ARM_NET)
            fx, fy, fw, fh = BODY_NET["front"]
            for x in range(fx + 1, fx + fw - 1): px[fy + 6][x] = pal["4"]   # belt / trim line
        if "boots" in pieces:
            fill_cube(LEG_NET, rows=(8, 11))
    else:
        if "leggings" in pieces:
            fill_cube(BODY_NET, rows=(6, 11))
            fill_cube(LEG_NET, rows=(0, 9))
    return png_from_pixels(64, 32, px)


def palette_from_png(raw: bytes) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """(base, accent) taken from an RGBA PNG: the most common mid-tone opaque colour and the lightest frequent one.
    Lets worn armor match a designer- or user-painted icon. stdlib only."""
    import struct as _s, zlib as _z
    from collections import Counter
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    w, h, depth, ctype = _s.unpack(">IIBB", raw[16:26])
    if depth != 8 or ctype not in (2, 6):
        return None
    pos, idat = 8, b""
    while pos < len(raw):
        ln = _s.unpack(">I", raw[pos:pos + 4])[0]; kind = raw[pos + 4:pos + 8]
        if kind == b"IDAT": idat += raw[pos + 8:pos + 8 + ln]
        pos += 12 + ln
    px = _z.decompress(idat); bpp = 4 if ctype == 6 else 3; stride = w * bpp + 1
    counts: Counter = Counter()
    prev = bytearray(w * bpp)
    for y in range(h):
        f = px[y * stride]; row = bytearray(px[y * stride + 1:(y + 1) * stride])
        for i in range(len(row)):   # PNG unfilter (None/Sub/Up/Average/Paeth)
            a = row[i - bpp] if i >= bpp else 0; b = prev[i]; c = prev[i - bpp] if i >= bpp else 0
            if f == 1: row[i] = (row[i] + a) & 255
            elif f == 2: row[i] = (row[i] + b) & 255
            elif f == 3: row[i] = (row[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = row
        for x in range(w):
            p = row[x * bpp:(x + 1) * bpp]
            if bpp == 4 and p[3] < 128:
                continue
            counts[(p[0], p[1], p[2])] += 1
    if not counts:
        return None
    lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    common = [c for c, _ in counts.most_common(8)]
    mids = sorted(common, key=lambda c: abs(lum(c) - 128))
    base = mids[0]
    lights = [c for c in common if lum(c) > lum(base) + 25]
    accent = max(lights, key=lum) if lights else _lighten(base, 0.35)
    return base, accent
