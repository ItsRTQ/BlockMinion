"""Mod Map: every feature of a mod as a card, and what derives from what, as edges.

Two sources, one graph:
- derived cards: computed from the spec every time (items, blocks, mobs, materials as one collapsed set
  each, foods, tab); never stored, so they always match what the generator built.
- custom cards (schema v7 `feature_cards`): anything the spec cannot express (a backpack, a minimap, a
  magic system). Created by the controller when a FEATURE task is requested, updated by the agent's
  handoff (`card` object) and by the user from the UI.

Edges carry the derivation: crafts, smelts_into, drops, drops_on_death, made_of, repairs.
`map_text()` is the compact form every worker packet receives so agents know what exists and what
connects without reading the code.
"""
from __future__ import annotations
import json
import re
import time
from pathlib import Path

from .spec import read_spec, coerce_mob_drop
from .state import Store, StateError
from .validation import InputError

CARD_KINDS = ("item", "block", "mob", "material", "food", "tab", "custom")
STATUSES = ("planned", "generated", "verified")
EDGE_LABEL = {"crafts": "crafts", "smelts_into": "smelts into", "drops": "drops", "drops_on_death": "drops on death", "made_of": "made of", "repairs": "repairs", "uses": "uses", "related": "related"}


def _local(ident: str, mod_id: str) -> str | None:
    """Local id for a local or <mod>:x reference; None for vanilla/tags."""
    if ident.startswith("#"):
        return None
    if ":" in ident:
        ns, path = ident.split(":", 1)
        return path if ns == mod_id else None
    return ident


def derived_cards(spec_raw: dict, workspace: Path | None) -> tuple[dict[str, dict], list[dict]]:
    spec = read_spec(spec_raw)
    mod = spec.mod_id
    cards: dict[str, dict] = {}
    edges: list[dict] = []
    assets = (workspace / "src/main/resources/assets" / mod) if workspace else None

    def tex(kind, ident):
        if not assets: return None
        p = assets / ("textures/block" if kind == "block" else "textures/item") / f"{ident}.png"
        return f"src/main/resources/assets/{mod}/textures/{'block' if kind == 'block' else 'item'}/{ident}.png" if p.is_file() else None

    for f in spec.features:
        cards[f.identifier] = {"id": f.identifier, "kind": f.kind, "title": f.label, "description": f"{'Block' if f.kind == 'block' else 'Item'} `{mod}:{f.identifier}`.", "owner": "spec",
                               "texture": tex(f.kind, f.identifier), "files": [f"src/main/resources/assets/{mod}/models/item/{f.identifier}.json"]}
    for m in spec.materials:
        pieces = m.item_ids()
        cards[m.identifier] = {"id": m.identifier, "kind": "material", "title": f"{m.label} set", "owner": "spec",
                               "description": f"Tier material `{m.identifier}` ({m.mining_level}-level, {m.durability} uses, +{m.attack_damage_bonus} dmg). Pieces: {', '.join(pieces)}.",
                               "pieces": [{"id": p, "kind": "tool" if any(p.endswith('_' + t) for t in ('sword', 'pickaxe', 'axe', 'shovel', 'hoe')) else "armor", "texture": tex("item", p)} for p in pieces],
                               "files": [f"src/main/java/{spec.package.replace('.', '/')}/gear/{''.join(x.capitalize() for x in m.identifier.split('_'))}Tier.java"] + [f"src/main/resources/assets/{mod}/models/item/{p}.json" for p in pieces]}
        src = _local(m.ingredient, mod)
        if src:
            edges.append({"from": src, "to": m.identifier, "kind": "made_of"})
            edges.append({"from": src, "to": m.identifier, "kind": "repairs"})
        else:
            edges.append({"from": "vanilla:" + m.ingredient, "to": m.identifier, "kind": "made_of"})
    for f in spec.foods:
        eff = ", ".join(e["effect"].replace("minecraft:", "") for e in f.effects) if f.effects else "no effect"
        cards[f.identifier] = {"id": f.identifier, "kind": "food", "title": f.label, "owner": "spec", "texture": tex("item", f.identifier),
                               "description": f"Food `{mod}:{f.identifier}`: nutrition {f.nutrition}, saturation {f.saturation}, {eff}.",
                               "files": [f"src/main/resources/assets/{mod}/models/item/{f.identifier}.json"]}
    for mb in spec.mobs:
        cards[mb.identifier] = {"id": mb.identifier, "kind": "mob", "title": mb.label, "owner": "spec",
                               "description": f"{mb.behavior.capitalize()} GeckoLib mob `{mod}:{mb.identifier}` ({mb.health} HP, speed {mb.speed}). Spawn egg `{mb.identifier}_spawn_egg`.",
                               "files": [f"src/main/java/{spec.package.replace('.', '/')}/entity/{''.join(x.capitalize() for x in mb.identifier.split('_'))}Entity.java", f"models/{mb.identifier}.bbmodel"]}
        for d in mb.drops:
            d = coerce_mob_drop(d); tgt = _local(d.item, mod)
            edges.append({"from": mb.identifier, "to": tgt or "vanilla:" + d.item, "kind": "drops_on_death", "label": f"{d.count_min}-{d.count_max}" + (f" @{int(d.chance * 100)}%" if d.chance < 1 else "")})
    for d in spec.drops:
        tgt = _local(d.item, mod)
        edges.append({"from": d.block, "to": tgt or "vanilla:" + d.item, "kind": "drops", "label": f"{d.count_min}-{d.count_max}" + (" fortune" if d.fortune else "")})
    for r in spec.recipes:
        res = _local(r.result, mod) or "vanilla:" + r.result
        inputs = list(r.key.values()) if r.kind == "shaped" else list(r.ingredients)
        kind = "smelts_into" if r.kind in ("smelting", "blasting", "smoking", "campfire_cooking") else "crafts"
        for ing in inputs:
            src = _local(ing, mod) or "vanilla:" + ing
            edges.append({"from": src, "to": res, "kind": kind, "label": r.id})
    # pieces of a material fold into the set node
    piece_of = {p: m.identifier for m in spec.materials for p in m.item_ids()}
    for e in edges:
        e["from"] = piece_of.get(e["from"], e["from"]); e["to"] = piece_of.get(e["to"], e["to"])
    # vanilla references become light nodes
    for e in edges:
        for key in ("from", "to"):
            v = e[key]
            if v.startswith("vanilla:") and v not in cards:
                cards[v] = {"id": v, "kind": "vanilla", "title": v.split(":", 1)[1].replace("minecraft:", ""), "description": "Vanilla Minecraft content.", "owner": "vanilla", "files": []}
    if spec.tab:
        cards["__tab"] = {"id": "__tab", "kind": "tab", "title": f"Creative tab: {spec.tab}", "description": "All of this mod's content is listed here.", "owner": "spec", "files": []}
    # dedupe edges
    seen, out = set(), []
    for e in edges:
        k = (e["from"], e["to"], e["kind"], e.get("label"))
        if k not in seen and e["from"] != e["to"]:
            seen.add(k); out.append(e)
    return cards, out


def custom_cards(store: Store, pid: str) -> dict[str, dict]:
    with store.tx() as con:
        rows = con.execute("SELECT * FROM feature_cards WHERE project_id=? ORDER BY created_at", (pid,)).fetchall()
    out = {}
    for r in rows:
        out[r["id"]] = {"id": r["id"], "kind": r["kind"], "title": r["title"], "description": r["description"], "owner": r["owner"], "status": r["status"],
                        "derived_from": json.loads(r["derived_from_json"]), "produces": json.loads(r["produces_json"]), "files": json.loads(r["files_json"]),
                        "acceptance": json.loads(r["acceptance_json"]), "history": json.loads(r["history_json"]), "created_at": r["created_at"], "updated_at": r["updated_at"]}
    return out


def project_status_to_card_status(status: str, levels: set[str]) -> str:
    if "CONTENT_VERIFIED" in levels:
        return "verified"
    if status in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        return "generated"
    return "planned"


def mod_map(store: Store, pid: str) -> dict:
    proj = store.project(pid)
    ws = Path(proj["root"])
    cards, edges = derived_cards(proj["spec"], ws if ws.is_dir() else None)
    from .evidence import levels_for_current_source
    try:
        levels = levels_for_current_source(store, pid, ws)
    except StateError:
        levels = set()
    base_status = project_status_to_card_status(proj["status"], levels)
    for c in cards.values():
        c.setdefault("status", base_status if c["owner"] == "spec" else "vanilla")
    custom = custom_cards(store, pid)
    for c in custom.values():
        cards[c["id"]] = c
        for src in c["derived_from"]:
            edges.append({"from": src, "to": c["id"], "kind": "uses"})
        for dst in c["produces"]:
            edges.append({"from": c["id"], "to": dst, "kind": "related"})
    tasks = {t["id"]: t for t in store.tasks(pid)}
    for c in cards.values():
        open_tasks = [t for t in tasks.values() if (":CHANGE:" + c["id"] + ":" in t["id"] + ":" or t["id"].endswith(":FEATURE:" + c["id"]) or t["id"].endswith(":MODEL:" + c["id"]) or t["id"].endswith(":ARMOR:" + c["id"])) and t["state"] not in ("DONE", "CANCELLED")]
        c["open_tasks"] = [{"id": t["id"], "state": t["state"], "role": t["role"]} for t in open_tasks]
    layout = store.get_setting(pid, "map_layout", {}) or {}
    return {"project": pid, "cards": list(cards.values()), "edges": edges, "layout": layout, "edge_labels": EDGE_LABEL}


def map_text(store: Store, pid: str, limit_chars: int = 3500) -> str:
    """Compact, agent-facing form of the map for worker packets."""
    m = mod_map(store, pid)
    lines = ["## Mod map (what exists and what derives from what)"]
    for c in sorted(m["cards"], key=lambda c: (c["kind"], c["id"])):
        if c["kind"] == "vanilla":
            continue
        extra = f" · pieces: {', '.join(p['id'] for p in c.get('pieces', []))}" if c.get("pieces") else ""
        files = f" · files: {', '.join(c.get('files', [])[:3])}" if c.get("files") else ""
        lines.append(f"- [{c['kind']}] {c['id']}: {c.get('description', c.get('title', ''))[:140]}{extra}{files}")
    for e in m["edges"]:
        lines.append(f"  {e['from']} --{EDGE_LABEL.get(e['kind'], e['kind'])}{' (' + e['label'] + ')' if e.get('label') else ''}--> {e['to']}")
    text = "\n".join(lines)
    return text[:limit_chars] + ("\n… (map truncated)" if len(text) > limit_chars else "")


# ---- custom cards and the tasks that create/change them ----
def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return s[:40] or "feature"


def create_feature_card(store: Store, pid: str, *, title: str, description: str, acceptance: list[str], derived_from: list[str] | None = None,
                        owner: str = "user", status: str = "planned") -> dict:
    title = title.strip(); description = description.strip()
    if not title or not description:
        raise InputError("A feature needs a title and a description")
    proj = store.project(pid)
    cards, _ = derived_cards(proj["spec"], None)
    cid = _slug(title)
    if cid in cards or cid in custom_cards(store, pid):
        raise InputError(f"A card named {cid!r} already exists")
    known = set(cards) | set(custom_cards(store, pid))
    bad = [d for d in (derived_from or []) if d not in known]
    if bad:
        raise InputError(f"derived_from references unknown cards: {bad}")
    now = time.time()
    card = {"id": cid, "project_id": pid, "kind": "custom", "title": title, "description": description[:2000], "owner": owner, "status": status,
            "derived_from": list(derived_from or []), "produces": [], "files": [], "acceptance": [a.strip() for a in acceptance if a.strip()][:12],
            "history": [{"at": now, "by": owner, "what": "created"}]}
    with store.tx() as con:
        con.execute("INSERT INTO feature_cards(id,project_id,kind,title,description,owner,status,derived_from_json,produces_json,files_json,acceptance_json,history_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, pid, "custom", title, card["description"], owner, status, json.dumps(card["derived_from"]), "[]", "[]", json.dumps(card["acceptance"]), json.dumps(card["history"]), now, now))
        store.event(con, pid, owner, "CARD_CREATED", {"card": cid, "title": title})
    return card


def update_card(store: Store, pid: str, cid: str, *, by: str, description: str | None = None, files: list[str] | None = None,
                produces: list[str] | None = None, acceptance: list[str] | None = None, status: str | None = None, note: str | None = None) -> dict:
    cards = custom_cards(store, pid)
    if cid not in cards:
        raise InputError(f"Unknown custom card {cid!r} (spec-derived cards are edited through the spec)")
    c = cards[cid]
    if description is not None: c["description"] = description.strip()[:2000]
    if files is not None: c["files"] = sorted(set(c["files"]) | {f.replace("\\", "/") for f in files})
    if produces is not None: c["produces"] = list(produces)
    if acceptance is not None: c["acceptance"] = [a.strip() for a in acceptance if a.strip()][:12]
    if status is not None:
        if status not in STATUSES: raise InputError(f"status must be one of {STATUSES}")
        c["status"] = status
    c["history"].append({"at": time.time(), "by": by, "what": note or "updated"})
    with store.tx() as con:
        con.execute("UPDATE feature_cards SET description=?, files_json=?, produces_json=?, acceptance_json=?, status=?, history_json=?, updated_at=? WHERE id=? AND project_id=?",
                    (c["description"], json.dumps(c["files"]), json.dumps(c["produces"]), json.dumps(c["acceptance"]), c["status"], json.dumps(c["history"][-30:]), time.time(), cid, pid))
        store.event(con, pid, by, "CARD_UPDATED", {"card": cid, "note": (note or "")[:200]})
    return c


def request_feature(store: Store, pid: str, *, title: str, description: str, acceptance: list[str], derived_from: list[str] | None = None) -> dict:
    """Custom feature: a card (planned) + a coder task with the card as its brief. Carril 2, minimal loop."""
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first; features are implemented on top of the generated source")
    card = create_feature_card(store, pid, title=title, description=description, acceptance=acceptance, derived_from=derived_from)
    task_id = f"{pid}:FEATURE:{card['id']}"
    instructions = ["Implement this feature card in the existing Fabric 1.21.1 (Mojang mappings) project:", f"Title: {card['title']}", f"Description: {card['description']}"]
    if card["acceptance"]:
        instructions += ["Acceptance criteria (the user will check each one in-game):"] + [f"- {a}" for a in card["acceptance"]]
    if card["derived_from"]:
        instructions += ["Builds on: " + ", ".join(card["derived_from"]) + " (see the mod map in your packet for what they are and where they live)."]
    instructions += ["Keep the change minimal and self-contained; register new content in ModMain like the existing content; add lang entries and models for any new item.",
                     "Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0.",
                     "In your handoff include a `card` object: {\"files\": [every file you created or edited], \"description\": \"one paragraph of what you built and how it works\", \"produces\": [ids of new content you added]}.",
                     "If the feature needs something the user must decide (keybind, GUI size, which block), report WAITING_USER with the question."]
    store.add_task(pid, task_id, "coder", f"Implement feature: {card['title']}")
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(instructions)))
    store.add_event(pid, "user", "FEATURE_REQUESTED", {"card": card["id"], "task": task_id})
    return {"card": card, "task": task_id, "next": {"action": "dispatch", "payload": {"task": task_id}}}


def request_change(store: Store, pid: str, cid: str, request: str) -> dict:
    """Change an existing card (spec-derived or custom): one coder task with the card's own context."""
    request = request.strip()
    if not request:
        raise InputError("Describe the change")
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first")
    m = mod_map(store, pid)
    card = next((c for c in m["cards"] if c["id"] == cid), None)
    if card is None or card["kind"] == "vanilla":
        raise InputError(f"Unknown card {cid!r}")
    n = sum(1 for t in store.tasks(pid) if f":CHANGE:{cid}:" in t["id"]) + 1
    task_id = f"{pid}:CHANGE:{cid}:{n}"
    related = [e for e in m["edges"] if cid in (e["from"], e["to"])]
    instructions = [f"Change request on feature card `{cid}` ({card['kind']}): {card['title']}", f"What it is today: {card.get('description', '')}",
                    "Files that implement it (start here, do not go through the whole project): " + (", ".join(card.get("files", [])) or "see the mod map"),
                    "Relations: " + ("; ".join(f"{e['from']} --{EDGE_LABEL.get(e['kind'], e['kind'])}--> {e['to']}" for e in related) or "none"),
                    "", "REQUESTED CHANGE:", request[:1500], "",
                    "Make exactly this change and nothing else. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0.",
                    "In your handoff include a `card` object with `files` (every file you edited) and a one-sentence `description` of the new behaviour."]
    if card["kind"] in ("item", "block", "mob", "material", "food"):
        instructions.append("Note: this content is generated from the spec. Edit the generated files directly (the controller accepts your edits as a revision); do not try to regenerate.")
    store.add_task(pid, task_id, "coder", f"Change {card['title']}: {request[:60]}")
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(instructions)))
    if cid in custom_cards(store, pid):
        update_card(store, pid, cid, by="user", note=f"change requested: {request[:120]}")
    store.add_event(pid, "user", "CHANGE_REQUESTED", {"card": cid, "task": task_id, "request": request[:300]})
    return {"card": cid, "task": task_id, "next": {"action": "dispatch", "payload": {"task": task_id}}}


def apply_card_handoff(store: Store, pid: str, task_id: str, handoff: dict, run_id: str) -> dict | None:
    """After a FEATURE/CHANGE task is DONE: record files/description on the card (custom) or log the change (derived)."""
    card_obj = handoff.get("card") if isinstance(handoff.get("card"), dict) else {}
    files = [f for f in (card_obj.get("files") or handoff.get("changed_files") or []) if isinstance(f, str)]
    desc = card_obj.get("description") if isinstance(card_obj.get("description"), str) else None
    produces = [p for p in (card_obj.get("produces") or []) if isinstance(p, str)]
    if ":FEATURE:" in task_id:
        cid = task_id.split(":FEATURE:")[1]
        return update_card(store, pid, cid, by=f"run:{run_id}", description=desc, files=files, produces=produces, status="generated", note="implemented by a coder run")
    if ":CHANGE:" in task_id:
        cid = task_id.split(":CHANGE:")[1].rsplit(":", 1)[0]
        if cid in custom_cards(store, pid):
            return update_card(store, pid, cid, by=f"run:{run_id}", description=desc, files=files, status="generated", note="changed by a coder run")
        store.add_event(pid, "controller", "CARD_CHANGED", {"card": cid, "run": run_id, "files": files[:20], "description": (desc or "")[:300]})
    return None
