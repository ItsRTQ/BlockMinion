"""Seed a CRAFTCTL_HOME with three projects for the UI tests: `infect` (the infectious zombies from the fixtures: three mobs, five behaviors, approved and
generated, so it has coder tasks, a map and a gallery) `quiet` (two items, generated, so it has an icons task and an Items tab) and `draft` (two items, approved but not generated)."""
import json
from pathlib import Path

from mod_orchestra import workflow
from mod_orchestra.config import HOME
from mod_orchestra.interpreter import apply_interpretation
from mod_orchestra.state import Store

FIX = Path(__file__).resolve().parents[1] / "fixtures"
HOME.mkdir(parents=True, exist_ok=True)
store = Store()   # the same default database that `craftctl ui` opens

idea = (FIX / "infectious_zombies.idea.txt").read_text(encoding="utf8").strip()
workflow.new_project(store, name="Infectious Zombies", mod_id="infect", package="com.example.infect", idea=idea)
apply_interpretation(store, "infect", {"status": "WAITING_USER", "spec": json.loads((FIX / "infectious_zombies.proposal.json").read_text(encoding="utf8")), "questions": []}, "seed")
workflow.plan_project(store, "infect"); workflow.approve_spec(store, "infect"); workflow.generate_project(store, "infect")

workflow.new_project(store, name="Quiet Gems", mod_id="quiet", package="com.example.quiet", idea="items: ruby, sapphire")
workflow.plan_project(store, "quiet"); workflow.approve_spec(store, "quiet"); workflow.generate_project(store, "quiet")
workflow.new_project(store, name="Draft Opal", mod_id="draft", package="com.example.draft", idea="items: opal, jade")   # not generated: its items can still be removed
workflow.plan_project(store, "draft"); workflow.approve_spec(store, "draft")
print("seeded", [p["id"] for p in store.projects()])
