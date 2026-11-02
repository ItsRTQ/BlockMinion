"""UI API (R2 activity feed, U7 verification views): drives the real HTTP server on a free port."""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import dispatch as dmod, ui, workflow
from mod_orchestra.provider import FakeProvider
from mod_orchestra.state import Store, StateError

REPLY = '```handoff\n' + json.dumps({"task": "u_mod:WORK", "status": "WAITING_USER", "scope": "s", "changed_files": [],
        "checks_run": [], "evidence": {"level": "STATIC", "pointer": "src"}, "risks": [], "unknowns": [],
        "needs_user": ["craftctl request-build u_mod"], "next_agent": "none"}) + '\n```'


class UiApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name); cls.store = Store(base / "state.sqlite")
        cls.p1 = patch.object(workflow, "PROJECTS", base / "projects"); cls.p1.start(); (base / "projects").mkdir()
        cls.p2 = patch.object(dmod, "provider_from_env", lambda: FakeProvider(REPLY)); cls.p2.start()
        cls.p3 = patch.object(ui.webbrowser, "open", lambda *a, **k: None); cls.p3.start()
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); cls.port = sock.getsockname()[1]
        cls.token_holder = {}
        real_token = ui.secrets.token_urlsafe
        def capture(n=32):
            t = real_token(n); cls.token_holder.setdefault("t", t); return t
        cls.p4 = patch.object(ui.secrets, "token_urlsafe", capture); cls.p4.start()
        cls.thread = threading.Thread(target=ui.serve, args=(cls.store, cls.port), daemon=True); cls.thread.start()
        deadline = time.time() + 15  # slow CI runners: wait until the server actually accepts connections
        while time.time() < deadline:
            if "t" in cls.token_holder:
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            time.sleep(0.1)
        else:
            raise RuntimeError("UI server did not start in time")
        workflow.new_project(cls.store, name="U", mod_id="u_mod", package="com.x.u", idea="items: gem")
        workflow.plan_project(cls.store, "u_mod"); workflow.approve_spec(cls.store, "u_mod")
        cls.store.add_task("u_mod", "u_mod:WORK", "coder", "ad-hoc coder work")

    @classmethod
    def tearDownClass(cls):
        for p in (cls.p1, cls.p2, cls.p3, cls.p4): p.stop()
        cls.tmp.cleanup()

    def call(self, path, payload=None, origin=True):
        headers = {"Authorization": "Bearer " + self.token_holder["t"]}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"; data = json.dumps(payload).encode()
            if origin: headers["Origin"] = f"http://127.0.0.1:{self.port}"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_1_verification_endpoints_before_source(self):
        self.assertEqual(self.call("/api/project/u_mod/validate")[1]["status"], "NO_SOURCE")
        self.assertEqual(self.call("/api/project/u_mod/diagnose")[1]["status"], "NO_LOG")
        self.assertEqual(self.call("/api/project/u_mod/runs")[1], [])
        self.assertEqual(self.call("/api/project/u_mod/bogus")[0], 400)

    def test_2_dispatch_runs_in_background_and_is_single_flight(self):
        code, out = self.call("/api/project/u_mod/dispatch", {})
        self.assertEqual((code, out["started"]), (200, True))
        for _ in range(40):
            runs = self.call("/api/project/u_mod/runs")[1]
            if runs and runs[0]["state"] != "RUNNING": break
            time.sleep(0.1)
        self.assertEqual(runs[0]["state"], "WAITING_USER")
        self.assertEqual(runs[0]["handoff"]["needs_user"], ["craftctl request-build u_mod"])
        detail = self.call("/api/run/" + runs[0]["id"])[1]
        self.assertIn("handoff", detail["log_tail"])
        self.assertFalse(self.call("/api/project/u_mod")[1]["dispatching"])

    def test_3_requeue_and_evidence_from_ui(self):
        code, out = self.call("/api/task/u_mod:WORK/requeue", {})
        self.assertEqual((code, out["state"]), (200, "READY"))
        code, out = self.call("/api/project/u_mod/evidence", {"level": "CLIENT_BOOT_PASS", "note": "x"})
        self.assertEqual(code, 400); self.assertIn("cannot be attached", out["error"])

    def test_4_post_without_origin_is_refused(self):
        self.assertEqual(self.call("/api/project/u_mod/dispatch", {}, origin=False)[0], 403)


if __name__ == "__main__":
    unittest.main()


class GuidanceGalleryFeedback(unittest.TestCase):
    """Server-side guidance, model gallery, authenticated file route and the feedback loop."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        from mod_orchestra import redact as redact_mod
        p2 = patch.object(redact_mod, "PROJECTS", base / "projects"); p2.start(); self.addCleanup(p2.stop)
        self.proj = workflow.new_project(self.store, name="G", mod_id="g_mod", package="com.x.g", idea="items: gem; mobs: sky critter; tab: Sky")

    def g(self):
        from mod_orchestra.guidance import guidance
        return guidance(self.store, "g_mod")

    def test_stages_follow_the_pipeline(self):
        self.assertEqual(self.g()["stage"], "spec"); self.assertEqual(self.g()["steps"][0]["action"], "approve")
        workflow.approve_spec(self.store, "g_mod"); self.assertEqual(self.g()["stage"], "source"); self.assertEqual(self.g()["steps"][0]["action"], "generate")
        workflow.generate_project(self.store, "g_mod"); g = self.g()
        self.assertEqual(g["stage"], "model"); self.assertEqual(g["steps"][0]["payload"]["task"], "g_mod:MODEL:sky_critter")
        # designer delivers (fake) -> build stage with request-build
        root = Path(self.proj["root"]); (root / "models").mkdir()
        from mod_orchestra.geckolib import placeholder_geo, placeholder_animation; from mod_orchestra.spec import Mob; from mod_orchestra.fabric import placeholder_png
        m = Mob(identifier="sky_critter", label="x")
        (root / "models/sky_critter.bbmodel").write_text("{}"); (root / "models/sky_critter.geo.json").write_text(json.dumps(placeholder_geo(m)))
        (root / "models/sky_critter.animation.json").write_text(json.dumps(placeholder_animation(m))); (root / "models/sky_critter.png").write_bytes(placeholder_png("t", 64, 32))
        (root / "models/sky_critter_rest.png").write_bytes(placeholder_png("r", 32, 32))
        h = {"task": "g_mod:MODEL:sky_critter", "status": "DONE", "scope": "s", "changed_files": ["models/sky_critter.geo.json"], "checks_run": [], "evidence": {"level": "STATIC", "pointer": "m"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "coder"}
        from mod_orchestra.dispatch import dispatch
        dispatch(self.store, "g_mod", task_id="g_mod:MODEL:sky_critter", provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))
        g = self.g(); self.assertEqual(g["stage"], "build"); self.assertEqual(g["steps"][0]["action"], "request-build")
        from mod_orchestra import build as build_mod
        a = build_mod.request_build(self.store, "g_mod"); self.assertEqual(self.g()["steps"][0]["action"], "decide")
        self.store.decide_approval(a["id"], True); self.assertEqual(self.g()["steps"][0]["action"], "build")

    def test_gallery_and_feedback(self):
        from mod_orchestra.feedback import model_gallery, give_model_feedback, file_for_ui
        from mod_orchestra.validation import InputError
        workflow.approve_spec(self.store, "g_mod"); workflow.generate_project(self.store, "g_mod")
        gal = model_gallery(self.store, "g_mod")[0]
        self.assertTrue(gal["placeholder"]); self.assertEqual(gal["task_state"], "READY"); self.assertEqual(gal["previews"], [])
        root = Path(self.proj["root"]); (root / "models").mkdir(); (root / "models/sky_critter_rest.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        self.assertEqual(model_gallery(self.store, "g_mod")[0]["previews"], ["models/sky_critter_rest.png"])
        path, ctype = file_for_ui(self.store, "g_mod", "models/sky_critter_rest.png"); self.assertEqual(ctype, "image/png")
        for bad in ("../../state.sqlite", "src/main/java/com/x/g/ModMain.java", "build.gradle", "models/../build.gradle"):
            with self.assertRaises(InputError):
                file_for_ui(self.store, "g_mod", bad)
        # feedback on a DONE task reopens it and reaches the next designer packet
        with self.store.tx() as con:
            con.execute("UPDATE tasks SET state='DONE' WHERE id='g_mod:MODEL:sky_critter'")
        out = give_model_feedback(self.store, "g_mod", "sky_critter", "wings too big")
        self.assertEqual(out["state"], "READY")
        from mod_orchestra.feedback import feedback_context
        self.assertIn("wings too big", feedback_context(self.store, "g_mod", "sky_critter"))
        self.assertEqual(model_gallery(self.store, "g_mod")[0]["feedback"][0]["text"], "wings too big")
        with self.assertRaisesRegex(InputError, "Unknown mob"):
            give_model_feedback(self.store, "g_mod", "dragon", "x")

    def test_replan_on_approval_picks_up_spec_changes(self):
        workflow.plan_project(self.store, "g_mod")
        self.assertNotIn("g_mod:MODEL:shadow", {t["id"] for t in self.store.tasks("g_mod")})
        from mod_orchestra.specedit import add_mob
        add_mob(self.store, "g_mod", identifier="shadow", label="Shadow", behavior="hostile")
        workflow.approve_spec(self.store, "g_mod")
        ids = {t["id"] for t in self.store.tasks("g_mod")}
        self.assertIn("g_mod:MODEL:shadow", ids); self.assertIn("g_mod:MODEL:sky_critter", ids)
        self.assertEqual(next(t["state"] for t in self.store.tasks("g_mod") if t["id"] == "g_mod:SPEC"), "DONE")
        self.assertIn("TASK_GRAPH_REPLANNED", [e["kind"] for e in self.store.events("g_mod")])


class DeleteFromUi(unittest.TestCase):
    def test_delete_requires_exact_id_and_removes_project(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            proj = workflow.new_project(store, name="D", mod_id="d_mod", package="com.x.d", idea="items: gem")
            root = Path(proj["root"]); root.mkdir(parents=True, exist_ok=True); (root / "x.txt").write_text("x")
            out = workflow.delete_project(store, "d_mod", remove_workspace=True)
            self.assertTrue(out["workspace_removed"]); self.assertFalse(root.exists())
            with self.assertRaises(StateError):
                store.project("d_mod")


class DeleteWithRunsAndInstructions(unittest.TestCase):
    def test_delete_removes_every_dependent_row(self):
        # host run 11: FOREIGN KEY constraint failed — runs and task_instructions were not deleted.
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            workflow.new_project(store, name="D", mod_id="d_mod", package="com.x.d", idea="items: gem; mobs: fox")
            workflow.plan_project(store, "d_mod"); workflow.approve_spec(store, "d_mod"); workflow.generate_project(store, "d_mod")
            h = {"task": "d_mod:MODEL:fox", "status": "FAILED", "scope": "s", "changed_files": [], "checks_run": [], "evidence": {"level": "NONE", "pointer": "-"}, "risks": ["x"], "unknowns": [], "needs_user": [], "next_agent": "none"}
            dmod.dispatch(store, "d_mod", task_id="d_mod:MODEL:fox", provider=FakeProvider("```handoff\n" + json.dumps(h) + "\n```"))
            from mod_orchestra.content import add_feature
            add_feature(store, "d_mod", kind="item", label="Moon Shard")  # creates a task with task_instructions
            self.assertTrue(store.runs("d_mod")); self.assertTrue(store.task_instructions("d_mod:ADD_ITEM:moon_shard"))
            out = workflow.delete_project(store, "d_mod", remove_workspace=True)
            self.assertGreaterEqual(out["rows"]["runs"], 1); self.assertGreaterEqual(out["rows"]["task_instructions"], 1)
            self.assertEqual(store.projects(), [])


class PercentEncodedIds(unittest.TestCase):
    def test_requeue_accepts_encoded_task_id(self):
        # host run 11: "Task not found: ovis_moon%3ASPEC" — the path segment was not URL-decoded.
        import mod_orchestra.ui as uimod
        from urllib.parse import unquote
        self.assertIn("unquote(", __import__("inspect").getsource(uimod.serve))
        self.assertEqual(unquote("ovis_moon%3ASPEC"), "ovis_moon:SPEC")


class ReplanKeepsUserTasks(unittest.TestCase):
    def test_add_task_survives_approve_spec_replan(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            workflow.new_project(store, name="K", mod_id="k_mod", package="com.x.k", idea="items: gem")
            workflow.plan_project(store, "k_mod")
            store.add_task("k_mod", "k_mod:EXTRA", "coder", "user-added", after=["k_mod:SPEC"])
            workflow.approve_spec(store, "k_mod")
            ids = {t["id"]: t for t in store.tasks("k_mod")}
            self.assertIn("k_mod:EXTRA", ids); self.assertEqual(ids["k_mod:SCAFFOLD"]["role"], "controller"); self.assertEqual(ids["k_mod:CONTENT:01"]["role"], "controller")
            self.assertEqual(ids["k_mod:EXTRA"]["state"], "READY", "edge from the (DONE) SPEC task survived")


class ExpiredApprovals(unittest.TestCase):
    def test_guidance_ignores_expired_pending_approval(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            workflow.new_project(store, name="E", mod_id="e_mod", package="com.x.e", idea="items: gem")
            workflow.plan_project(store, "e_mod"); workflow.approve_spec(store, "e_mod"); workflow.generate_project(store, "e_mod")
            from mod_orchestra import build as build_mod
            from mod_orchestra.guidance import guidance
            a = build_mod.request_build(store, "e_mod")
            self.assertEqual(guidance(store, "e_mod")["steps"][0]["action"], "decide")
            with store.tx() as con:
                con.execute("UPDATE approvals SET expires_at=? WHERE id=?", (time.time() - 1, a["id"]))
            self.assertEqual(guidance(store, "e_mod")["steps"][0]["action"], "request-build", "expired approvals must not be offered")


class FrontendConsistency(unittest.TestCase):
    """The static files must move together: every element id app.js reads with qs("…") must exist in index.html,
    and every handler the HTML expects must be wired (regression: an Items rewrite dropped the sprites modal code)."""
    def test_every_qs_id_exists_in_html_and_key_handlers_are_wired(self):
        import re
        static = Path(__file__).resolve().parents[1] / "src" / "mod_orchestra" / "static"
        html = (static / "index.html").read_text(encoding="utf8"); js = (static / "app.js").read_text(encoding="utf8")
        ids = set(re.findall(r'id="([^"]+)"', html))
        used = set(re.findall(r'qs\("([a-zA-Z0-9_-]+)"\)', js))
        missing = sorted(u for u in used if u not in ids)
        self.assertEqual(missing, [], f"app.js references ids absent from index.html: {missing}")
        for handler in ("sprites-btn", "sprites-go", "addmob-form", "addmat-form", "addfood-form", "p-delete", "del-go", "theme-save", "pol-all"):
            self.assertRegex(js, re.escape(f'qs("{handler}")') + r"\.(onclick|onsubmit)", f"{handler} has no handler")
        self.assertIn('const addForm = qs("addfeature-form");', js); self.assertIn("addForm.onsubmit", js)
        self.assertIn("let featureCache", js)
