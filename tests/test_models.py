"""R6 slice 2: MODEL tasks, designer MCP wiring, deliverable validation and installation."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import provider as pmod, workflow
from mod_orchestra.dispatch import dispatch
from mod_orchestra.models import SAFE_DIR, SAFE_SERVER, blockbench_server_config, install_model, validate_model_files
from mod_orchestra.geckolib import placeholder_geo, placeholder_animation
from mod_orchestra.fabric import placeholder_png
from mod_orchestra.provider import FakeProvider, TaskEnvelope
from mod_orchestra.spec import Mob
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError

ROOT = Path(__file__).resolve().parents[1]
IDEA = "items: gem; mobs: sky critter; tab: Critters"


def handoff(task, status="DONE", files=()):
    h = {"task": task, "status": status, "scope": "model", "changed_files": list(files),
         "checks_run": [{"command": "bbmodel_geckolib_validate require_idle_walk", "exit_code": 0}],
         "evidence": {"level": "STATIC", "pointer": "models/"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "coder"}
    return "```handoff\n" + json.dumps(h) + "\n```"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="C", mod_id="c_mod", package="com.x.c", idea=IDEA)
        workflow.plan_project(self.store, "c_mod"); workflow.approve_spec(self.store, "c_mod"); workflow.generate_project(self.store, "c_mod")
        self.ws = Path(proj["root"]); self.models = self.ws / "models"; self.models.mkdir(exist_ok=True)

    def deliver(self, mob="sky_critter", geo=None, anim=None, png=None):
        m = Mob(identifier=mob, label="x")
        (self.models / f"{mob}.bbmodel").write_text("{}")
        (self.models / f"{mob}.geo.json").write_text(json.dumps(geo or placeholder_geo(m)))
        (self.models / f"{mob}.animation.json").write_text(json.dumps(anim or placeholder_animation(m)))
        (self.models / f"{mob}.png").write_bytes(png or placeholder_png("t", 64, 64))


class Planning(Base):
    def test_model_task_sits_between_scaffold_and_build(self):
        tasks = {t["id"]: t for t in self.store.tasks("c_mod")}
        self.assertEqual(tasks["c_mod:MODEL:sky_critter"]["role"], "designer")
        self.assertEqual(tasks["c_mod:MODEL:sky_critter"]["state"], "READY")  # SCAFFOLD done by generate
        self.assertEqual(tasks["c_mod:BUILD"]["state"], "BACKLOG")

    def test_designer_run_gets_the_blockbench_server_and_instructions(self):
        captured = {}
        def fake_run(cmd, *, cwd, log, timeout, env, stdin_text=None):
            for i, a in enumerate(cmd):
                if a == "--mcp-config": captured["mcp"] = json.loads(Path(cmd[i + 1]).read_text())
            captured["prompt"] = stdin_text
            log.parent.mkdir(parents=True, exist_ok=True); log.write_text("$ x\n" + json.dumps({"result": handoff("c_mod:MODEL:sky_critter", "FAILED")}))
            return {"pid": 1, "exit_code": 0, "killed": False, "timeout_s": timeout, "duration_s": 1.0, "cmd": cmd}
        with patch.object(pmod, "run_logged", fake_run):
            prov = pmod.ClaudeCodeProvider(binary="claude-fake")
            env = TaskEnvelope("c_mod", "c_mod:MODEL:sky_critter", "designer", "t", self.ws, "# packet", "## Your job on this task (designer)")
            prov.run(env, self.ws / ".mod-orchestra/runs/r.log")
        srv = captured["mcp"]["mcpServers"]["blockbench"]
        self.assertEqual(srv["command"], "node"); self.assertEqual(Path(srv["args"][0]), SAFE_SERVER)
        self.assertEqual(srv["args"][1:], ["--root", str(self.ws / "models"), "--allow-write"])
        self.assertIn("minecraft-orchestra", captured["mcp"]["mcpServers"])
        self.assertIn("designer", captured["prompt"])


class Deliverables(Base):
    def test_valid_set_passes_and_installs_over_placeholders(self):
        self.deliver()
        out = dispatch(self.store, "c_mod", task_id="c_mod:MODEL:sky_critter", provider=FakeProvider(handoff("c_mod:MODEL:sky_critter", files=["models/sky_critter.geo.json"])))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        res = self.ws / "src/main/resources/assets/c_mod"
        self.assertEqual(json.loads((res / "geo/entity/sky_critter.geo.json").read_text())["minecraft:geometry"][0]["description"]["identifier"], "geometry.sky_critter")
        self.assertTrue((res / "animations/entity/sky_critter.animation.json").is_file())
        self.assertIn("MODEL_INSTALLED", [e["kind"] for e in self.store.events("c_mod")])
        from mod_orchestra.fabric import validate_generated
        self.assertEqual(validate_generated(self.ws)["status"], "PASS", "installed files must be accepted as a revision")
        from mod_orchestra.rigs import recipe
        self.assertEqual(out["handoff"]["model"]["bones"], sorted(b["name"] for b in recipe("quadruped")["bones"]))
        self.assertTrue((self.models / "sky_critter.bbmodel").is_file(), "editable source stays in models/")

    def test_missing_or_wrong_deliverables_fail_the_task_with_reason(self):
        out = dispatch(self.store, "c_mod", task_id="c_mod:MODEL:sky_critter", provider=FakeProvider(handoff("c_mod:MODEL:sky_critter")))
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("deliverables missing", out["error"])
        self.store.requeue("c_mod:MODEL:sky_critter", "retry")
        geo = placeholder_geo(Mob(identifier="other", label="x"))  # wrong identifier
        self.deliver(geo=geo)
        with self.assertRaisesRegex(InputError, "geometry.sky_critter"):
            validate_model_files(self.ws, "sky_critter")
        anim = placeholder_animation(Mob(identifier="sky_critter", label="x")); anim["animations"]["animation.sky_critter.walk"]["bones"]["antenna_zz"] = {}
        self.deliver(anim=anim)
        with self.assertRaisesRegex(InputError, "not in geo.json"):
            validate_model_files(self.ws, "sky_critter")
        self.deliver(png=placeholder_png("t", 32, 32))
        with self.assertRaisesRegex(InputError, "geo declares 64x64"):
            validate_model_files(self.ws, "sky_critter")
        bad = placeholder_animation(Mob(identifier="sky_critter", label="x")); del bad["animations"]["animation.sky_critter.idle"]
        self.deliver(anim=bad)
        with self.assertRaisesRegex(InputError, "lacks animation.sky_critter.idle"):
            validate_model_files(self.ws, "sky_critter")
        two_roots = placeholder_geo(Mob(identifier="sky_critter", label="x")); del two_roots["minecraft:geometry"][0]["bones"][1]["parent"]
        self.deliver(geo=two_roots)
        with self.assertRaisesRegex(InputError, "exactly one root"):
            validate_model_files(self.ws, "sky_critter")
        overflow = placeholder_geo(Mob(identifier="sky_critter", label="x")); overflow["minecraft:geometry"][0]["bones"][1]["cubes"][0]["uv"] = [60, 60]
        self.deliver(geo=overflow)
        with self.assertRaisesRegex(InputError, "leaves the 64x64 texture"):
            validate_model_files(self.ws, "sky_critter")
        self.deliver(geo=placeholder_geo(Mob(identifier="sky_critter", label="x")))
        late = placeholder_animation(Mob(identifier="sky_critter", label="x")); late["animations"]["animation.sky_critter.walk"]["bones"]["head"] = {"rotation": {"0.0": [0, 0, 0], "5.0": [1, 0, 0]}}
        self.deliver(anim=late)
        with self.assertRaisesRegex(InputError, "outside the clip length"):
            validate_model_files(self.ws, "sky_critter")
        no_attack = placeholder_animation(Mob(identifier="sky_critter", label="x")); del no_attack["animations"]["animation.sky_critter.attack"]
        self.deliver(anim=no_attack)
        validate_model_files(self.ws, "sky_critter")  # passive: attack optional
        with self.assertRaisesRegex(InputError, "lacks animation.sky_critter.attack"):
            validate_model_files(self.ws, "sky_critter", "hostile")


class VendoredServer(unittest.TestCase):
    def test_packaged_copy_matches_tools_dir(self):
        for rel in ["package.json", "SHA256SUMS.txt"] + [f"src/{p.name}" for p in (ROOT / "tools/blockbench-mcp-safe/src").glob("*.mjs")]:
            self.assertEqual((ROOT / "tools/blockbench-mcp-safe" / rel).read_bytes(), (SAFE_DIR / rel).read_bytes(), rel)

    def test_server_has_no_dependencies_and_no_network_or_exec(self):
        pkg = json.loads((SAFE_DIR / "package.json").read_text())
        self.assertFalse(pkg.get("dependencies")); self.assertEqual(pkg.get("license"), "MIT")
        src = "\n".join(p.read_text(encoding="utf8") for p in (SAFE_DIR / "src").glob("*.mjs"))
        for bad in ("child_process", "fetch(", "new Function", "node:http", "node:net", "eval("):
            self.assertNotIn(bad, src, bad)

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_server_starts_and_lists_tools(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        cfg = blockbench_server_config(Path(tmp.name))
        p = subprocess.Popen([cfg["command"]] + cfg["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}) + "\n")
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"); p.stdin.flush()
        tools = None
        for _ in range(10):
            line = p.stdout.readline()
            try: msg = json.loads(line)
            except Exception: continue
            if msg.get("id") == 2: tools = [t["name"] for t in msg["result"]["tools"]]; break
        p.stdin.close(); p.wait(timeout=10)
        self.assertIsNotNone(tools)
        for needed in ("bbmodel_geckolib_create", "bbmodel_edit", "bbmodel_geckolib_upsert_animation", "bbmodel_geckolib_validate",
                       "bbmodel_geckolib_export_geometry", "bbmodel_geckolib_export_animations", "bbmodel_geckolib_set_texture", "bbmodel_render"):
            self.assertIn(needed, tools)


if __name__ == "__main__":
    unittest.main()


class PreviewHistory(Base):
    def test_each_installed_model_keeps_its_previews_as_a_version(self):
        from mod_orchestra.feedback import model_gallery, file_for_ui
        self.deliver(); (self.models / "sky_critter_rest.png").write_bytes(placeholder_png("r", 32, 32))
        out = dispatch(self.store, "c_mod", task_id="c_mod:MODEL:sky_critter", provider=FakeProvider(handoff("c_mod:MODEL:sky_critter")))
        self.assertEqual(out["task_state"], "DONE")
        gal = model_gallery(self.store, "c_mod")[0]
        self.assertEqual(len(gal["versions"]), 1); self.assertEqual(gal["versions"][0]["run"], out["run"])
        self.assertTrue(any(p.endswith("sky_critter_rest.png") for p in gal["versions"][0]["previews"]))
        path, ctype = file_for_ui(self.store, "c_mod", gal["versions"][0]["previews"][0]); self.assertEqual(ctype, "image/png")


class AddMobAfterGeneration(Base):
    def test_files_tasks_and_instructions(self):
        from mod_orchestra.models import add_mob_after_generation
        from mod_orchestra.fabric import validate_generated
        out = add_mob_after_generation(self.store, "c_mod", Mob(identifier="moon_fox", label="Moon Fox", behavior="hostile", drops=("gem",)))
        self.assertEqual(out["tasks"], ["c_mod:ADD_MOB:moon_fox", "c_mod:MODEL:moon_fox"]); self.assertFalse(out["first_mob"])
        self.assertTrue((self.ws / "src/main/java/com/x/c/entity/MoonFoxEntity.java").is_file())
        self.assertTrue((self.ws / "src/main/resources/assets/c_mod/geo/entity/moon_fox.geo.json").is_file())
        self.assertTrue((self.ws / "src/main/resources/assets/c_mod/models/item/moon_fox_spawn_egg.json").is_file())
        lang = json.loads((self.ws / "src/main/resources/assets/c_mod/lang/en_us.json").read_text())
        self.assertEqual(lang["entity.c_mod.moon_fox"], "Moon Fox"); self.assertIn("entity.c_mod.sky_critter", lang)
        self.assertEqual(validate_generated(self.ws)["status"], "PASS", "new files are an accepted revision")
        spec = self.store.project("c_mod")["spec"]; self.assertEqual([m["identifier"] for m in spec["mobs"]], ["sky_critter", "moon_fox"])
        tasks = {t["id"]: t for t in self.store.tasks("c_mod")}
        self.assertEqual(tasks["c_mod:ADD_MOB:moon_fox"]["state"], "READY"); self.assertEqual(tasks["c_mod:MODEL:moon_fox"]["state"], "BACKLOG")
        instr = self.store.task_instructions("c_mod:ADD_MOB:moon_fox")
        self.assertIn("MoonFoxEntity", instr); self.assertIn("MobCategory.MONSTER", instr); self.assertIn("EntityRendererRegistry.register", instr)
        self.assertNotIn("first mob", instr)
        with self.assertRaisesRegex(InputError, "already exists"):
            add_mob_after_generation(self.store, "c_mod", Mob(identifier="moon_fox", label="x"))

    def test_first_mob_instructions_include_geckolib_setup_and_coder_done_reopens_build(self):
        from mod_orchestra.models import add_mob_after_generation
        from mod_orchestra import workflow as wf
        wf.new_project(self.store, name="P", mod_id="p_mod", package="com.x.p", idea="items: gem")
        wf.plan_project(self.store, "p_mod"); wf.approve_spec(self.store, "p_mod"); wf.generate_project(self.store, "p_mod")
        with self.store.tx() as con:
            con.execute("UPDATE tasks SET state='DONE' WHERE id='p_mod:BUILD'")
        out = add_mob_after_generation(self.store, "p_mod", Mob(identifier="glow_slime", label="Glow Slime"))
        self.assertTrue(out["first_mob"]); self.assertIn("GeckoLib repository", self.store.task_instructions("p_mod:ADD_MOB:glow_slime"))
        fake = FakeProvider(handoff("p_mod:ADD_MOB:glow_slime", files=["src/main/java/com/x/p/ModMain.java"]))
        res = dispatch(self.store, "p_mod", task_id="p_mod:ADD_MOB:glow_slime", provider=fake)
        self.assertEqual(res["task_state"], "DONE"); self.assertIn("Task-specific instructions", fake.envelopes[0].extra_instructions)
        states = {t["id"]: t["state"] for t in self.store.tasks("p_mod")}
        self.assertEqual(states["p_mod:MODEL:glow_slime"], "READY"); self.assertNotEqual(states["p_mod:BUILD"], "DONE")


class OpenInBlockbench(Base):
    def test_open_model_uses_the_system_opener_and_validates(self):
        from mod_orchestra.feedback import open_in_blockbench
        with self.assertRaisesRegex(InputError, "No .bbmodel"):
            open_in_blockbench(self.store, "c_mod", "sky_critter")
        self.deliver()
        import mod_orchestra.feedback as fb
        opened = {}
        import os as _os
        with patch("subprocess.Popen", lambda cmd, **k: opened.setdefault("cmd", list(cmd))), patch.object(fb, "find_blockbench", return_value=None), \
             patch("sys.platform", "linux"), patch.object(_os, "startfile", lambda path: opened.setdefault("cmd", ["startfile", str(path)]), create=True):
            out = open_in_blockbench(self.store, "c_mod", "sky_critter")
        self.assertTrue(out["opened"].endswith("sky_critter.bbmodel")); self.assertIn(opened["cmd"][0], ("xdg-open", "startfile"))
        self.assertIn("OPENED_IN_BLOCKBENCH", [e["kind"] for e in self.store.events("c_mod")])
        with self.assertRaisesRegex(InputError, "Unknown mob"):
            open_in_blockbench(self.store, "c_mod", "dragon")
