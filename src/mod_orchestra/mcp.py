"""Minimal MCP stdio JSON-RPC 2.0 server (line-delimited messages).

This is an experimental API facade, not a sandbox. It deliberately exposes
NO approval-grant endpoint. The trusted local user must approve from CLI/UI.
"""
from __future__ import annotations
import json
import sys
from .state import Store, StateError
from .doctor import inspect
from .workflow import summary, plan_project, generate_project, export_state_markdown
from .capabilities import CAPABILITIES, available_tasks, handoff
from .kb import search as kb_search
from .diagnostics import project_diagnose
from .build import tail_log
from .fabric import validate_generated
from pathlib import Path

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26")

# Shown to the connecting client (Claude Code reads this). Tells a cold agent what it can
# and cannot do here so it does not go looking for approval/build tools that do not exist.
INSTRUCTIONS = (
    "minecraft-mod-orchestra: local Fabric mod project controller. Tools are read-only except "
    "orchestra_project_plan (once per project) and orchestra_generate_source (only after the user "
    "approved the spec from the craftctl CLI or UI). There is deliberately NO tool to create projects, "
    "approve specs, grant approvals or run Gradle: ask the user to run `craftctl approve-spec <id>`, "
    "`craftctl request-build <id>`, `craftctl decide <approval> grant` and `craftctl build ...` themselves. "
    "Generated source is SOURCE_GENERATED_UNVERIFIED until a build and in-game test pass."
)

TOOLS = [
    {"name": "orchestra_doctor", "description": "Read-only Java/Gradle/Blockbench diagnostic", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "orchestra_project_status", "description": "Read project and task status", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_diagnose_build", "description": "Classify recent build log using bounded error patterns (hypotheses only)", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_logs_tail", "description": "Read the tail of the local project's latest build log", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_knowledge_search", "description": "Read-only Markdown KB search, version-filtered", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "profile": {"type": "string"}}, "required": ["query"], "additionalProperties": False}},
    {"name": "orchestra_capabilities", "description": "List the declared specialist roles and capabilities", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "orchestra_next_tasks", "description": "Read ready tasks and role suggestions", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_task_handoff", "description": "Create bounded context package for a specific task", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "task_id": {"type": "string"}}, "required": ["project", "task_id"], "additionalProperties": False}},
    {"name": "orchestra_project_plan", "description": "Create task DAG, once per project", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_generate_source", "description": "Generate source only for previously USER-APPROVED, empty project; no overwrite or code execution", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_footprint", "description": "Bounded Markdown project state", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_paint_skin", "description": "Designer: paint models/<mob>.png from the mob's models/<mob>.bbmodel (box-UV cubes): zone colours, face shading, edges, a head face with eyes/brows/nose/mouth of guaranteed contrast, at `scale` pixels per UV unit (default 2 = 128x128 over a 64x64 layout). Returns the face-contrast report. Only writes that PNG.", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "mob": {"type": "string"}, "palette": {"type": "object", "description": "{base: '#rrggbb', <name>: '#rrggbb', ...}"}, "zones": {"type": "array", "description": "[{bones: ['torso','*_arm*'], color: 'name or #hex', bands: {color, every, thickness}}]; the first matching zone wins, other bones use base", "items": {"type": "object"}}, "face": {"type": "object", "description": "{eyes, pupil, mouth, brow, teeth: '#hex', nose: bool, tusks: bool, style: 'angry'|'calm'}; pass false to leave the head unpainted"}, "scale": {"type": "integer", "minimum": 1, "maximum": 4}, "seed": {"type": "string"}}, "required": ["project", "mob", "palette"], "additionalProperties": False}},
    {"name": "orchestra_check_skin", "description": "Designer: measure how much the head's front face stands out in models/<mob>.png (works for any PNG, painted by hand or by orchestra_paint_skin)", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "mob": {"type": "string"}}, "required": ["project", "mob"], "additionalProperties": False}},
    {"name": "orchestra_check_sprites", "description": "Designer: run the creative gates on models/sprites/*.png (not the stock template of its kind, not a copy of another sprite of the set, 4+ colours) and list what would be rejected and why; repaint those and call again", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_validate_source", "description": "Static manifest + JSON verification; not a build or runtime check", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
]

def _skin_tool(store: Store, name: str, a: dict) -> object:
    import re
    from . import skin
    from .models import MODEL_DIR
    from .validation import InputError
    mob = str(a.get("mob", ""))
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", mob):
        raise InputError("mob must be the mob identifier (snake_case)")
    models = Path(store.project(a["project"])["root"]) / MODEL_DIR
    source = models / f"{mob}.bbmodel"
    if not source.is_file():
        raise StateError(f"models/{mob}.bbmodel does not exist yet: the MODEL task stages the base rig there")
    model = json.loads(source.read_text(encoding="utf8"))
    target = models / f"{mob}.png"
    if name == "orchestra_check_skin":
        if not target.is_file():
            raise StateError(f"models/{mob}.png does not exist yet")
        report = skin.face_report(model, target.read_bytes())
        return report or {"face": None, "note": "no `head` bone with a box-UV cube, or the PNG is not the model resolution (or a 2x/4x multiple): nothing to judge"}
    zones = a.get("zones") or []
    if len(zones) > 32 or len(json.dumps(a)) > 20000:
        raise InputError("too many zones or an oversized request")
    png, report = skin.paint_skin(model, palette=a["palette"], zones=zones, face=a.get("face", {}), scale=int(a.get("scale", 2)), seed=str(a.get("seed") or mob)[:64])
    tmp = target.with_suffix(".png.tmp")
    tmp.write_bytes(png)
    tmp.replace(target)
    report["file"] = f"{MODEL_DIR}/{mob}.png"
    report["next"] = f"bbmodel_geckolib_set_texture {{file: \"{mob}.bbmodel\", png_file: \"{mob}.png\", expected_revision}} then bbmodel_render to look at it"
    return report


def invoke(store: Store, name: str, a: dict) -> object:
    if name == "orchestra_doctor":
        return inspect()
    if name == "orchestra_diagnose_build":
        return project_diagnose(store, a["project"])
    if name == "orchestra_logs_tail":
        return tail_log(store, a["project"], 80)
    if name == "orchestra_knowledge_search":
        return kb_search(a["query"], a.get("profile"))
    if name == "orchestra_capabilities":
        return CAPABILITIES
    if name == "orchestra_next_tasks":
        return available_tasks(store, a["project"])
    if name == "orchestra_task_handoff":
        return handoff(store, a["project"], a["task_id"])
    if name == "orchestra_project_status":
        return summary(store, a["project"])
    if name == "orchestra_project_plan":
        return plan_project(store, a["project"])
    if name == "orchestra_generate_source":
        return generate_project(store, a["project"])
    if name == "orchestra_footprint":
        return export_state_markdown(store, a["project"])
    if name in ("orchestra_paint_skin", "orchestra_check_skin"):
        return _skin_tool(store, name, a)
    if name == "orchestra_check_sprites":
        from .spec import read_spec
        from .spritecheck import catalogue, check_sprites
        proj = store.project(a["project"])
        spec, folder = read_spec(proj["spec"]), Path(proj["root"]) / "models" / "sprites"
        known = catalogue(spec)
        files = {p.stem: p.read_bytes() for p in sorted(folder.glob("*.png")) if p.stem in known} if folder.is_dir() else {}
        rejected = check_sprites(spec, files)
        return {"checked": sorted(files), "ok": [i for i in sorted(files) if i not in rejected], "rejected": rejected,
                "missing": sorted(set(known) - set(files)), "rule": "repaint every rejected sprite with a new silhouette and call this again; the install rejects them otherwise"}
    if name == "orchestra_validate_source":
        root = Path(store.project(a["project"])["root"])
        if not (root / ".mod-orchestra" / "generation-manifest.json").is_file():
            raise StateError("No generated source to validate yet; the user must approve the spec and source must be generated first")
        return validate_generated(root)
    raise ValueError("Unknown or forbidden MCP tool")

def handle(store: Store, message: dict) -> dict | None:
    mid = message.get("id")
    method = message.get("method")
    if mid is None:  # notifications
        return None
    try:
        if method == "initialize":
            requested = (message.get("params") or {}).get("protocolVersion")
            version = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
            result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "minecraft-mod-orchestra", "version": "0.1.0"},
                      "instructions": INSTRUCTIONS}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            allowed = next((x for x in TOOLS if x["name"] == name), None)
            if allowed is None or not isinstance(args, dict):
                raise ValueError("Unknown tool or invalid arguments")
            props = allowed["inputSchema"]["properties"]
            if not set(args) <= set(props) or not set(allowed["inputSchema"].get("required", [])) <= set(args):
                raise ValueError("Unexpected or missing arguments")
            for key, value in args.items():
                if props[key].get("type") == "string" and not isinstance(value, str):
                    raise ValueError(f"Argument {key!r} must be a string")
            value = invoke(store, name, args)
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value}]}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as exc:
        if method == "tools/call":
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}}
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(exc)}}

def run(store: Store | None = None) -> None:
    store = store or Store()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("JSON-RPC request must be object")
            result = handle(store, payload)
        except Exception as exc:
            result = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
        if result is not None:
            print(json.dumps(result, separators=(",", ":")), flush=True)

if __name__ == "__main__":
    run()
