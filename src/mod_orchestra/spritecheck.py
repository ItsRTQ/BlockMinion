"""Creative gates for 16x16 item sprites: a sprite must not be the stock template of its kind, must not be another piece of the batch repainted,
and must use enough colours for the art direction to show. The designer runs the same checks through `orchestra_check_sprites` before it finishes;
`install_sprites` runs them again and rejects what fails, so a generic icon never reaches the mod.
"""
from __future__ import annotations

import struct
import zlib

from . import skin
from .art import effective_art
from .spec import Spec
from .textures import ITEM_MASKS

STOCK_IOU = 0.85      # silhouette overlap with the generator's own template above which a sprite counts as the template
PAIR_SAME = 0.85      # share of identical pixels between two sprites of a batch above which one is a copy of the other
MIN_COLOURS = 4


def catalogue(spec: Spec) -> dict[str, dict]:
    """identifier -> {mask, art_kind}: every sprite-bearing item of the spec and the placeholder silhouette the generator gives it."""
    out: dict[str, dict] = {}
    for f in spec.features:
        out[f.identifier] = {"mask": f.shape or ("block" if f.kind == "block" else "gem"), "art_kind": f.kind}
    for m in spec.materials:
        for k in m.tools:
            out[f"{m.identifier}_{k}"] = {"mask": k, "art_kind": "tool"}
        for k in m.armor:
            out[f"{m.identifier}_{k}"] = {"mask": "ingot" if k in ("chestplate", "leggings") else "gem", "art_kind": "armor"}
    for fd in spec.foods:
        out[fd.identifier] = {"mask": "food", "art_kind": "food"}
    return out


def template_alpha(mask: str) -> list[bool]:
    rows = ITEM_MASKS.get(mask)
    return [ch != "." for row in rows for ch in row] if rows else []


def read_sprite(png: bytes):
    """(alpha 256 bools, rgb per opaque pixel, colour count) for a 16x16 PNG, or None when it cannot be read."""
    try:
        w, h, rgba = skin.decode_png(png)
    except (ValueError, zlib.error, struct.error):
        return None
    if (w, h) != (16, 16):
        return None
    alpha, rgb, colours = [], [], set()
    for i in range(256):
        r, g, b, a = rgba[i * 4:i * 4 + 4]
        alpha.append(a >= 128)
        rgb.append((r, g, b) if a >= 128 else None)
        if a >= 128:
            colours.add((r, g, b))
    return alpha, rgb, len(colours)


def iou(a: list[bool], b: list[bool]) -> float:
    inter = sum(1 for x, y in zip(a, b) if x and y)
    union = sum(1 for x, y in zip(a, b) if x or y)
    return inter / union if union else 1.0


def same_share(p, q, tol: int = 24) -> float:
    """Share of the pixels opaque in either sprite that are opaque in both with nearly the same colour."""
    both = union = 0
    for x, y in zip(p, q):
        if x is None and y is None:
            continue
        union += 1
        if x is not None and y is not None and max(abs(x[i] - y[i]) for i in range(3)) <= tol:
            both += 1
    return both / union if union else 1.0


def check_sprites(spec: Spec, sprites: dict[str, bytes]) -> dict[str, str]:
    """identifier -> why it is rejected, for the sprites that fail; the others are fine. Sprites whose identifier is not in the spec are ignored."""
    cat = catalogue(spec)
    read = {ident: read_sprite(raw) for ident, raw in sprites.items() if ident in cat}
    rejected: dict[str, str] = {}
    for ident in sorted(read):
        info = read[ident]
        if info is None:
            continue                                   # not a readable 16x16 PNG: install_sprites reports that on its own
        alpha, _, colours = info
        art = effective_art(spec, cat[ident]["art_kind"], ident)
        cues = ", ".join(art["tags"][:3]) or "the concept"
        mask = cat[ident]["mask"]
        if colours < MIN_COLOURS:
            rejected[ident] = f"only {colours} colours; paint {MIN_COLOURS}-8 so the art direction ({cues}) can be seen"
            continue
        tpl = template_alpha(mask)
        if mask != "block" and tpl:
            overlap = iou(alpha, tpl)
            if overlap >= STOCK_IOU:
                rejected[ident] = (f"its silhouette is {overlap:.0%} the stock {mask} template; invent a shape of its own that carries the art direction "
                                   f"({cues}{'; silhouette: ' + art['silhouette'] if art['silhouette'] else ''})")
    names = [i for i in sorted(read) if read[i] is not None and i not in rejected]
    for n, ident in enumerate(names):
        for other in names[:n]:
            if other in rejected:
                continue
            share = same_share(read[ident][1], read[other][1])
            if share >= PAIR_SAME:
                rejected[ident] = f"{share:.0%} the same pixels as {other}; every piece needs its own silhouette and details, sharing only palette and motifs"
                break
    return rejected
