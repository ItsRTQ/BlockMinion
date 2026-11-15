"""The coder's skills by task: a run loads what its request touches; the rest stay one tool call away."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mod_orchestra.provider as pmod
from mod_orchestra import skillset
from mod_orchestra.artreq import CODER_ART_RULE
from mod_orchestra.dispatch import build_envelope
from mod_orchestra.mcp import handle
from mod_orchestra.modmap import request_change, request_feature
from mod_orchestra.provider import ClaudeCodeProvider, TaskEnvelope, _load_agent_definitions, _role_prompt
from mod_orchestra.shape import CODER_SHAPE_RULE

from test_art_requests import Base

ROOT = Path(__file__).resolve().parents[1]

# What a user asks for, and the topical skills that request needs. Measured before the vocabulary was accepted: no request
# here may miss a skill it needs (a miss is a guessed API); a few extra skills are allowed (an extra is only text).
CORPUS = [
    ("the spitter spits acid that burns the player for 5 seconds", {"effects", "items"}),
    ("add a backpack with 27 slots that opens with right click", {"gui", "items"}),
    ("pressing R reloads the rifle; ammo count shows above the hotbar", {"client-ui", "items", "data"}),
    ("a mana bar on the HUD that refills over time and is saved per player", {"client-ui", "data"}),
    ("the ruby ore should generate deeper, below y 16", {"worldgen"}),
    ("craft the wand from two sticks and a gem", {"recipes", "items"}),
    ("zombies sometimes drop the gem; dungeon chests have it too", {"loot-and-trades"}),
    ("add /heal that restores the health of the player who runs it", {"commands", "effects"}),
    ("when the boss dies, spawn particles and grant an advancement", {"polish"}),
    ("make the player fall slower: change vanilla gravity while the cape is worn", {"mixins"}),
    ("a minimap in the corner showing nearby mobs", {"minimap"}),
    ("the brute attacks twice as fast when below half health", set()),
    ("make it deal 2 more damage", set()),
    ("villagers sell the charm for 5 emeralds", {"loot-and-trades", "items"}),
    ("a furnace-like machine with a GUI that smelts twice as fast and uses energy", {"gui", "recipes", "data"}),
    ("the sword gets a new enchantment that freezes enemies", {"effects", "items"}),
    ("a potion of night vision that lasts 3 minutes", {"effects"}),
    ("add a config option to turn the explosions off", {"polish"}),
    ("the grenade is thrown and explodes after 3 seconds with smoke", {"items", "polish"}),
    ("a new dimension reached through a portal lit with the gem", {"worldgen"}),
    ("the staff has a cooldown of 10 seconds shown in the tooltip", {"items", "data"}),
    ("levels: killing mobs gives xp and each level unlocks more damage", {"data"}),
    ("a crosshair that changes when aiming with the scope", {"client-ui"}),
    ("the pet follows its owner and sits when told", set()),
    ("structures: a ruined tower with a chest of loot", {"worldgen", "loot-and-trades"}),
]


CORPUS_ES = [
    ("el spitter escupe ácido que quema al jugador por 5 segundos", {"effects", "items"}),
    ("agrega una mochila con 27 ranuras que se abre con clic derecho", {"gui", "items"}),
    ("al presionar R se recarga el rifle; la munición se ve arriba de la hotbar", {"client-ui", "items", "data"}),
    ("una barra de maná en pantalla que se rellena con el tiempo y se guarda por jugador", {"client-ui", "data"}),
    ("la mena de rubí debe generarse más abajo, bajo y 16", {"worldgen"}),
    ("la varita se craftea con dos palos y una gema", {"recipes", "items"}),
    ("los zombies a veces sueltan la gema; los cofres de mazmorras también la traen", {"loot-and-trades"}),
    ("un comando /curar que cura al jugador que lo usa", {"commands", "effects"}),
    ("cuando muere el jefe salen partículas y se da un logro", {"polish"}),
    ("que el jugador caiga más lento: cambia la gravedad mientras lleva la capa", {"mixins"}),
    ("un minimapa en la esquina con los mobs cercanos", {"minimap"}),
    ("que haga 2 más de daño", set()),
    ("el brute ataca el doble de rápido con menos de media vida", set()),
    ("los aldeanos venden el amuleto por 5 esmeraldas", {"loot-and-trades"}),
    ("una poción de visión nocturna que dura 3 minutos", {"effects"}),
    ("la granada se lanza y explota a los 3 segundos con humo", {"items", "polish"}),
    ("niveles: matar mobs da experiencia y cada nivel desbloquea más daño", {"data"}),
    ("una dimensión nueva a la que se entra por un portal", {"worldgen"}),
]


class Vocabulary(unittest.TestCase):
    def test_a_request_in_spanish_finds_the_same_skills(self):
        extra = 0
        for text, want in CORPUS_ES:
            got = set(skillset.choose(text))
            self.assertFalse(want - got, f"{text!r} needs {sorted(want - got)}")
            extra += len(got - want)
        self.assertLessEqual(extra, 8)
        self.assertEqual(set(skillset.TOPICS_ES), set(skillset.TOPICS))
        self.assertEqual(skillset.choose("el año pasado comió poco"), [], "accented letters are letters: `com` inside a word is not `come`")
        self.assertEqual(skillset.choose("Hostile GeckoLib mob (10.0 HP, velocidad 0.25)"), [])

    def test_no_request_misses_a_skill_it_needs_and_few_load_one_they_do_not(self):
        extra = 0
        for text, want in CORPUS:
            got = set(skillset.choose(text))
            self.assertFalse(want - got, f"{text!r} needs {sorted(want - got)}")
            extra += len(got - want)
        self.assertLessEqual(extra, 10, "the vocabulary got loose: skills are loaded for requests that do not touch them")

    def test_a_path_is_not_a_command_and_words_are_whole(self):
        self.assertEqual(skillset.choose("files: src/main/java/com/x/Thing.java, /tmp/run/log.txt"), [])
        self.assertIn("commands", skillset.choose("add /heal for admins"))
        self.assertEqual(skillset.choose("the scorekeeper restores the storefront"), [], "a word that only contains a keyword is not that keyword")

    def test_every_skill_of_the_coder_is_core_or_has_a_subject(self):
        for folder in (".claude", "src/mod_orchestra/resources/claude"):
            head = (ROOT / folder / "agents/coder.md").read_text(encoding="utf8").split("\n---\n")[0]
            listed = [l.strip()[2:] for l in head.splitlines() if l.strip().startswith("- ")]
            self.assertEqual(set(listed), set(skillset.CORE) | set(skillset.TOPICS), "a skill added to the coder needs its words in skillset.TOPICS (or a place in CORE)")
            self.assertIn("mcp__minecraft-orchestra__orchestra_skill", head)


class Briefs(Base):
    def test_only_the_users_part_of_a_brief_is_read(self):
        rules = "\n".join(CODER_SHAPE_RULE + CODER_ART_RULE)
        self.assertTrue(set(skillset.choose(rules)) >= {"gui", "effects", "items", "polish"}, "the fixed rules name every kind of thing: reading them would load everything")
        change = request_change(self.store, "s_mod", "spitter", "make it a little faster")["task"]
        many = request_change(self.store, "s_mod", "spitter", "both hit harder", ["acid_spit"])["task"]
        for tid in (self.feature, change, many):
            brief = build_envelope(self.store, "s_mod", self.task(tid)).extra_instructions
            part = skillset.request_part(brief)
            self.assertIsNotNone(part, tid); self.assertNotIn("Shape (build it", part); self.assertNotIn("Art: this mod never borrows", part); self.assertNotIn("gradlew", part)
        self.assertIn("make it a little faster", skillset.request_part(self.store.task_instructions(change)))
        self.assertIn("both hit harder", skillset.request_part(self.store.task_instructions(many)))
        self.assertIn("a hit player burns", skillset.request_part(self.store.task_instructions(self.feature)))
        cap = request_feature(self.store, "s_mod", title="Leap", description="jumps at its target", acceptance=["it lands"], kind="capability", carriers=["spitter"])["task"]
        self.assertNotIn("reusable component", skillset.request_part(self.store.task_instructions(cap)))

    def test_a_request_about_nothing_in_particular_loads_the_core_alone(self):
        tid = request_change(self.store, "s_mod", "spitter", "make it a little faster")["task"]
        env = build_envelope(self.store, "s_mod", self.task(tid))
        self.assertEqual(env.skills, ["coder", "gametest", "events"])
        tid = request_change(self.store, "s_mod", "gem", "right click throws it and it explodes with particles")["task"]
        self.assertEqual(build_envelope(self.store, "s_mod", self.task(tid)).skills, ["coder", "gametest", "events", "polish", "items"])

    def test_tasks_the_tool_writes_itself_and_other_roles_keep_the_roles_own_list(self):
        self.assertIsNone(skillset.for_task("coder", "Wire the painted art in: register the renderer for the projectile"))
        self.assertIsNone(skillset.for_task("designer", self.store.task_instructions(self.feature)))
        self.assertIsNone(skillset.for_task("coder", ""))
        self.store.add_task("s_mod", "s_mod:WIRE:1", "coder", "Wire something")
        self.assertIsNone(build_envelope(self.store, "s_mod", self.task("s_mod:WIRE:1")).skills)

    def test_the_run_is_given_the_chosen_skills_and_told_how_to_get_the_rest(self):
        full = _load_agent_definitions("coder")["coder"]["prompt"]
        self.assertEqual(full, _load_agent_definitions()["coder"]["prompt"]); self.assertEqual(full.count("# Preloaded skill: "), 15)
        chosen = _load_agent_definitions("coder", ["coder", "gametest", "events", "gui"])["coder"]["prompt"]
        self.assertEqual([l.split(": ")[1] for l in chosen.splitlines() if l.startswith("# Preloaded skill: ")], ["coder", "gui", "events", "gametest"], "in the role's own order")
        self.assertIn("# Skills not loaded for this task", chosen); self.assertIn("call the `orchestra_skill` tool with its name", chosen)
        later = [l.split("`")[1] for l in chosen.split("# Skills not loaded for this task")[1].splitlines() if l.startswith("- `")]
        self.assertEqual(set(later), set(skillset.TOPICS) - {"gui"})
        self.assertLess(len(chosen), 0.45 * len(full))
        self.assertEqual(_role_prompt("coder", ["coder", "gametest", "events", "gui"]).count("# Preloaded skill: "), 4, "the other runtimes get the same choice")
        self.assertNotIn("Skills not loaded", _load_agent_definitions("designer", None)["designer"]["prompt"])
        # through a real run command
        tid = request_change(self.store, "s_mod", "spitter", "make it a little faster")["task"]
        captured = {}
        def fake_run(cmd, *, cwd, log, timeout, env, stdin_text=None):
            captured["agents"] = json.loads(Path(cmd[cmd.index("--agents") + 1]).read_text())
            log.parent.mkdir(parents=True, exist_ok=True); log.write_text("{}"); return {"pid": 1, "exit_code": 0, "killed": False, "timeout_s": timeout, "duration_s": 1.0, "cmd": cmd}
        with patch.object(pmod, "run_logged", fake_run):
            ClaudeCodeProvider(binary="claude-fake").run(build_envelope(self.store, "s_mod", self.task(tid)), self.ws / "r.log")
        prompt = captured["agents"]["coder"]["prompt"]
        self.assertEqual(prompt.count("# Preloaded skill: "), 3); self.assertLess(len(prompt), 0.3 * len(full))

    def test_a_designer_that_only_paints_is_not_given_the_blockbench_skill(self):
        from mod_orchestra import artreq, models
        for text in (artreq.ART_INSTRUCTIONS, models.SPRITES_INSTRUCTIONS):
            self.assertNotRegex(text, r"(?i)blockbench|bbmodel|geo\.json", "a painted-art brief started to rely on a model: give it the skill back")
        full = _load_agent_definitions("designer")["designer"]["prompt"]; self.assertIn("# Preloaded skill: blockbench", full)
        for tid, want in (("s_mod:ART:acid_spit", ["designer"]), ("s_mod:ART:acid_spit:2", ["designer"]), ("s_mod:SPRITES", ["designer"]), ("s_mod:SPRITES:2", ["designer"]),
                          ("s_mod:MODEL:spitter", None), ("s_mod:ITEM3D:gem", None), ("s_mod:ANIMATE:gem:1", None), ("s_mod:ARMOR:ruby", None), ("s_mod:ARMOR3D:ruby", None),
                          ("s_mod:ARTPASS:x", None), ("s_mod:BLOCK3D:ore", None), ("s_mod:PROJ3D:glob", None)):
            self.assertEqual(skillset.for_task("designer", "", tid), want, tid)
        self.assertIsNone(skillset.for_task("coder", "", "s_mod:ART:x"), "the id alone never changes what a coder loads")
        painted = _load_agent_definitions("designer", ["designer"])["designer"]["prompt"]
        self.assertNotIn("# Preloaded skill: blockbench", painted); self.assertIn("# Preloaded skill: designer", painted); self.assertNotIn("Skills not loaded", painted)
        self.assertLess(len(painted), 0.3 * len(full))
        self.store.add_task("s_mod", "s_mod:ART:acid_spit", "designer", "Paint")
        self.assertEqual(build_envelope(self.store, "s_mod", self.task("s_mod:ART:acid_spit")).skills, ["designer"])

    def test_a_skill_is_one_tool_call_away_and_roles_are_not_served(self):
        call = lambda name: handle(self.store, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "orchestra_skill", "arguments": {"name": name}}})["result"]
        got = call("GUI "); self.assertFalse(got.get("isError"), got)
        self.assertIn((ROOT / "src/mod_orchestra/resources/claude/skills/gui/SKILL.md").read_text(encoding="utf8")[:200], json.loads(got["content"][0]["text"])["skill"])
        for name in ("coordinator", "../../settings", "nope"):
            bad = call(name); self.assertTrue(bad["isError"], name); self.assertIn("skills: coder, gametest, events, recipes", bad["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
