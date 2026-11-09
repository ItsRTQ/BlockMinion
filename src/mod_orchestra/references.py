"""Optional reference images: pictures the user attaches to a mob to say 'like this'. Never required, never interpreted by the tool: the designer is told they
exist and may look at them (inspiration for shape, proportion, mood and palette; not to be traced). They live in the project at references/<mob>/ref-<n>.<ext>."""
from __future__ import annotations

import base64 as _b64
import re
from pathlib import Path

from .state import Store
from .validation import InputError, safe_inside

MAX_BYTES = 3_000_000
MAX_PER_MOB = 4
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


def _kind(raw: bytes) -> str | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    return None


def _dir(store: Store, pid: str, mob: str) -> Path:
    proj = store.project(pid)
    if mob not in {m["identifier"] for m in proj["spec"].get("mobs", [])}:
        raise InputError(f"Unknown mob {mob!r}")
    return Path(proj["root"]) / "references" / mob


def list_references(store: Store, pid: str, mob: str) -> list[str]:
    folder = Path(store.project(pid)["root"]) / "references" / mob
    return sorted(f"references/{mob}/{p.name}" for p in folder.iterdir() if p.is_file() and p.suffix in MIME) if folder.is_dir() else []


def add_reference(store: Store, pid: str, mob: str, data_base64: str) -> dict:
    """USER-ONLY. The file type is decided by the bytes, not by the name the browser reports."""
    folder = _dir(store, pid, mob)
    try:
        raw = _b64.b64decode(data_base64, validate=True)
    except Exception:
        raise InputError("The image is not valid base64")
    ext = _kind(raw)
    if ext is None:
        raise InputError("A reference is a PNG, JPEG or WebP image")
    if len(raw) > MAX_BYTES:
        raise InputError(f"A reference is at most {MAX_BYTES // 1_000_000} MB")
    existing = list_references(store, pid, mob)
    if len(existing) >= MAX_PER_MOB:
        raise InputError(f"A mob has at most {MAX_PER_MOB} references: remove one first")
    folder.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(m.group(1)) for p in existing if (m := re.search(r"ref-(\d+)\.", p))] or [0])
    target = folder / f"ref-{n}{ext}"
    target.write_bytes(raw)
    store.add_event(pid, "user", "REFERENCE_ADDED", {"mob": mob, "file": f"references/{mob}/{target.name}", "bytes": len(raw)})
    return {"mob": mob, "file": f"references/{mob}/{target.name}", "references": list_references(store, pid, mob)}


def remove_reference(store: Store, pid: str, mob: str, name: str) -> dict:
    folder = _dir(store, pid, mob)
    if not re.fullmatch(r"ref-\d+\.(png|jpg|webp)", name or ""):
        raise InputError("Not a reference file name")
    target = safe_inside(folder, name)
    if not target.is_file():
        raise InputError("No such reference")
    target.unlink()
    store.add_event(pid, "user", "REFERENCE_REMOVED", {"mob": mob, "file": f"references/{mob}/{name}"})
    return {"mob": mob, "references": list_references(store, pid, mob)}


def references_block(store: Store, pid: str, mob: str) -> str:
    files = list_references(store, pid, mob)
    if not files:
        return ""
    return ("\n## Reference images the user attached (optional inspiration)\n"
            "Open them and look, if you can: take what they say about proportion, silhouette, mood and palette, and make your own creature. Do not trace or copy them.\n"
            + "\n".join(f"- `{f}`" for f in files) + "\n")
