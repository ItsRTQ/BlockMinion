"""Machine-readable capability registry and bounded, read-only task handoffs.

This registry helps the human coordinator or an LLM decide whom to invoke.
It does not confer operating-system permissions.
"""
from __future__ import annotations
import json
from .state import Store, StateError
from .workflow import export_state_markdown

CAPABILITIES = {
    "coordinator": ["dispatch", "merge_decisions", "task_state", "approval_requests"],
    "interpreter": ["extract_spec", "clarify", "scope_change"],
    "planner": ["architecture", "technical_plan", "vertical_slice"],
    "scrum-master": ["task_graph", "task_dependencies", "acceptance_criteria"],
    "researcher": ["official_docs", "source_discovery", "version_research", "licenses"],
    "investigator": ["existing_repo", "code_navigation", "baseline", "extension_points"],
    "coder": ["fabric_java", "registries", "resources", "data_generation", "tests"],
    "designer": ["pixel_textures", "blockbench", "geckolib", "rigging", "animation"],
    "world-builder": ["biomes", "features", "structures", "seed_testing", "dimensions"],
    "debugger": ["gradle_logs", "live_logs", "crash_reports", "root_cause", "minimal_fix"],
    "qa": ["game_tests", "visual_checks", "server_smoke", "multiplayer"],
    "release": ["artifact_audit", "license_checks", "packaging", "publishing_review"],
}


def available_tasks(store: Store, pid: str) -> list[dict]:
    store.refresh_ready(pid)
    data = store.project(pid)
    ready = []
    for task in store.tasks(pid):
        if task["state"] == "READY":
            # Gate interpretation and build task to explicit user actions.
            auto = task["role"] in {"coder", "designer"} and data["spec_state"] == "APPROVED"
            ready.append({"id": task["id"], "title": task["title"], "role": task["role"],
                          "capabilities": CAPABILITIES.get(task["role"], []),
                          "automatable_by_current_core": bool(auto and data["status"] == "PLAN_READY"),
                          "approval_required": task["role"] in {"interpreter", "debugger", "release"}})
    return ready


def handoff(store: Store, pid: str, task_id: str) -> str:
    proj = store.project(pid)
    match = next((t for t in store.tasks(pid) if t["id"] == task_id), None)
    if match is None:
        raise StateError("Task not found in project")
    profile = proj["spec"]["profile"]
    text = [
        "# Bounded task handoff (suggestion, NOT authorization)",
        f"Task: {match['id']}", f"Title: {match['title']}",
        f"Assigned role: {match['role']}", f"Task state: {match['state']}",
        f"Minecraft profile: {profile}", f"Workspace: {proj['root']}",
        "", "## User's original idea", proj["spec"]["idea"][:1800],
        "", __import__("mod_orchestra.modmap", fromlist=["map_text"]).map_text(store, pid),
        "", "## Constraints", "- No unapproved executable, dependency, file overwrite, world change or publication.",
        "- Fabric-first; check exact API signatures before proposing patches.",
        "- Agent roles are prompts; they do not provide a sandbox.",
        "- Return concrete changed paths, logs, tests and unverified behavior, never self-declared runtime success.",
        "", "## Relevant capabilities", ", ".join(CAPABILITIES.get(match["role"], [])),
        "", "## Footprint excerpt", export_state_markdown(store, pid)[:1800],
        "", "## Completion contract", "Return task_id, status, changed_files, evidence, risks, next_action."
    ]
    result = "\n".join(text)
    return result[:5600]  # context budget (characters, not actual tokenizer tokens)
