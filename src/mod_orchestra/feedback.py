"""Model feedback loop: the user looks at the designer's previews in the UI and says what to change.
The note is stored as an event and the MODEL task is reopened; the next designer run receives every
feedback note for that mob in its packet, newest first."""
from __future__ import annotations
import json
from pathlib import Path
from .state import Store, StateError
from .validation import safe_inside, InputError

PREVIEW_SUFFIXES = ("_rest.png", "_walk.png", "_face.png", "_front.png", "_iso.png", "_preview.png")


def model_gallery(store: Store, pid: str) -> list[dict]:
    """Per mob: source/export presence, installed state, previews and texture as UI-servable paths."""
    proj = store.project(pid)
    root = Path(proj["root"]); models = root / "models"; assets = root / "src/main/resources/assets" / pid
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
                    "feedback": feedback[:10], "placeholder": not (models / f"{mid}.bbmodel").is_file()})
    return out


def file_for_ui(store: Store, pid: str, relative: str) -> tuple[Path, str]:
    """Only PNG/JSON under models/ or assets/<mod>/ may be served to the local UI."""
    root = Path(store.project(pid)["root"])
    rel = relative.replace("\\", "/")
    if not (rel.startswith("models/") or rel.startswith(f"src/main/resources/assets/{pid}/") or rel.startswith(".mod-orchestra/previews/")):
        raise InputError("Not a servable path")
    path = safe_inside(root, rel)
    if not path.is_file() or path.suffix.lower() not in (".png", ".json"):
        raise InputError("Not a servable file")
    return path, ("image/png" if path.suffix.lower() == ".png" else "application/json")


def give_model_feedback(store: Store, pid: str, mob: str, text: str) -> dict:
    text = text.strip()
    if not text:
        raise InputError("Feedback is empty")
    proj = store.project(pid)
    if mob not in {m["identifier"] for m in proj["spec"].get("mobs", [])}:
        raise InputError(f"Unknown mob {mob!r}")
    task_id = f"{pid}:MODEL:{mob}"
    task = next((t for t in store.tasks(pid) if t["id"] == task_id), None)
    if task is None:
        raise StateError(f"No MODEL task for {mob}; plan the project first")
    store.add_event(pid, "user", "MODEL_FEEDBACK", {"mob": mob, "text": text[:600], "task": task_id})
    if task["state"] == "DONE":
        with store.tx() as con:
            con.execute("UPDATE tasks SET state='READY',version=version+1,lease_owner=NULL,lease_expiry=NULL,attempt=attempt+1 WHERE id=?", (task_id,))
            store.event(con, pid, "user", "TASK_REQUEUED", {"task": task_id, "from": "DONE", "reason": "model feedback"})
    elif task["state"] in ("FAILED", "WAITING_USER", "BLOCKED"):
        store.requeue(task_id, "model feedback")
    return {"mob": mob, "task": task_id, "state": "READY", "next": {"action": "dispatch", "payload": {"task": task_id}}}


def feedback_context(store: Store, pid: str, mob: str) -> str:
    notes = [e["payload"]["text"] for e in store.events(pid, 200) if e["kind"] == "MODEL_FEEDBACK" and e["payload"].get("mob") == mob]
    if not notes:
        return ""
    lines = ["", "## User feedback on the previous model (newest first) — apply it, keep what was not mentioned"]
    lines += [f"- {n}" for n in notes[:8]]
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
