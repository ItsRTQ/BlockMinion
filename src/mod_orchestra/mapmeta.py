"""Mod Map 2.0: how the USER organises the map (folders, memberships, tags, positions, view preferences).

This is view metadata. It lives in one project setting (`map_meta`), apart from the spec, the feature cards and the mod's source,
and nothing here is read by `modmap.map_text`, `request_change` or any agent brief: a folder's name or a tag is never an instruction.
Moving a card between folders, deleting a folder or tagging a card changes this document only; no file of the mod is touched.

The document is saved whole by the UI (`POST map-meta`) and normalised here, so what is stored is always consistent:
no folder cycles, no membership of a folder that does not exist, no duplicate tags.
"""
from __future__ import annotations

import json
import re

from .state import Store, StateError
from .validation import InputError

SETTING = "map_meta"
VERSION = 1
MODES = ("auto", "suggest", "manual")
VIRTUAL = "auto:"            # ids of the automatic groups the UI shows for cards the user has not filed (never stored as folders)
MAX_FOLDERS = 2000
MAX_DEPTH = 12
MAX_NAME = 60
MAX_TAG = 32
MAX_TAGS_PER_CARD = 24
MAX_RULE_VALUES = 24
MAX_BYTES = 2_000_000
_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")
_SPACE = re.compile(r"\s+")


def empty() -> dict:
    return {"version": VERSION, "folders": {}, "members": {}, "excluded": {}, "tags": {}, "fpos": {}, "pos": {}, "prefs": {}}


def clean_tag(tag) -> str:
    """One spelling per tag: trimmed, inner spaces collapsed, capped. Comparison is case-insensitive (`tag_key`)."""
    return _SPACE.sub(" ", str(tag)).strip()[:MAX_TAG].strip()


def tag_key(tag) -> str:
    return clean_tag(tag).casefold()


def _tags(values) -> list[str]:
    out, seen = [], set()
    for v in values if isinstance(values, list) else []:
        t = clean_tag(v)
        if t and tag_key(t) not in seen:
            seen.add(tag_key(t)); out.append(t)
    return out[:MAX_TAGS_PER_CARD]


def _xy(v) -> dict | None:
    if isinstance(v, dict) and all(isinstance(v.get(k), (int, float)) and not isinstance(v.get(k), bool) and abs(v[k]) < 1e7 for k in ("x", "y")):
        return {"x": round(float(v["x"]), 1), "y": round(float(v["y"]), 1)}
    return None


def _folder_ok(fid: str, folders: dict) -> bool:
    return fid in folders or (isinstance(fid, str) and fid.startswith(VIRTUAL) and len(fid) <= 80)


def normalize(raw) -> dict:
    """The stored shape of whatever the UI sent. Refuses what would corrupt the hierarchy; drops what merely dangles."""
    if not isinstance(raw, dict):
        raise InputError("The map organisation must be an object")
    if len(json.dumps(raw)) > MAX_BYTES:
        raise InputError("The map organisation is too large")
    out = empty()
    src = raw.get("folders") or {}
    if not isinstance(src, dict):
        raise InputError("folders must be an object keyed by folder id")
    if len(src) > MAX_FOLDERS:
        raise InputError(f"At most {MAX_FOLDERS} folders")
    for fid, f in src.items():
        if not isinstance(fid, str) or not _ID.match(fid):
            raise InputError(f"Bad folder id: {fid!r}")
        if not isinstance(f, dict):
            raise InputError(f"Folder {fid} must be an object")
        name = _SPACE.sub(" ", str(f.get("name") or "")).strip()[:MAX_NAME]
        if not name:
            raise InputError(f"Folder {fid} needs a name")
        mode = f.get("mode") or "manual"
        if mode not in MODES:
            raise InputError(f"Folder {fid}: mode must be one of {', '.join(MODES)}")
        rules = f.get("rules") if isinstance(f.get("rules"), dict) else {}
        out["folders"][fid] = {
            "id": fid, "name": name, "parent": f.get("parent") or None, "mode": mode,
            "rules": {"kinds": [str(k)[:40] for k in (rules.get("kinds") or []) if isinstance(k, str)][:MAX_RULE_VALUES],
                      "tags": _tags(rules.get("tags")), "words": _tags(rules.get("words"))},
            "order": int(f["order"]) if isinstance(f.get("order"), int) and not isinstance(f.get("order"), bool) else 0,
        }
    folders = out["folders"]
    for fid, f in folders.items():        # the hierarchy: every parent exists, nothing is its own ancestor
        if f["parent"] is not None and f["parent"] not in folders:
            raise InputError(f"Folder {fid}: parent {f['parent']!r} does not exist")
        seen, cur, depth = {fid}, f["parent"], 1
        while cur is not None:
            if cur in seen:
                raise InputError(f"Folder {fid} would be inside itself")
            seen.add(cur); cur = folders[cur]["parent"]; depth += 1
        if depth > MAX_DEPTH:
            raise InputError(f"Folders can nest at most {MAX_DEPTH} deep")
    for key in ("members", "excluded"):   # card -> folders; `members`: the first is where the card lives, the rest are references
        for card, fids in (raw.get(key) or {}).items() if isinstance(raw.get(key), dict) else []:
            keep = []
            for fid in fids if isinstance(fids, list) else []:
                ok = fid in folders if key == "members" else _folder_ok(fid, folders)
                if ok and fid not in keep:
                    keep.append(fid)
            if keep and isinstance(card, str) and len(card) <= 200:
                out[key][card] = keep
    for card, t in (raw.get("tags") or {}).items() if isinstance(raw.get("tags"), dict) else []:
        if not isinstance(t, dict) or not isinstance(card, str) or len(card) > 200:
            continue
        add = _tags(t.get("add")); added = {tag_key(x) for x in add}
        remove = [x for x in _tags(t.get("remove")) if tag_key(x) not in added]   # an explicit tag wins over its own removal
        if add or remove:
            out["tags"][card] = {"add": add, "remove": remove}
    for fid, v in (raw.get("fpos") or {}).items() if isinstance(raw.get("fpos"), dict) else []:
        if _folder_ok(fid, folders) and _xy(v):
            out["fpos"][fid] = _xy(v)
    for fid, cards in (raw.get("pos") or {}).items() if isinstance(raw.get("pos"), dict) else []:
        if not _folder_ok(fid, folders) or not isinstance(cards, dict):
            continue
        kept = {c: _xy(v) for c, v in cards.items() if isinstance(c, str) and len(c) <= 200 and _xy(v)}
        if kept:
            out["pos"][fid] = kept
    prefs = raw.get("prefs") if isinstance(raw.get("prefs"), dict) else {}
    out["prefs"] = {str(k)[:40]: v for k, v in prefs.items()
                    if isinstance(v, (str, int, float, bool)) or (isinstance(v, list) and all(isinstance(x, str) for x in v) and len(v) <= 200)}
    return out


def load(store: Store, pid: str) -> dict:
    """The stored organisation, or an empty one (a project from before Mod Map 2.0 needs no migration: it simply has none yet)."""
    raw = store.get_setting(pid, SETTING, None)
    if not isinstance(raw, dict):
        return empty()
    try:
        return normalize(raw)
    except InputError:
        return empty()


def save(store: Store, pid: str, raw) -> dict:
    """USER-ONLY (the UI is the user). Stores the normalised document; the event carries counts, not the document."""
    meta = normalize(raw)
    with store.tx() as con:
        if con.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone() is None:
            raise StateError(f"Project not found: {pid}")
        con.execute("INSERT OR REPLACE INTO project_settings(project_id, key, value_json) VALUES(?,?,?)", (pid, SETTING, json.dumps(meta)))
        store.event(con, pid, "user", "MAP_ORGANIZED", {"folders": len(meta["folders"]), "filed_cards": len(meta["members"]), "tagged_cards": len(meta["tags"])})
    return meta
