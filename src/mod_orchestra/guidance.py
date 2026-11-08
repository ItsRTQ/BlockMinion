"""What the UI shows first: where a project is, what just happened, what to do next.

Computed server-side from the Footprint so CLI, UI and future surfaces agree. Each next step
carries an `action` the UI can run directly (POST /api/project/<id>/<action>) or a `command`
for the terminal, and a `who` (user | agent | controller).
"""
from __future__ import annotations
import time
from pathlib import Path
from .evidence import levels_for_current_source
from .state import Store, StateError

STAGES = ["idea", "spec", "source", "model", "build", "server", "client", "verified"]


def stage_of(store: Store, pid: str, proj: dict, tasks: list[dict], levels: set[str]) -> str:
    if proj["status"] == "IDEA" and proj["spec_state"] != "APPROVED":
        return "idea" if not proj["spec"].get("features") and not proj["spec"].get("mobs") else "spec"
    if proj["spec_state"] != "APPROVED":
        return "spec"
    if proj["status"] in ("IDEA", "PLAN_READY"):
        return "source"
    model_open = any(":MODEL:" in t["id"] and t["state"] != "DONE" for t in tasks)
    if model_open and "BUILD_PASS" not in levels:
        return "model"
    if "BUILD_PASS" not in levels:
        return "build"
    if "SERVER_BOOT_PASS" not in levels:
        return "server"
    if "CLIENT_BOOT_PASS" not in levels or "CONTENT_VERIFIED" not in levels:
        return "client"
    return "verified"


def guidance(store: Store, pid: str) -> dict:
    proj = store.project(pid)
    tasks = store.tasks(pid)
    root = Path(proj["root"])
    try:
        levels = levels_for_current_source(store, pid, root)
    except StateError:
        levels = set()
    stage = stage_of(store, pid, proj, tasks, levels)
    spec = proj["spec"]
    questions = spec.get("questions") or []
    runs = store.runs(pid)
    running = [r for r in runs if r["state"] == "RUNNING"]
    now = time.time()
    live = [a for a in store.approvals(pid) if a["expires_at"] > now]   # expired approvals are dead ends; never offer them
    pending = [a for a in live if a["state"] == "PENDING"]
    granted = [a for a in live if a["state"] == "GRANTED"]
    waiting = [t for t in tasks if t["state"] in ("WAITING_USER", "BLOCKED", "FAILED")]
    ready = [t for t in tasks if t["state"] == "READY"]
    steps: list[dict] = []

    def step(label, who, *, action=None, payload=None, command=None, detail=None):
        steps.append({"label": label, "who": who, "action": action, "payload": payload or {}, "command": command, "detail": detail})

    from .dispatch import autopilot_policy
    cost = round(sum(float(r.get("cost_usd") or 0) for r in runs), 2)
    if running:
        r = running[0]
        return {"stage": stage, "stages": STAGES, "headline": f"A {r['role']} worker is running on {r['task_id']}",
                "detail": "Started by the controller with your installed Claude Code. This page refreshes until it finishes.",
                "steps": [], "busy": True, "questions": questions, "levels": sorted(levels), "cost_usd": cost, "runs": len(runs),
                "autopilot": autopilot_policy(store, pid)}

    if stage == "idea":
        step("Let the interpreter propose a spec from your idea", "agent", action="dispatch", payload={"task": f"{pid}:SPEC"},
             detail="One bounded worker reads the idea and proposes the content (items, blocks, tool and armor sets, foods, mobs and their body plans), an art direction for each, and the behaviors (mechanics such as infection or projectiles) the coder will build after generation. It may ask up to 3 questions; you approve the result.")
        step("…or write the idea in grammar form", "user", command="craftctl new … --idea \"items: a, b; blocks: c; mobs: d; tab: Label\"")
    elif stage == "spec":
        for q in questions:
            step(f"Answer: {q}", "user", action="answer", payload={"text": ""}, detail="Your answer is appended to the idea and the interpreter runs again.")
        if not questions and proj["spec_state"] != "APPROVED":
            step("Approve the spec", "user", action="approve", detail="Review items, blocks, recipes, drops, tab and mobs below. Approval unlocks generation.")
            step("Or change it first", "user", command=f"craftctl add-recipe/add-drop/add-mob/set-tab {pid} …")
    elif stage == "source":
        step("Generate the Fabric source", "controller", action="generate", detail="Deterministic generator: Java, JSON, placeholder textures, Gradle wrapper. Never overwrites.")
    elif stage == "model":
        for t in tasks:
            if ":MODEL:" in t["id"] and t["state"] == "READY":
                step(f"Dispatch the designer for {t['id'].split(':MODEL:')[1]}", "agent", action="dispatch", payload={"task": t["id"]},
                     detail="Authors the .bbmodel, texture, idle/walk with the vendored Blockbench MCP, renders previews, exports. ~$1–2.")
            elif ":MODEL:" in t["id"] and t["state"] in ("FAILED", "WAITING_USER", "BLOCKED"):
                step(f"Requeue {t['id']} ({t['state']})", "user", action="requeue", payload={"task": t["id"]}, detail=t.get("last_error"))
    elif stage == "build":
        if granted:
            step("Run the trusted build", "controller", action="build", payload={"approval_id": granted[0]["id"]}, detail="Gradle through the broker; BUILD_PASS is recorded with the JAR hash.")
        elif pending:
            step("Grant the pending build approval", "user", action="decide", payload={"approval_id": pending[0]["id"], "grant": True}, detail=pending[0]["description"])
        else:
            step("Request a build approval", "user", action="request-build", detail="One-use approval; Gradle is executable project code.")
        step("Or look at it in the game now", "user", action="run-client", detail="runClient compiles the current source and opens Minecraft with only this mod. The trusted build is still needed for evidence.")
    elif stage == "server":
        gt_granted = [a for a in granted if a["kind"] == "run_gametests"]
        gt_pending = [a for a in pending if a["kind"] == "run_gametests"]
        if "GAMETEST_PASS" not in levels:
            if gt_granted:
                step("Run the mod's GameTests", "controller", action="gametest", payload={"approval_id": gt_granted[0]["id"]}, detail="Headless test server; generated checks plus any tests written for custom features. Records GAMETEST_PASS or opens a repair.")
            elif gt_pending:
                step("Grant the pending GameTest approval", "user", action="decide", payload={"approval_id": gt_pending[0]["id"], "grant": True}, detail=gt_pending[0]["description"])
            else:
                step("Request a GameTest run (optional, cheap)", "user", action="request-gametest", detail="Runs the generated checks (items registered, blocks place, mobs spawn, recipes load) and the coder's tests for custom features in a headless server.")
        smoke_granted = [a for a in granted if a["kind"] == "run_dedicated_server_smoke"]
        smoke_pending = [a for a in pending if a["kind"] == "run_dedicated_server_smoke"]
        if smoke_granted:
            step("Run the dedicated-server smoke", "controller", action="server-smoke", payload={"approval_id": smoke_granted[0]["id"]}, detail="Boots the server with the mod in run/, checks the log, stops it. Records SERVER_BOOT_PASS or opens a repair.")
        elif smoke_pending:
            step("Grant the server smoke approval", "user", action="decide", payload={"approval_id": smoke_pending[0]["id"], "grant": True}, detail=smoke_pending[0]["description"])
        else:
            step("Request a server smoke approval", "user", action="request-smoke", detail="It accepts the Minecraft EULA in the isolated run/ folder on your behalf.")
    elif stage == "client":
        if "CLIENT_BOOT_PASS" not in levels:
            step("Launch the game client", "user", action="run-client", detail="Opens Minecraft with only this mod. Look at tabs, items, mobs; then record what you saw below.")
        step("Record what you observed", "user", action="evidence", detail="CLIENT_BOOT_PASS once the game loaded the mod; CONTENT_VERIFIED for behaviour you actually saw.")
    else:
        step("All four evidence levels are on this exact source", "controller", detail="Change the spec in a new project, or add tasks (e.g. another mob) and iterate.")

    for t in waiting:
        if ":MODEL:" in t["id"] or t["id"].endswith(":SPEC"):
            continue
        step(f"{t['id']} is {t['state']}", "user", action="requeue", payload={"task": t["id"]}, detail=t.get("last_error") or "Requeue to try again")
    for t in ready:
        if ":FEATURE:" in t["id"] or ":CHANGE:" in t["id"]:
            what = "implement the feature" if ":FEATURE:" in t["id"] else "make the change"
            steps.insert(0, {"label": f"Dispatch the coder to {what} ({t['id'].split(':', 1)[1]})", "who": "agent", "action": "dispatch",
                             "payload": {"task": t["id"]}, "command": None, "detail": "The coder gets the card's files, relations and your request — not the whole project."})
        elif any(k in t["id"] for k in (":ADD_ITEM:", ":ADD_BLOCK:", ":ADD_MATERIAL:", ":ADD_FOOD:", ":ADD_ORE:")):
            steps.insert(0, {"label": f"Dispatch the coder to register the new {t['id'].split(':')[-2].split('_')[1].lower()} ({t['id'].split(':')[-1]})", "who": "agent", "action": "dispatch",
                             "payload": {"task": t["id"]}, "command": None, "detail": "Its model, texture and lang are already written; the coder only adds the registration lines and compiles."})
        elif ":ADD_MOB:" in t["id"]:
            steps.insert(0, {"label": f"Dispatch the coder to register the new mob ({t['id'].split(':ADD_MOB:')[1]})", "who": "agent", "action": "dispatch",
                             "payload": {"task": t["id"]}, "command": None, "detail": "The mob's own files are already written; the coder only wires ModMain/ModClient and compiles."})
        elif ":ARMOR3D:" in t["id"]:
            steps.insert(0, {"label": f"Dispatch the designer to model the 3D armor ({t['id'].split(':ARMOR3D:')[1]})", "who": "agent", "action": "dispatch",
                             "payload": {"task": t["id"]}, "command": None, "detail": "Edits the GeckoLib armor template in Blockbench (MCP), textures it, renders it; the controller validates the bones and installs. ~$1–2."})
        elif ":ARMOR:" in t["id"]:
            steps.insert(0, {"label": f"Dispatch the designer to paint worn armor ({t['id'].split(':ARMOR:')[1]})", "who": "agent", "action": "dispatch",
                             "payload": {"task": t["id"]}, "command": None, "detail": "Paints both armor layers in the mod's theme, renders them worn on the player template, installs. ~$1."})
        elif ":SPRITES:" in t["id"]:
            steps.append({"label": f"Dispatch the designer to paint the icons ({t['id']})", "who": "agent", "action": "dispatch",
                          "payload": {"task": t["id"]}, "command": None, "detail": "Designs every icon from its art direction (and the worn-armor layers) by script; the controller rejects copies of the stock shapes and installs the rest. Autopilot runs it by itself. ~$0.5–1."})   # cosmetic: never ahead of an approval, a build or a model
        elif ":MODEL:" in t["id"] and stage not in ("model",):
            steps.insert(0, {"label": f"Dispatch the designer for {t['id'].split(':MODEL:')[1]}", "who": "agent", "action": "dispatch",
                             "payload": {"task": t["id"]}, "command": None, "detail": "Authors the .bbmodel, texture, idle/walk; renders previews. ~$1–2."})
    repairs = [t for t in ready if ":REPAIR:" in t["id"]]
    if repairs:
        step(f"Let the debugger repair the build ({repairs[0]['id']})", "agent", action="dispatch", payload={"task": repairs[0]["id"]}, detail="Autonomous repair loop, max 3 attempts per failure.")
    agent_ready = [t for t in ready if t["role"] not in ("qa",)]
    if agent_ready and proj["spec_state"] == "APPROVED" and not any(s["who"] == "user" and s["action"] in ("approve", "answer", "decide") for s in steps):
        step(f"Autopilot: run the {len(agent_ready)} READY task(s) back to back until you are needed", "agent", action="orchestrate",
             payload={"max_runs": 5, "max_cost_usd": 5.0},
             detail="Chains interpreter → coder → designer → debugger automatically. Stops at every gate (approval, question, unrepairable failure) or when the budget is hit.")
    last = runs[-1] if runs else None
    happened = (f"Last worker: {last['role']} on {last['task_id']} → {last['state']}" + (f" (${last['cost_usd']:.2f}, {int(last['duration_s'] or 0)} s)" if last.get("cost_usd") else "")) if last else "No agent has run yet."
    return {"stage": stage, "stages": STAGES, "headline": HEADLINES[stage], "detail": happened, "steps": steps, "busy": False,
            "questions": questions, "levels": sorted(levels), "cost_usd": cost, "runs": len(runs), "autopilot": autopilot_policy(store, pid)}


HEADLINES = {
    "idea": "Idea recorded — no spec yet",
    "spec": "Spec drafted — needs your review",
    "source": "Spec approved — source not generated",
    "model": "Source ready — mob models pending",
    "build": "Ready to build",
    "server": "Built — dedicated server not verified",
    "client": "Server verified — needs your eyes in the game",
    "verified": "Verified on this exact source",
}
