"""Model feedback loop: the user looks at the designer's previews in the UI and says what to change.
The note is stored as an event and the MODEL task is reopened; the next designer run receives every
feedback note for that mob in its packet, newest first."""
from __future__ import annotations
import json
from pathlib import Path
from .state import Store, StateError
from .validation import safe_inside, InputError

PREVIEW_SUFFIXES = ("_rest.png", "_walk.png", "_face.png", "_front.png", "_iso.png", "_preview.png")


from .references import list_references


def model_gallery(store: Store, pid: str) -> list[dict]:
    """Per mob: source/export presence, installed state, previews and texture as UI-servable paths."""
    proj = store.project(pid)
    root = Path(proj["root"]); models = root / "models"; assets = root / "src/main/resources/assets" / pid
    from .art import effective_art
    from .spec import read_spec
    spec_obj = read_spec(proj["spec"])
    out = []
    for m in proj["spec"].get("mobs", []):
        mid = m["identifier"]
        previews = sorted(p.name for p in models.glob(f"{mid}_*.png")) if models.is_dir() else []
        task = next((t for t in store.tasks(pid) if t["id"] == f"{pid}:MODEL:{mid}"), None)
        feedback = [e["payload"] for e in store.events(pid, 200) if e["kind"] == "MODEL_FEEDBACK" and e["payload"].get("mob") == mid]
        versions = []
        hist = root / ".mod-orchestra" / "previews"
        if hist.is_dir():
            runs = {r["id"]: r for r in store.runs(pid)}
            for d in sorted(hist.iterdir(), key=lambda d: runs.get(d.name, {}).get("created_at", 0)):
                files = sorted(f.name for f in d.glob(f"{mid}*.png"))
                if files:
                    r = runs.get(d.name, {})
                    versions.append({"run": d.name, "created_at": r.get("created_at"), "cost_usd": r.get("cost_usd"),
                                     "previews": [f".mod-orchestra/previews/{d.name}/{n}" for n in files]})
        out.append({"mob": mid, "identifier": mid, "body_plan": m.get("body_plan") or "quadruped", "label": m["label"], "behavior": m["behavior"], "versions": versions, "drops": m.get("drops", []),
                    "bbmodel": (models / f"{mid}.bbmodel").is_file(), "geo": (models / f"{mid}.geo.json").is_file(),
                    "animation": (models / f"{mid}.animation.json").is_file(),
                    "texture": f"models/{mid}.png" if (models / f"{mid}.png").is_file() else None,
                    "installed_texture": f"src/main/resources/assets/{pid}/textures/entity/{mid}.png" if (assets / "textures/entity" / f"{mid}.png").is_file() else None,
                    "previews": [f"models/{n}" for n in previews],
                    "task_state": task["state"] if task else None, "task": task["id"] if task else None,
                    "feedback": feedback[:10], "placeholder": not (models / f"{mid}.bbmodel").is_file(),
                    "design_notes": latest_design_notes(store, pid, mid), "mood": effective_art(spec_obj, "mob", mid)["mood"],
                    "references": list_references(store, pid, mid)})
    return out


def file_for_ui(store: Store, pid: str, relative: str) -> tuple[Path, str]:
    """Only PNG/JSON under models/ or assets/<mod>/ may be served to the local UI."""
    root = Path(store.project(pid)["root"])
    rel = relative.replace("\\", "/")
    if not (rel.startswith("models/") or rel.startswith(f"src/main/resources/assets/{pid}/") or rel.startswith(".mod-orchestra/previews/") or rel.startswith("references/")):
        raise InputError("Not a servable path")
    path = safe_inside(root, rel)
    if not path.is_file() or path.suffix.lower() not in (".png", ".json", ".jpg", ".webp") or (path.suffix.lower() in (".jpg", ".webp") and not rel.startswith("references/")):
        raise InputError("Not a servable file")
    return path, {".png": "image/png", ".json": "application/json", ".jpg": "image/jpeg", ".webp": "image/webp"}[path.suffix.lower()]


def record_design_notes(store: Store, pid: str, mob: str, handoff: dict, run_id: str) -> dict | None:
    """What the designer explored before building: `design_notes: {takes: [2-5 one-liners], chosen: n, why}` in its handoff. Lenient on purpose: it is
    a thinking aid and a menu for the user's redesign, never a gate, so a missing or malformed one is simply not recorded."""
    notes = handoff.get("design_notes") if isinstance(handoff, dict) else None
    if not isinstance(notes, dict) or not isinstance(notes.get("takes"), list):
        return None
    takes = [" ".join(str(t).split())[:220] for t in notes["takes"] if str(t).strip()][:5]
    if len(takes) < 2:
        return None
    chosen = notes.get("chosen")
    chosen = chosen if isinstance(chosen, int) and not isinstance(chosen, bool) and 1 <= chosen <= len(takes) else None
    out = {"mob": mob, "takes": takes, "chosen": chosen, "why": " ".join(str(notes.get("why") or "").split())[:400], "run": run_id}
    store.add_event(pid, "agent:designer", "DESIGN_NOTES", out)
    return out


def latest_design_notes(store: Store, pid: str, mob: str) -> dict | None:
    return next((e["payload"] for e in store.events(pid, 300) if e["kind"] == "DESIGN_NOTES" and e["payload"].get("mob") == mob), None)


FEEDBACK_SCOPES = ("all", "shape", "skin")


def give_model_feedback(store: Store, pid: str, mob: str, text: str = "", *, scope: str = "all", take: int | None = None, mood: dict | None = None) -> dict:
    """USER-ONLY redesign request. Everything beyond the text is optional: `scope` (all, only the shape, only the skin), `take` (build another of the
    designer's own explored ideas) and `mood` (new dial values, saved to the mob's art direction). At least one of them must say what should change."""
    from .spec import coerce_mood
    text = text.strip()
    if scope not in FEEDBACK_SCOPES:
        raise InputError(f"scope must be one of {', '.join(FEEDBACK_SCOPES)}")
    mood = coerce_mood(mood) if mood is not None else None
    if not (text or scope != "all" or take is not None or mood is not None):
        raise InputError("Say what should change: write it, pick another take, change the mood or limit it to the shape or the skin")
    proj = store.project(pid)
    if mob not in {m["identifier"] for m in proj["spec"].get("mobs", [])}:
        raise InputError(f"Unknown mob {mob!r}")
    if take is not None:
        notes = latest_design_notes(store, pid, mob)
        if not notes:
            raise InputError("This mob has no design notes yet: the designer has not explored takes for it")
        if not isinstance(take, int) or isinstance(take, bool) or not 1 <= take <= len(notes["takes"]):
            raise InputError(f"take is a number from 1 to {len(notes['takes'])}")
    if mood is not None:
        from .content import set_mood
        set_mood(store, pid, "mob", mob, mood)
    task_id = f"{pid}:MODEL:{mob}"
    task = next((t for t in store.tasks(pid) if t["id"] == task_id), None)
    if task is None:
        raise StateError(f"No MODEL task for {mob}; plan the project first")
    store.add_event(pid, "user", "MODEL_FEEDBACK", {"mob": mob, "text": text[:600], "task": task_id, "scope": scope, "take": take, "mood": mood})
    if task["state"] == "DONE":
        with store.tx() as con:
            con.execute("UPDATE tasks SET state='READY',version=version+1,lease_owner=NULL,lease_expiry=NULL,attempt=attempt+1 WHERE id=?", (task_id,))
            store.event(con, pid, "user", "TASK_REQUEUED", {"task": task_id, "from": "DONE", "reason": "model feedback"})
    elif task["state"] in ("FAILED", "WAITING_USER", "BLOCKED"):
        store.requeue(task_id, "model feedback")
    return {"mob": mob, "task": task_id, "state": "READY", "next": {"action": "dispatch", "payload": {"task": task_id}}}


def feedback_context(store: Store, pid: str, mob: str) -> str:
    from .art import mood_prose
    events = [e["payload"] for e in store.events(pid, 200) if e["kind"] == "MODEL_FEEDBACK" and e["payload"].get("mob") == mob]
    if not events:
        return ""
    notes = latest_design_notes(store, pid, mob)
    lines = ["", "## User feedback on the previous model (newest first): apply it, keep what was not mentioned"]
    for n in events[:8]:
        parts = [n.get("text") or ""]
        if n.get("scope") == "shape":
            parts.append("[Change ONLY the shape: proportions, cubes, silhouette, animations. Keep the look of the current skin: its palette and surface, repainting only what the new UV layout requires.]")
        elif n.get("scope") == "skin":
            parts.append("[Change ONLY the skin and face: keep the geometry and the animations exactly as they are, repaint.]")
        if n.get("take") and notes and n["take"] <= len(notes["takes"]):
            parts.append(f"[The user prefers take {n['take']} from your own design notes: \"{notes['takes'][n['take'] - 1]}\". Build that one, in your own way.]")
        if n.get("mood"):
            parts.append(f"[The user adjusted the mood: {mood_prose(n['mood'])}.]")
        lines.append("- " + " ".join(p for p in parts if p))
    lines += ["", f"The previous `models/{mob}.bbmodel` is still there: edit it (`bbmodel_edit`, `bbmodel_geckolib_upsert_animation` with `replace: true`) rather than starting over, unless the feedback asks for a different creature."]
    return "\n".join(lines)


def find_blockbench() -> str | None:
    """Best-effort location of the Blockbench desktop app (not required: file association is used first)."""
    import os, shutil
    candidates = []
    if os.name == "nt":
        for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
            if base:
                candidates += [Path(base) / "Programs" / "Blockbench" / "Blockbench.exe", Path(base) / "Blockbench" / "Blockbench.exe"]
    elif os.uname().sysname == "Darwin" if hasattr(os, "uname") else False:
        candidates += [Path("/Applications/Blockbench.app")]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("blockbench") or shutil.which("Blockbench")


def open_in_blockbench(store: Store, pid: str, mob: str) -> dict:
    """Open models/<mob>.bbmodel with the user's Blockbench (file association). Local, user-initiated, never run by agents."""
    import os, subprocess, sys
    root = Path(store.project(pid)["root"])
    if mob not in {m["identifier"] for m in store.project(pid)["spec"].get("mobs", [])}:
        raise InputError(f"Unknown mob {mob!r}")
    path = root / "models" / f"{mob}.bbmodel"
    if not path.is_file():
        raise InputError("No .bbmodel for this mob yet (the designer has not run)")
    app = find_blockbench()
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise StateError(f"Could not open {path.name}: {exc}. Install Blockbench (https://www.blockbench.net) with the GeckoLib Animation Utils plugin, or open the file by hand.")
    store.add_event(pid, "user", "OPENED_IN_BLOCKBENCH", {"mob": mob, "app": app})
    return {"opened": str(path), "app": app, "note": None if app else "Opened with the system's default app for .bbmodel; if nothing appeared, install Blockbench."}
