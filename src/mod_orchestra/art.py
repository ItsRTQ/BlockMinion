"""Art direction: the concept, visual cues (tags) and palette every entity is painted from.

Authored art (spec `art` fields, written by the interpreter from the idea and the theme, editable in the UI) always wins. Where it is missing,
`effective_art` derives a sheet from the mod's theme without calling any agent: the theme's phrases become tags (and its `#rrggbb` colours the
palette), pieces of one set share a few tags and each gets different ones of its own, and the kind adds its functional cues (blade, guard, grip).
A derived sheet is a floor, not creativity: the designer is told to turn the cues into a distinct shape and to treat the stock silhouette as forbidden.
"""
from __future__ import annotations

import hashlib
import re

from .spec import Spec, Art

HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
LEAD = re.compile(r"^(and|with|a|an|the|of|plus)\s+", re.I)
NOT_VISUAL = {"aesthetic", "mood", "style", "theme", "vibe", "feel", "feeling", "atmosphere", "tone", "overall"}   # describes a mood, not something to draw

# What a piece of this kind has to be (function, not style), so even a derived sheet says what to draw.
KIND_CUES = {
    "sword": ("blade", "guard", "grip"), "pickaxe": ("pick head", "haft"), "axe": ("axe bit", "haft"), "shovel": ("scoop blade", "haft"), "hoe": ("hooked blade", "haft"),
    "helmet": ("head guard", "face opening"), "chestplate": ("chest plate", "shoulder line"), "leggings": ("hip and thigh plates",), "boots": ("toe cap", "sole"),
    "gem": ("faceted crystal",), "ingot": ("bar with bevelled ends",), "food": ("something edible",), "block": ("a tileable surface",), "item": ("a handheld object",),
    "biped": ("upright body", "two arms"), "quadruped": ("four legs", "head on a neck"), "bird": ("beak", "wings"), "fish": ("fins", "tail"),
    "serpent": ("long body",), "insect": ("six legs", "segmented body"), "primate": ("long arms", "knuckle-walking", "hunched torso"),
}


def _clean(theme: str) -> str:
    return HEX.sub("", re.sub(r"\(\s*#[0-9a-fA-F]{6}\s*\)", "", theme or ""))


def theme_tags(theme: str) -> list[str]:
    """The theme's phrases as short lower-case tags, in order and without duplicates ("jagged edges", "leather straps", ...)."""
    tags, seen = [], set()
    for sentence in re.split(r"[;.\n:]", _clean(theme)):
        for part in re.split(r",|\bwith\b", sentence):
            phrase = LEAD.sub("", part.strip(" -–—()\"'")).strip().lower()
            phrase = re.sub(r"\s+", " ", phrase)
            if 2 <= len(phrase) <= 40 and len(phrase.split()) <= 5 and phrase not in seen and not (set(phrase.split()) & NOT_VISUAL):
                seen.add(phrase); tags.append(phrase)
    return tags


def theme_palette(theme: str) -> list[dict]:
    """[{name, hex}] for every `#rrggbb` in the theme, named by the words before it ("olive-green skin")."""
    out = []
    for segment in re.split(r"[,;.:\n]", theme or ""):
        for m in HEX.finditer(segment):
            name = LEAD.sub("", HEX.sub("", re.sub(r"[()]", " ", segment[:m.start()])).strip(" -–—\"'")).strip().lower()
            out.append({"name": re.sub(r"\s+", " ", name) or "colour", "hex": "#" + m.group(1).lower()})
    return out


def _pick(seed: str, items: list[str], n: int) -> list[str]:
    """A deterministic subset of n items, different for different seeds, in a stable order."""
    ranked = sorted(items, key=lambda t: hashlib.blake2b(f"{seed}|{t}".encode(), digest_size=4).digest())
    chosen = set(ranked[:n])
    return [t for t in items if t in chosen]


def _find(spec: Spec, kind: str, identifier: str):
    """(label, authored Art | None, cue key, piece Art-text | None, set Art | None) for an entity."""
    if kind == "mob":
        m = next((x for x in spec.mobs if x.identifier == identifier), None)
        return (m.label, m.art, m.body_plan, None, None) if m else None
    if kind == "food":
        f = next((x for x in spec.foods if x.identifier == identifier), None)
        return (f.label, f.art, "food", None, None) if f else None
    if kind in ("item", "block"):
        f = next((x for x in spec.features if x.identifier == identifier), None)
        return (f.label, f.art, f.shape or ("block" if f.kind == "block" else "item"), None, None) if f else None
    for mat in spec.materials:                       # tool / armor piece "<material>_<piece>", or the set itself
        if kind == "set" and mat.identifier == identifier:
            return mat.label, mat.art, "set", None, mat.art
        for piece in tuple(mat.tools) + tuple(mat.armor):
            if kind in ("tool", "armor") and f"{mat.identifier}_{piece}" == identifier:
                text = (mat.art.pieces.get(piece) if mat.art else None) or None
                return f"{mat.label} {piece}", mat.art, piece, text, mat.art
    return None


def effective_art(spec: Spec, kind: str, identifier: str) -> dict:
    """{concept, tags, silhouette, palette, source}: the authored art where there is some, derived from the theme where there is not.
    kind: item | block | tool | armor | food | mob | set (a whole tool/armor set)."""
    found = _find(spec, kind, identifier)
    if found is None:
        raise KeyError(f"unknown {kind} {identifier!r}")
    label, art, cue_key, piece_text, set_art = found
    theme = theme_tags(spec.theme)
    cues = KIND_CUES.get(cue_key, ())
    if art and art.tags:
        tags = list(art.tags)
    else:
        shared = theme[:3]                                                   # the set / the mod speaks with one voice...
        own = _pick(identifier, theme[3:] or theme, 3 if theme[3:] else 0)   # ...and each piece adds cues of its own
        tags = shared + [t for t in own if t not in shared]
    authored_concept = piece_text or (art.concept if art and art.concept else "")
    concept = authored_concept or (f"{label}: " + (f"{', '.join(cues)}; " if cues else "") + (f"showing {', '.join(tags[:4])}" if tags else "designed to fit this mod")).strip()
    return {"concept": concept, "tags": tags, "silhouette": art.silhouette if art else "", "palette": theme_palette(spec.theme),
            "source": "authored" if authored_concept or (art and art.tags) else "derived", "cues": list(cues)}


def brief(spec: Spec, kind: str, identifier: str, *, palette: bool = True) -> str:
    """The art direction of one entity as prompt text."""
    a = effective_art(spec, kind, identifier)
    lines = [f"concept: {a['concept']}"]
    if a["tags"]:
        lines.append("visual cues: " + ", ".join(a["tags"]))
    if a["silhouette"]:
        lines.append(f"silhouette: {a['silhouette']}")
    if palette and a["palette"]:
        lines.append("palette: " + "; ".join(f"{p['name']} {p['hex']}" for p in a["palette"]))
    return "\n".join(lines)
