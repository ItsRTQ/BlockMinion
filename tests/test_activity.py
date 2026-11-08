import tempfile
import time
import unittest
from pathlib import Path

from mod_orchestra import activity, workflow
from mod_orchestra.state import Store
from unittest.mock import patch


class Alive:
    def __init__(self, alive=True): self.alive = alive
    def is_alive(self): return self.alive


class TestDescribeTask(unittest.TestCase):
    def test_every_kind_has_a_sentence_and_a_place_to_look(self):
        cases = {
            "p:SPEC": ("Interpreter · reading your idea and proposing the spec", {"tab": "spec"}),
            "p:MODEL:brute": ("Designer · model of brute", {"tab": "features", "sub": "mobs", "focus": "mob:brute"}),
            "p:ADD_MOB:ape": ("Coder · adding the mob ape", {"tab": "features", "sub": "mobs", "focus": "mob:ape"}),
            "p:SPRITES:1": ("Designer · item icons", {"tab": "features", "sub": "items"}),
            "p:ARMOR:groko": ("Designer · worn armor of groko", {"tab": "features", "sub": "items"}),
            "p:ARMOR3D:groko": ("Designer · 3D armor of groko", {"tab": "features", "sub": "items"}),
            "p:FEATURE:infection": ("Coder · infection", {"tab": "map", "focus": "infection"}),
            "p:CHANGE:infection:2": ("Coder · change on infection", {"tab": "map", "focus": "infection"}),
            "p:REPAIR:1": ("Debugger · repairing the build", {"tab": "activity"}),
            "p:SOMETHING:new_kind": ("Qa · something new kind", {"tab": "activity"}),
        }
        roles = {"p:ADD_MOB:ape": "coder", "p:SOMETHING:new_kind": "qa", "p:SPRITES:1": "designer", "p:ARMOR:groko": "designer", "p:ARMOR3D:groko": "designer"}
        for tid, (label, target) in cases.items():
            d = activity.describe_task(tid, roles.get(tid))
            self.assertEqual((d["label"], d["target"]), (label, target), tid)

    def test_a_task_id_without_a_project_prefix_still_describes(self):
        self.assertEqual(activity.describe_task("weird")["target"], {"tab": "activity"})                    # ids always carry the project, but a stray one never breaks the banner
        self.assertEqual(activity.describe_task("")["target"], {"tab": "activity"})


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "s.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop); (base / "projects").mkdir()
        workflow.new_project(self.store, name="Infectious Zombies", mod_id="infect", package="com.x.i", idea="hostile mobs: brute")
        workflow.new_project(self.store, name="Quiet", mod_id="quiet", package="com.x.q", idea="items: gem")

    def test_only_projects_with_a_live_job_are_running(self):
        now = time.time()
        inflight = {"infect": {"thread": Alive(True), "job": "dispatch", "started": now - 30}, "quiet": {"thread": Alive(False), "job": "build", "started": now - 99}}
        snap = activity.snapshot(self.store, inflight, [], now)
        self.assertEqual(list(snap["projects"]), ["infect"])
        a = snap["projects"]["infect"]
        self.assertEqual((a["running"], a["job"], a["name"], a["elapsed_s"]), (True, "dispatch", "Infectious Zombies", 30.0))
        self.assertEqual(a["step"]["role"], "controller"); self.assertEqual(a["step"]["target"], {"tab": "activity"})      # no agent yet: the controller is starting it

    def test_a_running_agent_gives_its_role_runtime_and_destination(self):
        with self.store.tx() as con:
            con.execute("INSERT INTO runs(id, project_id, task_id, role, provider, state, created_at) VALUES('r1','infect','infect:MODEL:brute','designer','antigravity-cli','RUNNING',?)", (time.time() - 12,))
        a = activity.snapshot(self.store, {"infect": {"thread": Alive(True), "job": "orchestrate", "started": time.time() - 20}}, [])["projects"]["infect"]
        self.assertEqual((a["job_label"], a["step"]["role"], a["step"]["runtime"], a["step"]["label"]), ("Autopilot", "designer", "antigravity-cli", "Designer · model of brute"))
        self.assertEqual(a["step"]["target"], {"tab": "features", "sub": "mobs", "focus": "mob:brute"})

    def test_controller_jobs_say_what_they_do_and_where_the_result_is(self):
        a = activity.snapshot(self.store, {"infect": {"thread": Alive(True), "job": "build", "started": time.time()}}, [])["projects"]["infect"]
        self.assertEqual((a["step"]["label"], a["step"]["target"]), ("Building with Gradle", {"tab": "verify"}))

    def test_finished_jobs_say_whether_they_worked(self):
        now = time.time()
        ok = activity.finished_entry(self.store, "infect", {"job": "dispatch", "started": now - 50, "finished": now - 5, "result": {"task_state": "DONE"}, "error": None})
        self.assertEqual((ok["state"], ok["elapsed_s"], ok["error"]), ("done", 45.0, None))
        wait = activity.finished_entry(self.store, "infect", {"job": "dispatch", "started": now - 50, "finished": now, "result": {"task_state": "WAITING_USER"}})
        self.assertEqual(wait["state"], "waiting")
        bad = activity.finished_entry(self.store, "infect", {"job": "build", "started": now - 50, "finished": now, "error": "gradle exploded " * 40})
        self.assertEqual(bad["state"], "failed"); self.assertLessEqual(len(bad["error"]), 300)
        failed_task = activity.finished_entry(self.store, "infect", {"job": "dispatch", "started": now - 5, "finished": now, "result": {"task_state": "FAILED", "error": "proposal rejected"}})
        self.assertEqual((failed_task["state"], failed_task["error"]), ("failed", "proposal rejected"))

    def test_recent_keeps_the_last_quarter_hour_newest_first(self):
        now = time.time()
        old = {"project": "quiet", "job": "build", "state": "done", "finished_at": now - 3600, "elapsed_s": 1, "step": {}}
        a = {"project": "infect", "job": "dispatch", "state": "done", "finished_at": now - 300, "elapsed_s": 1, "step": {}}
        b = {"project": "infect", "job": "build", "state": "failed", "finished_at": now - 10, "elapsed_s": 1, "step": {}}
        recent = activity.snapshot(self.store, {}, [old, a, b], now)["recent"]
        self.assertEqual([r["job"] for r in recent], ["build", "dispatch"]); self.assertEqual(recent[0]["name"], "Infectious Zombies")


if __name__ == "__main__":
    unittest.main()
