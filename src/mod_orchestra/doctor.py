"""Non-invasive first-run diagnostics. Never install or run downloaded software."""
from __future__ import annotations
import hashlib
import time
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from .config import PROFILE, WRAPPER_DIR, WRAPPER_FILES


def _version(command: list[str]) -> str | None:
    try:
        p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=8, check=False)
        return p.stdout.strip().splitlines()[0][:180] if p.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _staging_status() -> dict:
    from .config import PROJECTS
    from .fabric import STAGING_DIRNAME, STAGING_ORPHAN_AGE
    root = PROJECTS / STAGING_DIRNAME
    if not root.is_dir():
        return {"pending": [], "note": "none"}
    now = time.time()
    pending = [{"name": e.name, "age_s": int(now - e.stat().st_mtime), "orphan": now - e.stat().st_mtime > STAGING_ORPHAN_AGE}
               for e in root.iterdir() if e.is_dir()]
    return {"pending": pending, "note": "orphans are removed by the next craftctl generate"}


def _schema_status() -> dict:
    from .state import Store, SCHEMA_VERSION, StateError
    try:
        store = Store()
        return {"version": store.schema_version(), "current": SCHEMA_VERSION, "path": str(store.path), "ok": True}
    except StateError as exc:
        return {"version": None, "current": SCHEMA_VERSION, "ok": False, "error": str(exc)}


def _wrapper_status() -> dict:
    """Recompute embedded wrapper hashes against the provenance record."""
    files = {}
    ok = True
    for relative, expected in WRAPPER_FILES.items():
        path = WRAPPER_DIR / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        files[relative] = {"sha256": actual, "ok": actual == expected}
        ok = ok and actual == expected
    return {"gradle": PROFILE["gradle"], "distribution_sha256": PROFILE["gradle_dist_sha256"], "ok": ok,
            "files": files, "provenance": str(WRAPPER_DIR / "PROVENANCE.md")}


def inspect() -> dict:
    java = shutil.which("java")
    java_version = _version([java, "-version"]) if java else None
    major = None
    if java_version:
        m = re.search(r'"(?:1\.)?(\d+)', java_version)
        if m:
            major = int(m.group(1))
    gradle = shutil.which("gradle")
    git = shutil.which("git")
    blockbench = shutil.which("Blockbench") or shutil.which("blockbench")
    minecraft = Path(os.environ.get("APPDATA", "~/.minecraft")).expanduser() / ".minecraft" if os.name == "nt" and not os.environ.get("APPDATA", "").endswith(".minecraft") else Path.home() / ".minecraft"
    if os.name == "nt" and os.environ.get("APPDATA"):
        minecraft = Path(os.environ["APPDATA"]) / ".minecraft"
    return {
        "os": platform.system(), "machine": platform.machine(), "python": platform.python_version(),
        "profile": PROFILE, "java": {"executable": java, "version": java_version, "major": major,
                                    "compatible": major is not None and major >= PROFILE["gradle_jdk_major"],
                                    "note": f"JDK {PROFILE['gradle_jdk_major']}+ runs Gradle/Loom; sources compile with --release {PROFILE['java_major']}"},
        "gradle": {"executable": gradle, "version": _version([gradle, "--version"]) if gradle else None,
                   "note": "Optional: generated workspaces ship the official hash-verified wrapper (see wrapper)"},
        "wrapper": _wrapper_status(),
        "node": {"executable": shutil.which("node"), "version": _version([shutil.which("node"), "--version"]) if shutil.which("node") else None,
                 "note": "Required for the designer worker (vendored blockbench-mcp-safe runs on Node)"},
        "blockbench": {"executable": __import__("mod_orchestra.feedback", fromlist=["find_blockbench"]).find_blockbench(),
                       "note": "Optional: opens the designer's .bbmodel files for inspection/editing (GeckoLib Animation Utils plugin recommended)"},
        "claude_code": {"executable": shutil.which("claude") or os.environ.get("CRAFTCTL_CLAUDE_BIN"),
                        "note": "Default agent runtime (craftctl dispatch / orchestrate); uses your own Claude login"},
        "gemini_cli": {"executable": shutil.which("gemini") or os.environ.get("CRAFTCTL_GEMINI_BIN"),
                       "note": "Alternative agent runtime: CRAFTCTL_PROVIDER=gemini-cli or --provider gemini-cli; uses your own Google login"},
        "provider": os.environ.get("CRAFTCTL_PROVIDER", "claude-code"),
        "schema": _schema_status(),
        "stagings": _staging_status(),
        "git": {"executable": git, "version": _version([git, "--version"]) if git else None},
        "blockbench": {"executable": blockbench, "note": "Optional for static item/block prototypes"},
        "minecraft": {"directory": str(minecraft), "launcher_files_found": minecraft.is_dir(),
                      "note": "Not required to generate Fabric source"},
        "notes": ["No dependencies were installed or changed.", "The toolchain has not been build-verified in this environment.",
                  "Gradle's wrapper may be generated locally using a trusted Gradle installation."],
    }
