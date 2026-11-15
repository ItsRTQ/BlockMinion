"""What exists in the mod beyond the spec: content a coder made (a projectile, an effect, a particle, a screen, an extra item),
and content that is simply in the code without the tool knowing where it came from.

Two sources, one registry (project setting `made_content`, so it does not depend on how long ago something happened):

- DECLARED: a coder's handoff said so. `art_needed` names each visible thing with its kind and what it is; a feature card's
  `produces` names ids. Recorded when the handoff is applied, and back-filled once from every past event and card.
- FOUND: `inventory` reads the source and lists what is registered in the game's registries, with file and line. Compared
  with what the generator itself registers for the current spec (generated fresh in a temporary folder and read the same way)
  and with what is already known, what is left is in the code and tracked by nothing. The user adopts it (it becomes a card)
  or says to ignore it. Nothing is adopted without the user: reading code with patterns can miss things, and it must not
  invent them. It reports only registrations whose registry AND literal id it can read.

Each entry becomes a card of the mod map (`cards`), linked to the feature that made it, so it can be seen, pointed at from
the chat and changed like anything else. `inventory` knows nothing about this tool's projects: it reads any Fabric mod's
source (Mojang mappings), which is the first piece of mapping a mod that was not made here.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

SETTING = "made_content"
ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
# What a card of made content can be. `content` is "something registered, of a kind the map has no name for".
KINDS = ("projectile", "effect", "particle", "entity", "gui", "sound", "made_item", "made_block", "content")
FROM_ART = {"item": "made_item", "projectile": "projectile", "effect_icon": "effect", "particle": "particle", "entity": "entity", "block": "made_block", "gui": "gui", "other": "content"}
FROM_REGISTRY = {"ENTITY_TYPE": "entity", "MOB_EFFECT": "effect", "PARTICLE_TYPE": "particle", "SOUND_EVENT": "sound", "MENU": "gui", "BLOCK": "made_block", "ITEM": "made_item"}
PRIORITY = ("ENTITY_TYPE", "MOB_EFFECT", "PARTICLE_TYPE", "MENU", "BLOCK", "ITEM", "SOUND_EVENT")   # one id in several registries: the first names what it is


def _empty() -> dict:
    return {"entries": {}, "ignored": [], "backfilled": False}


def _save(store: Store, pid: str, reg: dict) -> None:
    with store.tx() as con:   # written directly: a setting change is copied whole into an event
        con.execute("INSERT OR REPLACE INTO project_settings(project_id, key, value_json) VALUES(?,?,?)", (pid, SETTING, json.dumps(reg)))


def _put(reg: dict, cid: str, **fields) -> bool:
    """Add or complete one entry. What a coder declared later never erases what is known: empty values do not overwrite."""
    if not isinstance(cid, str) or not ID.match(cid):
        return False
    cur = reg["entries"].get(cid)
    new = dict(cur or {"id": cid, "kind": "content", "what": "", "card": None, "path": None, "for": [], "source": "declared", "files": []})
    for k, v in fields.items():
        if v in (None, "", []):
            continue
        if k == "kind" and (v not in KINDS or (cur and cur.get("kind") != "content" and v == "content")):
            continue   # a known kind is not replaced by "content"
        new[k] = v
    changed = new != cur
    reg["entries"][cid] = new
    return changed


def load(store: Store, pid: str) -> dict:
    """The registry, back-filled once from everything the project's history says a coder made."""
    raw = store.get_setting(pid, SETTING, None)
    reg = _empty() | raw if isinstance(raw, dict) and isinstance(raw.get("entries"), dict) else _empty()
    if reg["backfilled"]:
        return reg
    from .modmap import custom_cards
    for e in store.events_of(pid, "ART_REQUESTED"):
        for a in e["payload"].get("assets", []):
            if isinstance(a, dict):
                _put(reg, a.get("id"), kind=FROM_ART.get(a.get("kind"), "content"), what=str(a.get("what") or "")[:300], card=e["payload"].get("card"), path=a.get("path"),
                     **{"for": [f for f in (a.get("for") or []) if isinstance(f, str)][:12]})
    for card in custom_cards(store, pid).values():
        for cid in card.get("produces") or []:
            _put(reg, cid, card=card["id"])
    reg["backfilled"] = True
    _save(store, pid, reg)
    return reg


def record_art(store: Store, pid: str, card: str | None, assets: list[dict]) -> None:
    """A coder declared visible things it made (`art_needed`)."""
    reg = load(store, pid); changed = False
    for a in assets:
        changed |= _put(reg, a.get("id"), kind=FROM_ART.get(a.get("kind"), "content"), what=str(a.get("what") or "")[:300], card=card, path=a.get("path"),
                        **{"for": [f for f in (a.get("for") or []) if isinstance(f, str)][:12]})
    if changed:
        _save(store, pid, reg)


def record_produces(store: Store, pid: str, card: str, ids: list[str]) -> None:
    """A coder said a feature card produces these ids."""
    reg = load(store, pid); changed = False
    for cid in ids:
        changed |= _put(reg, cid, card=card)
    if changed:
        _save(store, pid, reg)


def entries(store: Store, pid: str) -> dict[str, dict]:
    return load(store, pid)["entries"]


def _title(cid: str) -> str:
    return cid.replace("_", " ").capitalize()


def cards(store: Store, pid: str, known: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Map cards and edges for made content that is not already a card. `known`: the cards the map has so far."""
    out, edges = [], []
    for cid, e in entries(store, pid).items():
        if cid in known:
            continue   # the spec (or a feature) already has a card with this id: it is that thing
        parent = e.get("card") if e.get("card") in known else None
        files = [f for f in [e.get("path")] + list(e.get("files") or []) if f]
        out.append({"id": cid, "kind": e["kind"], "title": _title(cid), "description": e.get("what") or "", "owner": "coder", "files": files, "made": {"source": e["source"], "feature": parent, "registry": e.get("registry")},
                    "status": (known[parent].get("status") if parent else None) or "generated"})
        if parent:
            edges.append({"from": parent, "to": cid, "kind": "makes"})
        for owner in e.get("for") or []:
            if owner in known and owner != parent:
                edges.append({"from": owner, "to": cid, "kind": "uses"})
    return out, edges


# ---------- reading the source ----------
_REGISTER = re.compile(r"\bRegistry\s*\.\s*register(?:ForHolder|Reference)?\s*\(\s*(?:BuiltInRegistries|Registries)\s*\.\s*([A-Z_]+)\s*,")
_LITERAL = re.compile(r'"((?:[a-z0-9_.\-]+:)?[a-z0-9_./\-]+)"')
_HELPER = re.compile(r"\b([A-Za-z_]\w*)\s*\(\s*(?:final\s+)?String\s+([A-Za-z_]\w*)\b[^)]*\)\s*(?:throws\s+[\w., ]+)?\{")


def _blank_comments(src: str) -> str:
    """The source with comments and text blocks blanked (same length, same lines), so commented-out code is not read."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    src = re.sub(r'"""[\s\S]*?"""', blank, src)
    src = re.sub(r"/\*[\s\S]*?\*/", blank, src)
    return re.sub(r"//[^\n]*", blank, src)


def _argument(src: str, start: int) -> str:
    """The argument that begins at `start`, up to the comma or parenthesis that ends it (nested parentheses respected)."""
    depth, i, quote = 0, start, False
    while i < len(src) and i - start < 400:
        ch = src[i]
        if ch == '"' and src[i - 1] != "\\":
            quote = not quote
        elif not quote:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                break
        i += 1
    return src[start:i]


def _body(src: str, open_brace: int) -> str:
    depth, i = 0, open_brace
    while i < len(src) and i - open_brace < 4000:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return src[open_brace:i]


def _own_id(literals: list[str], mod_id: str | None) -> str | None:
    """The id an expression names, when it is this mod's: `id("x")`, `fromNamespaceAndPath(MOD_ID, "x")`, `"mod:x"`, `("mod", "x")`."""
    if not literals:
        return None
    last = literals[-1]
    ns, _, path = last.rpartition(":")
    if not ns and len(literals) >= 2 and re.fullmatch(r"[a-z0-9_.\-]+", literals[-2]):
        ns = literals[-2]   # ("namespace", "path")
    if ns and mod_id and ns != mod_id:
        return None       # someone else's id (a vanilla override, another mod)
    return path if re.fullmatch(r"[a-z0-9_]+(?:/[a-z0-9_]+)*", path) else None


def inventory(root: Path, mod_id: str | None = None) -> list[dict]:
    """What the Java source registers in the game's registries: [{registry, id, file, line}], for any Fabric mod (Mojang mappings).
    Only registrations whose registry and literal id can both be read are reported; ids of another namespace are left out."""
    out, seen = [], set()
    src_root = root / "src"
    for path in sorted(src_root.rglob("*.java")) if src_root.is_dir() else []:
        try:
            src = _blank_comments(path.read_text(encoding="utf8", errors="replace"))
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        line = lambda pos: src.count("\n", 0, pos) + 1
        helpers: dict[str, str] = {}
        for m in _HELPER.finditer(src):    # a helper that registers by name: `register(String name, ...) { Registry.register(BuiltInRegistries.X, id(name), ...) }`
            body = _body(src, m.end() - 1)
            r = _REGISTER.search(body)
            if not r:
                continue
            id_arg, name = _argument(body, r.end()), re.escape(m.group(2))
            # the id it registers must come from that String: used directly, or through a local built from it (`ResourceLocation rl = id(name)`)
            words = re.findall(r"[A-Za-z_]\w*", id_arg)
            if not _LITERAL.search(id_arg) and (m.group(2) in words or any(re.search(rf"\b{re.escape(w)}\s*=[^;=]*\b{name}\b", body[:r.start()]) for w in words)):
                helpers[m.group(1)] = r.group(1)
        found = []
        for m in _REGISTER.finditer(src):
            id_arg = _argument(src, m.end())
            cid = None if "withDefaultNamespace" in id_arg else _own_id(_LITERAL.findall(id_arg), mod_id)   # the default namespace is the game's, not the mod's
            if cid:
                found.append((m.group(1), cid, m.start()))
        for name, registry in helpers.items():
            for m in re.finditer(rf'(?<![\w.]){re.escape(name)}\s*\(\s*"([a-z0-9_]+(?:/[a-z0-9_]+)*)"', src):
                found.append((registry, m.group(1), m.start()))
        for registry, cid, pos in found:
            if (registry, cid, rel) not in seen:
                seen.add((registry, cid, rel)); out.append({"registry": registry, "id": cid, "file": rel, "line": line(pos)})
    return out


def _baseline(store: Store, pid: str) -> set[tuple[str, str]]:
    """What the generator itself registers for the current spec: the project generated fresh in a temporary folder, read the same way."""
    from . import fabric
    from .spec import read_spec
    proj = store.project(pid)
    with tempfile.TemporaryDirectory(prefix="bm-baseline-") as tmp:
        target = Path(tmp) / "mod"
        fabric._generate_into(read_spec(proj["spec"]), target)
        return {(x["registry"], x["id"]) for x in inventory(target, proj["spec"].get("mod_id") or pid)}


def scan(store: Store, pid: str) -> dict:
    """What is registered in the mod's code and tracked by nothing: not generated from the spec, not declared by a coder, not adopted,
    not ignored. One entry per id, with every place it is registered and a guess of what it is and which feature's files hold it."""
    proj = store.project(pid); root = Path(proj["root"])
    if not (root / "src").is_dir():
        raise StateError("Generate the project first")
    try:
        base = _baseline(store, pid)
    except Exception as exc:   # without a baseline the tool's own content would be listed as unknown: say so instead of guessing
        raise StateError(f"Could not work out what the generator itself registers ({type(exc).__name__}: {str(exc)[:160]}); nothing was listed")
    reg = load(store, pid); tracked = set(reg["entries"]); ignored = set(reg["ignored"])
    from .modmap import custom_cards, mod_map
    known_cards = {c["id"] for c in mod_map(store, pid)["cards"]}
    by_file = {}
    for card in custom_cards(store, pid).values():
        for f in card.get("files") or []:
            by_file.setdefault(f, card["id"])
    found: dict[str, dict] = {}
    everything = inventory(root, proj["spec"].get("mod_id") or pid)
    for x in everything:
        if (x["registry"], x["id"]) in base or x["id"] in tracked or x["id"] in ignored or x["id"] in known_cards:
            continue
        e = found.setdefault(x["id"], {"id": x["id"], "registries": [], "places": [], "feature": None})
        if x["registry"] not in e["registries"]:
            e["registries"].append(x["registry"])
        e["places"].append({"registry": x["registry"], "file": x["file"], "line": x["line"]})
        e["feature"] = e["feature"] or by_file.get(x["file"])
    for e in found.values():
        first = next((r for r in PRIORITY if r in e["registries"]), e["registries"][0])
        e["kind"] = FROM_REGISTRY.get(first, "content"); e["registry"] = first
    store.add_event(pid, "user", "MADE_SCANNED", {"registered": len(everything), "untracked": len(found)})
    return {"untracked": sorted(found.values(), key=lambda e: e["id"]), "registered": len(everything), "generated": len(base), "tracked": len(tracked), "ignored": sorted(ignored)}


def adopt(store: Store, pid: str, cid: str, *, kind: str | None = None, card: str | None = None, what: str = "") -> dict:
    """USER-ONLY: this thing found in the code is part of the mod: track it (it becomes a card)."""
    if not ID.match(cid or ""):
        raise InputError("Not a content id")
    from .modmap import custom_cards, mod_map
    if cid in {c["id"] for c in mod_map(store, pid)["cards"]} and cid not in entries(store, pid):
        raise InputError(f"{cid!r} is already a card of the mod")
    if card and card not in custom_cards(store, pid):
        raise InputError(f"No feature card {card!r}")
    if kind and kind not in KINDS:
        raise InputError("kind must be one of " + ", ".join(KINDS))
    proj = store.project(pid); root = Path(proj["root"])
    places = [x for x in inventory(root, proj["spec"].get("mod_id") or pid) if x["id"] == cid]
    if not places:
        raise InputError(f"Nothing registered as {cid!r} was found in the code")
    first = next((r for r in PRIORITY if any(x["registry"] == r for x in places)), places[0]["registry"])
    reg = load(store, pid)
    _put(reg, cid, kind=kind or FROM_REGISTRY.get(first, "content"), what=" ".join(str(what).split())[:300], card=card, source="found", registry=first,
         files=list(dict.fromkeys(x["file"] for x in places))[:12])
    reg["entries"][cid]["source"] = reg["entries"][cid].get("source") or "found"
    reg["ignored"] = [i for i in reg["ignored"] if i != cid]
    _save(store, pid, reg)
    store.add_event(pid, "user", "MADE_ADOPTED", {"id": cid, "kind": reg["entries"][cid]["kind"], "card": card})
    return reg["entries"][cid]


def ignore(store: Store, pid: str, cid: str, ignored: bool = True) -> dict:
    """USER-ONLY: do not list this id as untracked again (or list it again)."""
    if not ID.match(cid or ""):
        raise InputError("Not a content id")
    reg = load(store, pid)
    reg["ignored"] = sorted((set(reg["ignored"]) | {cid}) if ignored else (set(reg["ignored"]) - {cid}))
    _save(store, pid, reg)
    store.add_event(pid, "user", "MADE_IGNORED" if ignored else "MADE_UNIGNORED", {"id": cid})
    return {"ignored": reg["ignored"]}


def view(store: Store, pid: str) -> dict:
    reg = load(store, pid)
    return {"entries": sorted(reg["entries"].values(), key=lambda e: e["id"]), "ignored": reg["ignored"], "kinds": list(KINDS)}
