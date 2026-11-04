#!/usr/bin/env python3
"""Regenerate src/mod_orchestra/resources/blockbench/rigs/* from the recipes in mod_orchestra.rigs.

    python scripts/regen_rigs.py [plan ...]

Each plan goes through scripts/build_rig.mjs, i.e. the vendored blockbench-mcp-safe code, so the committed
.bbmodel/.geo.json/.animation.json are exactly what the designer's MCP tools would produce. The recipe itself is
committed too (<plan>.recipe.json) so a test can detect a recipe that changed without a regen.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mod_orchestra import rigs  # noqa: E402


def build(plan: str) -> dict:
    rec = rigs.recipe(plan)
    rigs.RIG_DIR.mkdir(parents=True, exist_ok=True)
    rigs.rig_path(plan, "recipe").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf8")
    proc = subprocess.run(["node", str(ROOT / "scripts/build_rig.mjs"), str(rigs.rig_path(plan, "recipe")), str(rigs.RIG_DIR)],
                          capture_output=True, text=True)
    if proc.returncode:
        raise SystemExit(f"{plan}: build failed\n{proc.stderr}")
    return json.loads(proc.stdout)


if __name__ == "__main__":
    plans = sys.argv[1:] or list(rigs.RECIPES)
    for p in plans:
        rep = build(p)
        q = rep["quality"]
        print(f"{p}: valid={rep['validate']['valid']} warnings={rep['validate'].get('warnings', [])} "
              f"quality errors={q.get('errors', [])} warnings={q.get('warnings', [])}")
