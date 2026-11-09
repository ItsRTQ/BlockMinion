import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import art, skin, workflow
from mod_orchestra.spec import Art, coerce_art, read_spec, validate_art
from mod_orchestra.specedit import add_material, add_food
from mod_orchestra.spritecheck import check_sprites, catalogue, iou, template_alpha
from mod_orchestra.state import Store
from mod_orchestra.textures import tinted_item_png
from mod_orchestra.validation import InputError

THEME = ("Tribal ork warband aesthetic: rugged olive-green skin (#4a6b3b), weathered dark iron (#3b3f42), bone-white accents (#d9cfb8), and blood-rust "
         "warpaint (#8c2d19). Crude, heavy-forged plates, jagged edges, leather straps, and battle-worn tribal motifs with a fierce, primal mood.")


def sprite(shape_seed: int, colours: int = 5) -> bytes:
    """An original 16x16 sprite (own irregular shape, `colours` colours)."""
    palette = [(40, 20, 20), (150, 30, 25), (210, 70, 40), (230, 200, 150), (90, 80, 70), (20, 90, 60)][:colours]
    px = bytearray(1024)
    for y in range(16):
        for x in range(16):
            if (x * 7 + y * 3 + shape_seed) % 5 != 0 and 1 <= x <= 13 and 2 <= y <= 14 and (x + 2 * y + shape_seed) % 11 < 9 and abs(x - 7) + abs(y - 8) < 9 + shape_seed % 3:
                px[(y * 16 + x) * 4:(y * 16 + x) * 4 + 4] = bytes(palette[(x * 3 + y * 5 + shape_seed) % len(palette)]) + b"\xff"
    return skin.encode_png(16, 16, bytes(px))


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop); (base / "projects").mkdir()
        self.project = workflow.new_project(self.store, name="G", mod_id="g_mod", package="com.x.g", idea="items: tooth; hostile mobs: brute")
        add_material(self.store, "g_mod", identifier="groko", label="Groko", ingredient="minecraft:iron_ingot", tools=["sword", "axe"], armor=["helmet", "boots"], color="#4a6b3b")
        add_food(self.store, "g_mod", identifier="grub_stew", label="Grub Stew")
        raw = self.store.project("g_mod")["spec"]; raw["theme"] = THEME
        with self.store.tx() as con:
            con.execute("UPDATE projects SET spec_json=? WHERE id=?", (json.dumps(raw), "g_mod"))
        workflow.plan_project(self.store, "g_mod"); workflow.approve_spec(self.store, "g_mod"); workflow.generate_project(self.store, "g_mod")
        self.spec = read_spec(self.store.project("g_mod")["spec"]); self.root = Path(self.project["root"])


class TestSpecArt(unittest.TestCase):
    def test_coercion_forms_and_round_trip(self):
        self.assertIsNone(coerce_art(None)); self.assertIsNone(coerce_art("")); self.assertIsNone(coerce_art({}))
        self.assertEqual(coerce_art("a cleaver"), Art(concept="a cleaver"))
        a = coerce_art({"concept": "c", "tags": "jagged, bone teeth ; rust", "silhouette": "cleaver", "pieces": {"sword": "notched"}})
        self.assertEqual(a.tags, ("jagged", "bone teeth", "rust")); self.assertEqual(a.pieces, {"sword": "notched"})
        self.assertIs(coerce_art(a), a)
        with self.assertRaises(InputError):
            coerce_art(["x"])

    def test_validation(self):
        validate_art(Art(concept="ok", tags=("serrated edge",)), "x")
        for bad in (Art(concept="x" * 400), Art(tags=("a",)), Art(tags=tuple("tag%d" % i for i in range(20))), Art(concept="<script>"), Art(silhouette="s" * 80),
                    Art(pieces={"wand": "x"}), Art(pieces={"sword": "x" * 400})):
            with self.assertRaises(InputError, msg=str(bad)):
                validate_art(bad, "x", ("sword",))

    def test_spec_keeps_art_on_every_entity_kind(self):
        raw = {"schema_version": 2, "name": "G", "mod_id": "g_mod", "package": "com.x.g", "idea": "i", "profile": "p", "theme": THEME,
               "features": [{"kind": "item", "identifier": "tooth", "label": "Tooth", "art": {"concept": "a fang", "tags": ["curved", "yellowed"]}}],
               "materials": [{"identifier": "groko", "label": "Groko", "ingredient": "minecraft:iron_ingot", "tools": ["sword"], "armor": ["helmet"],
                              "art": {"concept": "crude iron", "pieces": {"sword": "a cleaver", "helmet": "a horned bucket"}}}],
               "foods": [{"identifier": "stew", "label": "Stew", "art": "a murky stew"}],
               "mobs": [{"identifier": "brute", "label": "Brute", "art": {"concept": "a hulking ork", "tags": ["scarred hide", "iron pauldron"]}}]}
        spec = read_spec(json.loads(json.dumps(raw)))
        again = read_spec(json.loads(json.dumps(spec.to_dict())))
        self.assertEqual((again.features[0].art.tags, again.materials[0].art.pieces["helmet"], again.foods[0].art.concept, again.mobs[0].art.tags),
                         (("curved", "yellowed"), "a horned bucket", "a murky stew", ("scarred hide", "iron pauldron")))
        raw["materials"][0]["art"]["pieces"]["boots"] = "x"
        with self.assertRaises(InputError):
            read_spec(raw)


class TestTheme(unittest.TestCase):
    def test_tags_are_visual_phrases_in_order(self):
        tags = art.theme_tags(THEME)
        self.assertEqual(tags[:4], ["rugged olive-green skin", "weathered dark iron", "bone-white accents", "blood-rust warpaint"])
        for needle in ("jagged edges", "leather straps", "heavy-forged plates", "battle-worn tribal motifs"):
            self.assertIn(needle, tags)
        self.assertFalse([t for t in tags if "aesthetic" in t or "mood" in t or "#" in t])      # moods and colour codes are not things to draw

    def test_palette_pairs_hex_with_its_words(self):
        pal = art.theme_palette(THEME)
        self.assertEqual([(p["name"], p["hex"]) for p in pal], [("rugged olive-green skin", "#4a6b3b"), ("weathered dark iron", "#3b3f42"), ("bone-white accents", "#d9cfb8"), ("blood-rust warpaint", "#8c2d19")])
        self.assertEqual(art.theme_palette("no colours here"), []); self.assertEqual(art.theme_tags(""), [])


class TestEffectiveArt(Project):
    def test_siblings_share_voice_but_each_has_its_own_cues(self):
        sword, axe, helmet = (art.effective_art(self.spec, "tool", "groko_sword"), art.effective_art(self.spec, "tool", "groko_axe"), art.effective_art(self.spec, "armor", "groko_helmet"))
        self.assertEqual(sword["tags"][:3], axe["tags"][:3]); self.assertEqual(sword["tags"][:3], helmet["tags"][:3])
        self.assertNotEqual(sword["tags"], axe["tags"]); self.assertEqual(sword["source"], "derived")
        self.assertIn("blade", sword["concept"]); self.assertIn("axe bit", axe["concept"])
        self.assertEqual(len(sword["palette"]), 4); self.assertEqual(art.effective_art(self.spec, "tool", "groko_sword"), sword)   # deterministic

    def test_authored_art_wins_and_pieces_override_the_set(self):
        mats = [replace(self.spec.materials[0], art=Art(concept="crude iron", tags=("notched", "bone teeth"), pieces={"sword": "a notched cleaver"}))]
        spec = replace(self.spec, materials=mats)
        sword, axe = art.effective_art(spec, "tool", "groko_sword"), art.effective_art(spec, "tool", "groko_axe")
        self.assertEqual((sword["concept"], sword["tags"], sword["source"]), ("a notched cleaver", ["notched", "bone teeth"], "authored"))
        self.assertEqual(axe["concept"], "crude iron")                                                  # no piece text: the set's concept
        self.assertEqual(art.effective_art(spec, "set", "groko")["concept"], "crude iron")
        brief = art.brief(spec, "tool", "groko_sword")
        self.assertIn("concept: a notched cleaver", brief); self.assertIn("visual cues: notched, bone teeth", brief); self.assertIn("#4a6b3b", brief)
        self.assertNotIn("palette", art.brief(spec, "tool", "groko_sword", palette=False))

    def test_every_kind_resolves_and_unknown_does_not(self):
        for kind, ident in (("item", "tooth"), ("food", "grub_stew"), ("set", "groko"), ("armor", "groko_boots")):
            self.assertTrue(art.effective_art(self.spec, kind, ident)["concept"], (kind, ident))
        for kind, ident in (("tool", "nope"), ("mob", "ghost"), ("item", "nope")):
            with self.assertRaises(KeyError):
                art.effective_art(self.spec, kind, ident)


class TestSpriteGates(Project):
    def test_the_stock_template_is_rejected_with_the_art_direction(self):
        rej = check_sprites(self.spec, {"groko_sword": tinted_item_png("sword", (74, 107, 59), (200, 200, 200)), "tooth": sprite(1), "grub_stew": sprite(2)})
        self.assertEqual(list(rej), ["groko_sword"]); self.assertIn("stock sword template", rej["groko_sword"]); self.assertIn("rugged olive-green skin", rej["groko_sword"])

    def test_a_copy_of_a_sibling_and_flat_sprites_are_rejected(self):
        rej = check_sprites(self.spec, {"groko_sword": sprite(1), "groko_axe": sprite(1), "tooth": sprite(2, colours=3)})
        self.assertEqual(sorted(rej), ["groko_sword", "tooth"])        # axe sorts first and stays; the later copy is the one rejected
        self.assertIn("same pixels as groko_axe", rej["groko_sword"]); self.assertIn("only 3 colours", rej["tooth"])

    def test_original_sprites_pass_and_the_rest_is_ignored(self):
        self.assertEqual(check_sprites(self.spec, {"groko_sword": sprite(1), "groko_axe": sprite(2), "groko_helmet": sprite(3), "contact_sheet": b"x", "not_in_spec": sprite(4)}), {})
        self.assertEqual(check_sprites(self.spec, {"tooth": b"not a png"}), {})                          # unreadable: install_sprites reports that on its own

    def test_masks_and_catalogue(self):
        cat = catalogue(self.spec)
        self.assertEqual((cat["groko_sword"]["mask"], cat["groko_helmet"]["mask"], cat["groko_boots"]["mask"], cat["grub_stew"]["mask"], cat["tooth"]["mask"]), ("sword", "gem", "gem", "food", "gem"))
        self.assertEqual(iou(template_alpha("sword"), template_alpha("sword")), 1.0); self.assertLess(iou(template_alpha("sword"), template_alpha("food")), 0.5)

    def test_install_sprites_rejects_the_template_and_installs_the_original(self):
        from mod_orchestra.models import install_sprites
        sp = self.root / "models" / "sprites"; sp.mkdir(parents=True)
        (sp / "groko_sword.png").write_bytes(tinted_item_png("sword", (74, 107, 59), (200, 200, 200))); (sp / "groko_axe.png").write_bytes(sprite(2))
        res = install_sprites(self.store, "g_mod", "t", ["groko_sword", "groko_axe"], run_id="r1", actor="agent:designer")
        self.assertEqual(res["installed"], ["src/main/resources/assets/g_mod/textures/item/groko_axe.png"]); self.assertIn("stock sword template", res["rejected"]["groko_sword"])
        self.assertEqual((self.root / "src/main/resources/assets/g_mod/textures/item/groko_axe.png").read_bytes(), sprite(2))


class TestBriefs(Project):
    def test_sprite_task_carries_the_art_direction(self):
        from mod_orchestra.models import request_sprites
        out = request_sprites(self.store, "g_mod", ["groko_sword", "groko_helmet", "grub_stew"])
        text = self.store.task_instructions(out["task"])
        for needle in ("paint THAT, not the stock icon", "- groko_sword: Groko sword", "    concept: Groko sword", "    visual cues: rugged olive-green skin", "Set groko (Groko)", "Palette from the mod's theme",
                       "#4a6b3b", "#8c2d19", "- grub_stew: Grub Stew"):
            self.assertIn(needle, text)

    def test_sprite_instructions_state_the_creative_rules_and_the_check(self):
        from mod_orchestra.models import SPRITES_INSTRUCTIONS
        for needle in ("85% or more the stock template", "fewer than 4 colours", "orchestra_check_sprites", "own silhouette"):
            self.assertIn(needle, SPRITES_INSTRUCTIONS)

    def test_the_mob_packet_has_its_art_direction(self):
        from mod_orchestra import rigs
        from mod_orchestra.models import rig_block
        raw = self.store.project("g_mod")["spec"]
        mob = next(m for m in raw["mobs"] if m["identifier"] == "brute"); mob["art"] = {"concept": "a hulking ork with a broken tusk", "tags": ["scarred hide", "iron pauldron"]}
        with self.store.tx() as con:
            con.execute("UPDATE projects SET spec_json=? WHERE id=?", (json.dumps(raw), "g_mod"))
        text = rig_block(self.store, "g_mod", "brute", self.root)
        self.assertIn("Art direction for this creature", text); self.assertIn("a hulking ork with a broken tusk", text); self.assertIn("scarred hide, iron pauldron", text); self.assertIn("orchestra_paint_skin", text)

    def test_interpreter_is_told_to_write_art(self):
        from mod_orchestra.interpreter import SPEC_INSTRUCTIONS
        for needle in ('"art"', "visual cues", "pieces", "never mood words", "stock fantasy vocabulary", "the cues describe, they do not dictate"):
            self.assertIn(needle, SPEC_INSTRUCTIONS.replace("6-10 concrete visual cues", "visual cues"))


class TestSetArt(Project):
    def test_list_and_set_every_kind(self):
        from mod_orchestra.content import list_art, set_art
        keys = set(list_art(self.store, "g_mod"))
        self.assertEqual(keys, {"item:tooth", "food:grub_stew", "mob:brute", "set:groko", "tool:groko_sword", "tool:groko_axe", "armor:groko_helmet", "armor:groko_boots"})
        self.assertTrue(all(v["source"] == "derived" for v in list_art(self.store, "g_mod").values()))
        out = set_art(self.store, "g_mod", "tool", "groko_sword", concept="a notched cleaver with bone teeth")
        self.assertEqual((out["art"]["concept"], out["art"]["source"]), ("a notched cleaver with bone teeth", "authored"))
        set_art(self.store, "g_mod", "set", "groko", concept="crude black iron", tags="serrated edge, bone teeth ; rust red", silhouette="cleaver")
        a = list_art(self.store, "g_mod")
        self.assertEqual((a["set:groko"]["tags"], a["set:groko"]["silhouette"]), (["serrated edge", "bone teeth", "rust red"], "cleaver"))
        self.assertEqual(a["tool:groko_sword"]["concept"], "a notched cleaver with bone teeth")           # the piece text survived the set edit
        self.assertEqual((a["armor:groko_helmet"]["concept"], a["armor:groko_helmet"]["tags"]), ("crude black iron", ["serrated edge", "bone teeth", "rust red"]))   # no piece text: the set's
        for kind, ident in (("item", "tooth"), ("food", "grub_stew"), ("mob", "brute")):
            self.assertEqual(set_art(self.store, "g_mod", kind, ident, concept=f"a {ident}", tags=["x y", "z w"])["art"]["source"], "authored")
        self.assertEqual(read_spec(self.store.project("g_mod")["spec"]).mobs[0].art.tags, ("x y", "z w"))

    def test_empty_fields_clear_and_bad_input_is_refused(self):
        from mod_orchestra.content import list_art, set_art
        set_art(self.store, "g_mod", "tool", "groko_axe", concept="a skull-knobbed slab")
        set_art(self.store, "g_mod", "tool", "groko_axe", concept="")
        self.assertEqual(list_art(self.store, "g_mod")["tool:groko_axe"]["source"], "derived")
        set_art(self.store, "g_mod", "mob", "brute", concept="x y z"); set_art(self.store, "g_mod", "mob", "brute")
        self.assertIsNone(read_spec(self.store.project("g_mod")["spec"]).mobs[0].art)
        for args in (("wand", "tooth"), ("item", "nope"), ("mob", "ghost"), ("tool", "groko_wand"), ("set", "nope")):
            with self.assertRaises(InputError, msg=str(args)):
                set_art(self.store, "g_mod", *args, concept="a thing")
        with self.assertRaises(InputError):
            set_art(self.store, "g_mod", "item", "tooth", concept="<script>")
        with self.assertRaises(InputError):
            set_art(self.store, "g_mod", "item", "tooth", concept="ok", tags=["a"] * 20)

    def test_editing_after_generation_is_cosmetic(self):
        from mod_orchestra.content import set_art
        before = self.store.project("g_mod")["status"]
        set_art(self.store, "g_mod", "item", "tooth", concept="a yellowed fang")
        self.assertEqual((self.store.project("g_mod")["status"], self.store.project("g_mod")["spec_state"]), (before, "APPROVED"))


class TestSetArtBeforeGeneration(unittest.TestCase):
    def test_it_returns_the_spec_to_draft_like_any_spec_edit(self):
        from mod_orchestra.content import set_art
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite")
            with patch.object(workflow, "PROJECTS", Path(tmp) / "p"):
                (Path(tmp) / "p").mkdir()
                workflow.new_project(store, name="G", mod_id="g_mod", package="com.x.g", idea="items: tooth")
                workflow.plan_project(store, "g_mod"); workflow.approve_spec(store, "g_mod")
                self.assertEqual(store.project("g_mod")["spec_state"], "APPROVED")
                set_art(store, "g_mod", "item", "tooth", concept="a yellowed fang")
                self.assertEqual(store.project("g_mod")["spec_state"], "DRAFT")


class TestCli(unittest.TestCase):
    def test_set_art_and_show_art_through_the_command_line(self):
        import os, subprocess, sys
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "CRAFTCTL_HOME": home}
            run = lambda *a: subprocess.run([sys.executable, "-m", "mod_orchestra.cli", *a], env=env, capture_output=True, text=True)
            self.assertEqual(run("new", "--name", "G", "--id", "g_mod", "--package", "com.x.g", "--idea", "items: tooth; hostile mobs: brute").returncode, 0)
            r = run("set-art", "g_mod", "--kind", "mob", "--id", "brute", "--concept", "a hulking ork with a broken tusk", "--tags", "scarred hide", "iron pauldron")
            self.assertEqual(r.returncode, 0, r.stderr)
            shown = json.loads(run("show-art", "g_mod").stdout)
            self.assertEqual((shown["mob:brute"]["source"], shown["mob:brute"]["tags"]), ("authored", ["scarred hide", "iron pauldron"]))
            self.assertEqual(shown["item:tooth"]["source"], "derived")
            self.assertNotEqual(run("set-art", "g_mod", "--kind", "mob", "--id", "ghost", "--concept", "x y").returncode, 0)


class TestAutomaticIcons(Project):
    def test_generation_plans_the_first_design_of_every_icon(self):
        tasks = {t["id"]: t for t in self.store.tasks("g_mod")}
        t = tasks["g_mod:SPRITES:1"]
        self.assertEqual((t["role"], t["state"]), ("designer", "READY")); self.assertIn("Design", t["title"])
        text = self.store.task_instructions("g_mod:SPRITES:1")
        for needle in ("- tooth:", "- groko_sword:", "- groko_axe:", "- groko_helmet:", "- groko_boots:", "- grub_stew:", "Worn-armor layers to paint for material(s): groko",
                       "First design of every icon", "    concept:", "visual cues"):
            self.assertIn(needle, text)
        ev = next(e for e in self.store.events("g_mod", 500) if e["kind"] == "SPRITES_REQUESTED")
        self.assertEqual((ev["actor"], ev["payload"]["initial"]), ("controller", True))

    def test_it_is_planned_once_and_skips_what_the_user_uploaded(self):
        from mod_orchestra.models import ensure_initial_sprites
        self.assertIsNone(ensure_initial_sprites(self.store, "g_mod"))                                   # a SPRITES task exists: never again
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite")
            with patch.object(workflow, "PROJECTS", Path(tmp) / "p"):
                (Path(tmp) / "p").mkdir()
                workflow.new_project(store, name="G", mod_id="h_mod", package="com.x.h", idea="items: tooth, claw")
                workflow.plan_project(store, "h_mod"); workflow.approve_spec(store, "h_mod")
                store.add_event("h_mod", "user", "TEXTURE_UPLOADED", {"kind": "item", "identifier": "tooth"})
                self.assertIsNone(ensure_initial_sprites(store, "h_mod"))                                # not generated yet: nothing to install over
                out = workflow.generate_project(store, "h_mod")
                self.assertEqual(out["sprites_task"], "h_mod:SPRITES:1")
                text = store.task_instructions("h_mod:SPRITES:1")
                self.assertIn("- claw:", text); self.assertNotIn("- tooth:", text)                       # the user's own icon is left alone

    def test_a_project_with_nothing_to_paint_gets_no_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite")
            with patch.object(workflow, "PROJECTS", Path(tmp) / "p"):
                (Path(tmp) / "p").mkdir()
                workflow.new_project(store, name="G", mod_id="m_mod", package="com.x.m", idea="hostile mobs: brute")
                workflow.plan_project(store, "m_mod"); workflow.approve_spec(store, "m_mod")
                self.assertNotIn("sprites_task", workflow.generate_project(store, "m_mod"))              # mobs only: their skins are the MODEL tasks


class TestRedesign(Project):
    def paint_first_version(self):
        sp = self.root / "models" / "sprites"; sp.mkdir(parents=True, exist_ok=True)
        (sp / "groko_sword.png").write_bytes(sprite(1)); (sp / "groko_axe.png").write_bytes(sprite(2)); (sp / "paint.py").write_text("# the designer's script")

    def test_redesigning_painted_icons_needs_a_note(self):
        from mod_orchestra.models import request_sprites
        self.paint_first_version()
        with self.assertRaisesRegex(InputError, "say what should change"):
            request_sprites(self.store, "g_mod", ["groko_sword"])
        request_sprites(self.store, "g_mod", ["grub_stew"])                                                # never painted by the designer: a plain request is fine

    def test_the_designer_gets_the_note_the_previous_work_and_earlier_notes(self):
        from mod_orchestra.models import request_sprites
        self.paint_first_version()
        first = request_sprites(self.store, "g_mod", ["groko_sword", "groko_axe"], notes="the blade is too thin")
        second = request_sprites(self.store, "g_mod", ["groko_sword"], notes="add a red wrap on the grip")
        t1, t2 = self.store.task_instructions(first["task"]), self.store.task_instructions(second["task"])
        for needle in ("REDESIGN: 2 of these were already painted", "models/sprites/paint.py", "keep every sprite and detail it does not mention", "- the blade is too thin"):
            self.assertIn(needle, t1)
        self.assertLess(t2.index("- add a red wrap on the grip"), t2.index("- the blade is too thin"))      # newest first, earlier notes kept
        self.assertNotIn("the blade is too thin", t1.replace("- the blade is too thin", ""))
        self.assertTrue(any(t["title"].startswith("Redesign") for t in self.store.tasks("g_mod") if t["id"] == second["task"]))

    def test_the_notes_about_other_icons_do_not_leak(self):
        from mod_orchestra.models import request_sprites
        self.paint_first_version()
        request_sprites(self.store, "g_mod", ["groko_axe"], notes="make the axe heavier")
        out = request_sprites(self.store, "g_mod", ["groko_sword"], notes="sharper edge")
        self.assertNotIn("make the axe heavier", self.store.task_instructions(out["task"]))


class TestAutopilotAndIcons(Project):
    def test_a_failed_icon_run_does_not_stop_autopilot(self):
        from mod_orchestra.dispatch import orchestrate
        from mod_orchestra.provider import FakeProvider
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite")
            with patch.object(workflow, "PROJECTS", Path(tmp) / "p"):
                (Path(tmp) / "p").mkdir()
                workflow.new_project(store, name="G", mod_id="k_mod", package="com.x.k", idea="items: tooth, claw")
                workflow.plan_project(store, "k_mod"); workflow.approve_spec(store, "k_mod"); workflow.generate_project(store, "k_mod")
                self.assertEqual([t["id"] for t in store.tasks("k_mod") if t["state"] == "READY" and t["role"] == "designer"], ["k_mod:SPRITES:1"])
                result = orchestrate(store, "k_mod", max_runs=3, provider=FakeProvider("no handoff block here"))
                self.assertTrue(any(r["task"] == "k_mod:SPRITES:1" for r in result["runs"]), result)           # it ran by itself
                self.assertNotIn("SPRITES", result["stopped_because"])                                           # and its failure did not stop Autopilot
                self.assertTrue(any(e["kind"] == "SPRITES_NOT_DONE" and e["payload"]["task"] == "k_mod:SPRITES:1" for e in store.events("k_mod", 500)))

    def test_the_guidance_puts_icons_after_the_models(self):
        from mod_orchestra.guidance import guidance
        labels = [st["label"] for st in guidance(self.store, "g_mod")["steps"]]
        model = next(i for i, l in enumerate(labels) if "for brute" in l); icon = next(i for i, l in enumerate(labels) if "icons" in l)
        self.assertLess(model, icon)


class TestSpriteTool(Project):
    def test_designer_checks_before_finishing(self):
        from mod_orchestra.mcp import invoke, TOOLS
        sp = self.root / "models" / "sprites"; sp.mkdir(parents=True)
        (sp / "groko_sword.png").write_bytes(tinted_item_png("sword", (1, 2, 3), (4, 5, 6))); (sp / "groko_axe.png").write_bytes(sprite(2)); (sp / "contact_sheet.png").write_bytes(b"x")
        out = invoke(self.store, "orchestra_check_sprites", {"project": "g_mod"})
        self.assertEqual(out["checked"], ["groko_axe", "groko_sword"]); self.assertEqual(out["ok"], ["groko_axe"]); self.assertIn("groko_sword", out["rejected"])
        self.assertIn("groko_helmet", out["missing"])
        (sp / "groko_sword.png").write_bytes(sprite(5))
        self.assertEqual(invoke(self.store, "orchestra_check_sprites", {"project": "g_mod"})["rejected"], {})
        agents = Path(__file__).resolve().parents[1] / "src/mod_orchestra/resources/claude/agents"
        self.assertIn("orchestra_check_sprites", {t["name"] for t in TOOLS})
        for md in agents.glob("*.md"):
            self.assertEqual("orchestra_check_sprites" in md.read_text(encoding="utf8").split("---")[1], md.stem == "designer", md.name)


if __name__ == "__main__":
    unittest.main()


class TestReferenceAndAvoid(Project):
    """The user's own words ("like the Tank from Left 4 Dead", "not cartoon") have a place to live and reach the designer."""

    def test_coercion_validation_and_round_trip(self):
        a = coerce_art({"concept": "a brute", "reference": " the Tank from Left 4 Dead ", "avoid": "cartoon, bright colours ; stripes"})
        self.assertEqual((a.reference, a.avoid), ("the Tank from Left 4 Dead", ("cartoon", "bright colours", "stripes")))
        self.assertIsNotNone(coerce_art({"reference": "a vanilla pig"}))                                    # a sheet with only a reference is a sheet
        for bad in (Art(reference="r" * 130), Art(avoid=tuple(f"thing {i}" for i in range(9))), Art(avoid=("a",))):
            with self.assertRaises(InputError):
                validate_art(bad, "x")

    def test_the_proposal_is_fitted_not_rejected(self):
        from mod_orchestra.interpreter import fit_proposal
        fitted, notes = fit_proposal({"mobs": [{"identifier": "b", "art": {"reference": "ref " * 60, "avoid": [f"avoid number {i}" for i in range(12)] + ["x" * 70, "avoid number 1"]}}]})
        art = fitted["mobs"][0]["art"]
        self.assertLessEqual(len(art["reference"]), 120); self.assertEqual(len(art["avoid"]), 8); self.assertTrue(all(2 <= len(t) <= 48 for t in art["avoid"]))
        self.assertTrue(any("art.avoid to 8" in n for n in notes)); self.assertTrue(any("art.reference to 120" in n for n in notes))

    def test_the_effective_sheet_and_the_designer_brief_carry_them(self):
        mats = [replace(self.spec.materials[0], art=Art(concept="crude iron", reference="a goblin forge's work", avoid=("shiny", "ornate")))]
        spec = replace(self.spec, materials=mats)
        a = art.effective_art(spec, "tool", "groko_sword"); self.assertEqual((a["reference"], a["avoid"], a["source"]), ("a goblin forge's work", ["shiny", "ornate"], "authored"))
        text = art.brief(spec, "tool", "groko_sword")
        self.assertIn("it should resemble: a goblin forge's work", text); self.assertIn("it must NOT look like: shiny, ornate", text); self.assertIn("wins over every default", text)
        self.assertNotIn("resemble", art.brief(self.spec, "tool", "groko_sword"))                           # nothing is said when nothing was asked

    def test_the_mob_packet_and_the_sprite_task_show_them(self):
        from mod_orchestra.content import set_art
        from mod_orchestra.models import rig_block, request_sprites
        set_art(self.store, "g_mod", "mob", "brute", concept="a hulking grotesque mutant with pale human skin", reference="the Tank from Left 4 Dead", avoid=["cartoon", "saturated green"])
        packet = rig_block(self.store, "g_mod", "brute", self.root)
        for needle in ("it should resemble: the Tank from Left 4 Dead", "it must NOT look like: cartoon, saturated green"):
            self.assertIn(needle, packet)
        set_art(self.store, "g_mod", "set", "groko", concept="crude iron", avoid=["shiny"])
        self.assertIn("it must NOT look like: shiny", self.store.task_instructions(request_sprites(self.store, "g_mod", ["groko_sword"])["task"]))

    def test_set_art_edits_them_and_the_listing_returns_them(self):
        from mod_orchestra.content import list_art, set_art
        out = set_art(self.store, "g_mod", "mob", "brute", concept="a brute", reference="the Tank", avoid="cartoon, cute")
        self.assertEqual((out["art"]["reference"], out["art"]["avoid"]), ("the Tank", ["cartoon", "cute"]))
        self.assertEqual(list_art(self.store, "g_mod")["mob:brute"]["avoid"], ["cartoon", "cute"])
        set_art(self.store, "g_mod", "mob", "brute")                                                        # everything empty clears it
        self.assertIsNone(read_spec(self.store.project("g_mod")["spec"]).mobs[0].art)

    def test_the_interpreter_is_told_to_keep_the_users_style_words(self):
        from mod_orchestra.interpreter import SPEC_INSTRUCTIONS
        text = SPEC_INSTRUCTIONS.replace("{{", "{").replace("}}", "}")
        for needle in ("The user's style words are the art direction", "belong in the concept AND in the tags", "not green because something is infected", "art.reference",
                       "the designer cannot see it", "a small head and enormous shoulders and arms", "list it in `art.avoid`", "art.reference 120, at most 8 art.avoid phrases"):
            self.assertIn(needle, text)

    def test_the_skill_has_no_stock_colours_and_says_how_to_look_like_a_brute(self):
        root = Path(__file__).resolve().parents[1]
        for rel in (".claude/skills/blockbench/SKILL.md", "src/mod_orchestra/resources/claude/skills/blockbench/SKILL.md", "src/mod_orchestra/models.py"):
            text = (root / rel).read_text(encoding="utf8")
            for stock in ("#5c7f3a", "#d9cfb8", "#8c2d19", "#3b3f42"):
                self.assertNotIn(stock, text, f"{rel} still teaches {stock}")
        skill = (root / ".claude/skills/blockbench/SKILL.md").read_text(encoding="utf8")
        for needle in ("The colours are never given here", "No regular bands or stripes", "`grim`", "Shape comes before paint", "`reference`", "`avoid`", "`rotten`"):
            self.assertIn(needle, skill)


class TestPaintWithoutAnAgent(Project):
    RECIPE = {"palette": {"base": "#9d8878", "rags": "#4b4944"}, "zones": [{"bones": ["body", "head"], "color": "base", "surface": "flesh"}, {"bones": ["*_leg*"], "color": "rags", "surface": "cloth"}],
              "face": {"style": "grim", "eyes": "#d6c46a", "mouth": "#1c1012"}, "seed": "brute"}

    def setUp(self):
        super().setUp()
        from mod_orchestra import rigs
        rigs.stage_rig(self.root, "biped", "brute", "g_mod")

    def test_it_paints_the_models_png_and_installs_it_as_the_mobs_texture(self):
        from mod_orchestra.content import paint_mob_skin
        out = paint_mob_skin(self.store, "g_mod", "brute", self.RECIPE, install=True)
        self.assertEqual((out["size"], out["installed"], out["face_check"]["ok"]), ([128, 128], True, True))
        installed = self.root / "src/main/resources/assets/g_mod/textures/entity/brute.png"
        self.assertEqual(skin.decode_png(installed.read_bytes())[:2], (128, 128)); self.assertEqual(installed.read_bytes(), (self.root / "models/brute.png").read_bytes())

    def test_without_install_only_the_model_workspace_changes(self):
        from mod_orchestra.content import paint_mob_skin
        before = (self.root / "src/main/resources/assets/g_mod/textures/entity/brute.png").read_bytes() if (self.root / "src/main/resources/assets/g_mod/textures/entity/brute.png").exists() else None
        out = paint_mob_skin(self.store, "g_mod", "brute", self.RECIPE)
        self.assertFalse(out["installed"]); self.assertTrue((self.root / "models/brute.png").is_file())
        after = (self.root / "src/main/resources/assets/g_mod/textures/entity/brute.png")
        self.assertEqual(after.read_bytes() if after.exists() else None, before)

    def test_bad_input_is_refused(self):
        from mod_orchestra.content import paint_mob_skin
        from mod_orchestra.state import StateError
        for mob, recipe, error in (("../x", self.RECIPE, InputError), ("ghost", self.RECIPE, StateError), ("brute", {}, InputError), ("brute", {"palette": {"cloth": "#000000"}}, InputError),
                                   ("brute", dict(self.RECIPE, surface="granite"), InputError)):
            with self.assertRaises(error, msg=mob):
                paint_mob_skin(self.store, "g_mod", mob, recipe)

    def test_the_command_line_does_the_same(self):
        import os, subprocess, sys
        recipe = Path(self.tmp.name) / "skin.json"; recipe.write_text(json.dumps(self.RECIPE))
        env = {**os.environ, "CRAFTCTL_HOME": self.tmp.name}
        r = subprocess.run([sys.executable, "-m", "mod_orchestra.cli", "paint-skin", "--help"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("--install", r.stdout); self.assertIn("--recipe", r.stdout)


class TestCreativeFreedom(Project):
    """No templates and no anchors: the user's words come first, the scaffold is optional, the artist explores before building."""

    def packet(self, idea=None):
        from mod_orchestra.models import rig_block
        if idea is not None:
            self.set_idea(idea)
        return rig_block(self.store, "g_mod", "brute", self.root)

    def set_idea(self, idea):
        raw = self.store.project("g_mod")["spec"]; raw["idea"] = idea
        with self.store.tx() as con:
            con.execute("UPDATE projects SET spec_json=? WHERE id=?", (json.dumps(raw), "g_mod"))

    def test_the_users_words_come_first_verbatim_and_win(self):
        idea = "hostile mobs: brute. The Brute is grotesque, human skin tone, a mutated infected primate, a bit like the Tank from Left 4 Dead, not a cartoon."
        text = self.packet(idea)
        self.assertLess(text.index("What the user wrote, in their own words"), text.index("Optional scaffold"))
        self.assertIn(idea, text); self.assertIn("it wins over every summary below", text); self.assertIn("Where they disagree, follow the words", text)
        self.assertRegex(text, r"Look for what they said about [\w ]+ \(`brute`\)")

    def test_a_long_idea_is_cut_at_a_word_and_an_empty_one_adds_nothing(self):
        from mod_orchestra.models import USER_WORDS_LIMIT
        text = self.packet("word " * 2000)
        self.assertIn("word ...", text); self.assertLess(len(text), USER_WORDS_LIMIT + 6000)
        self.assertNotIn("What the user wrote", self.packet("   "))

    def test_the_sprite_and_armor_packets_carry_the_words_too(self):
        from mod_orchestra.models import request_sprites, request_armor_design
        self.set_idea("items: groko sword. Crude and brutal, nothing shiny.")
        self.assertIn("Crude and brutal, nothing shiny.", self.store.task_instructions(request_sprites(self.store, "g_mod", ["groko_sword"])["task"]))
        self.assertIn("Crude and brutal, nothing shiny.", self.store.task_instructions(request_armor_design(self.store, "g_mod", "groko")["task"]))

    def test_the_scaffold_is_optional_and_never_a_recolour(self):
        text = self.packet()
        for needle in ("Optional scaffold", "use it, reshape it heavily, or ignore it and build your own from scratch", "not to decide the design"):
            self.assertIn(needle, text)
        from mod_orchestra.models import MODEL_INSTRUCTIONS
        for needle in ("optional scaffold", "yours to use, reshape heavily or ignore", "Never deliver the scaffold with only a recolour", "Explore before you build",
                       "three deliberately different takes", "most typical version", '"design_notes"', "the user sees it and may ask for another take"):
            self.assertIn(needle, MODEL_INSTRUCTIONS)
        self.assertNotIn("Only start a fresh", MODEL_INSTRUCTIONS); self.assertNotIn("Start from `models/<mob>.bbmodel`", MODEL_INSTRUCTIONS)

    def test_nothing_in_what_the_agents_read_teaches_a_look(self):
        """Examples anchor: every concrete one we ever shipped came back in the output. The prompts, the skill and the designer's instructions carry none."""
        import re
        from mod_orchestra.interpreter import SPEC_INSTRUCTIONS
        from mod_orchestra.models import MODEL_INSTRUCTIONS, SPRITES_INSTRUCTIONS, ARMOR_INSTRUCTIONS
        root = Path(__file__).resolve().parents[1]
        texts = {"interpreter": SPEC_INSTRUCTIONS, "model": MODEL_INSTRUCTIONS, "sprites": SPRITES_INSTRUCTIONS, "armor": ARMOR_INSTRUCTIONS,
                 "skill": (root / ".claude/skills/blockbench/SKILL.md").read_text(encoding="utf8"), "designer": (root / ".claude/agents/designer.md").read_text(encoding="utf8")}
        anchors = [r"\bork", r"\borc\b", r"serrated", r"bone teeth", r"hammered iron", r"rust red", r"horned", r"armour plates", r"a hunch", r"#5c7f3a", r"#d9cfb8", r"#8c2d19", r"skull knob", r"leather lashing"]
        for name, text in texts.items():
            for pattern in anchors:
                self.assertIsNone(re.search(pattern, text, re.I), f"{name} still teaches a look: {pattern}")


class TestMood(Project):
    """Mood dials are an open vocabulary of suggestions: written by the interpreter alone, shown to the artists as sentences, editable at redesign."""

    def test_coercion_is_strict_for_what_people_type_and_open_in_vocabulary(self):
        from mod_orchestra.spec import coerce_mood
        self.assertEqual(coerce_mood({" Grotesque ": 0.8, "Toon": 0, "eerie  calm": 0.333}), {"grotesque": 0.8, "toon": 0.0, "eerie calm": 0.33})
        self.assertEqual(coerce_mood(None), {}); self.assertEqual(coerce_mood({}), {})
        for bad, why in (({"x": 1}, "2-24 letters"), ({"grotesque": 2}, "0 to 1"), ({"grotesque": "high"}, "0 to 1"), ({"grotesque": True}, "0 to 1"), ({f"dial {chr(97 + i)}x": 0.5 for i in range(13)}, "at most 12"), ([1], "object of dials")):
            with self.assertRaisesRegex(InputError, why):
                coerce_mood(bad)

    def test_the_spec_keeps_them_for_the_mod_and_per_entity(self):
        raw = self.store.project("g_mod")["spec"]; raw["mood"] = {"grotesque": 0.8}
        raw["mobs"][0]["art"] = {"concept": "a brute", "mood": {"gore": 0.2, "grotesque": 1}}
        spec = read_spec(raw); self.assertEqual((spec.mood, spec.mobs[0].art.mood), ({"grotesque": 0.8}, {"gore": 0.2, "grotesque": 1.0}))
        again = read_spec(spec.to_dict()); self.assertEqual((again.mood, again.mobs[0].art.mood), (spec.mood, spec.mobs[0].art.mood))
        self.assertEqual(read_spec(self.store.project("g_mod")["spec"] | {"mood": None}).mood, {})                  # older specs have none

    def test_an_agents_dials_are_fitted_not_rejected(self):
        from mod_orchestra.interpreter import fit_proposal
        fitted, notes = fit_proposal({"mood": {"Grotesque!": 1.7, "x": 0.5, "cute": -3, "menace": "high", **{f"dial {chr(97 + i)}x": 0.5 for i in range(14)}},
                                      "mobs": [{"identifier": "b", "art": {"concept": "c", "mood": {"gore": 5}}}]})
        self.assertEqual(fitted["mood"]["grotesque"], 1.0); self.assertEqual(fitted["mood"]["cute"], 0.0); self.assertNotIn("x", fitted["mood"]); self.assertNotIn("menace", fitted["mood"])
        self.assertLessEqual(len(fitted["mood"]), 12); self.assertEqual(fitted["mobs"][0]["art"]["mood"], {"gore": 1.0})
        self.assertTrue(any("mood dial" in n and "dropped" in n for n in notes)); self.assertTrue(any("mood to 12 dials" in n for n in notes))
        from mod_orchestra.interpreter import spec_from_proposal
        full = json.loads((Path(__file__).parent / "fixtures" / "infectious_zombies.proposal.json").read_text(encoding="utf8"))
        spec = spec_from_proposal(self.store.project("g_mod")["spec"], dict(full, mood={"Bad Key!!": 9}))          # the whole proposal still goes through
        self.assertEqual(spec.mood, {"bad key": 1.0})

    def test_prose_reads_like_a_person_and_zero_is_a_decision(self):
        from mod_orchestra.art import mood_prose
        self.assertEqual(mood_prose({"toon": 0, "grotesque": 0.8, "gore": 0.2, "cute": 0.5, "dread": 0.95, "worn": 0.1}),
                         "extremely dread (0.95), strongly grotesque (0.8), moderately cute (0.5), a hint of gore (0.2), barely worn (0.1), not at all toon (0)")
        self.assertEqual(mood_prose({}), "")

    def test_the_entity_overrides_the_mod_one_dial_at_a_time_and_the_brief_says_so(self):
        raw = self.store.project("g_mod")["spec"]; raw["mood"] = {"grotesque": 0.4, "toon": 0.0}
        raw["mobs"][0]["art"] = {"concept": "a hulking mutant", "mood": {"grotesque": 0.85, "gore": 0.3}}
        spec = read_spec(raw)
        a = art.effective_art(spec, "mob", "brute"); self.assertEqual(a["mood"], {"grotesque": 0.85, "toon": 0.0, "gore": 0.3})
        text = art.brief(spec, "mob", "brute")
        self.assertIn("mood, as suggestions to feel your way with, not rules: strongly grotesque (0.85), a hint of gore (0.3), not at all toon (0)", text)
        self.assertNotIn("mood, as suggestions", art.brief(read_spec(self.store.project("g_mod")["spec"]), "mob", "brute"))   # nothing is said when nothing was inferred
        self.assertEqual(art.effective_art(spec, "tool", "groko_sword")["mood"], {"grotesque": 0.4, "toon": 0.0})              # items inherit the mod's

    def test_editing_art_keeps_the_dials_unless_they_are_sent(self):
        from mod_orchestra.content import list_art, set_art
        set_art(self.store, "g_mod", "mob", "brute", concept="a brute", mood={"grotesque": 0.8})
        set_art(self.store, "g_mod", "mob", "brute", concept="a bigger brute", tags=["scarred"])                   # the Art form never sends mood
        self.assertEqual(list_art(self.store, "g_mod")["mob:brute"]["mood"], {"grotesque": 0.8})
        set_art(self.store, "g_mod", "mob", "brute", concept="x", mood={"grotesque": 0.1, "cute": 0.0}); self.assertEqual(list_art(self.store, "g_mod")["mob:brute"]["mood"], {"cute": 0.0, "grotesque": 0.1})
        set_art(self.store, "g_mod", "mob", "brute", concept="x", mood={}); self.assertEqual(list_art(self.store, "g_mod")["mob:brute"]["mood"], {})
        set_art(self.store, "g_mod", "set", "groko", concept="crude", mood={"crude": 0.9}); set_art(self.store, "g_mod", "set", "groko", concept="very crude")
        self.assertEqual(list_art(self.store, "g_mod")["set:groko"]["mood"], {"crude": 0.9})

    def test_the_designer_packet_carries_them(self):
        from mod_orchestra.content import set_art
        from mod_orchestra.models import rig_block
        set_art(self.store, "g_mod", "mob", "brute", concept="a hulking mutant", mood={"grotesque": 0.85, "toon": 0})
        self.assertIn("strongly grotesque (0.85), not at all toon (0)", rig_block(self.store, "g_mod", "brute", self.root))

    def test_the_interpreter_infers_them_alone_and_treats_them_as_suggestions(self):
        from mod_orchestra.interpreter import SPEC_INSTRUCTIONS
        text = SPEC_INSTRUCTIONS.replace("{{", "{").replace("}}", "}")
        for needle in ('"mood": {"<dial>": 0.0}', "open-vocabulary dials from 0 to 1", "including explicit 0 for what they rule out", "infer them from the\nidea without asking", "suggestions the artists feel their way with, not rules"):
            self.assertIn(needle, text)


class TestDesignNotesAndRedesign(Project):
    """The designer's explored takes are recorded by themselves; a redesign can ask for another take, only the shape or only the skin, or a new mood."""
    NOTES = {"takes": ["a hunched giant with one oversized arm", "a lean sprinter with long jaw", "a bloated torso on thin legs"], "chosen": 1, "why": "the lopsided arm reads at a glance"}

    def handoff(self, **extra):
        return {"task": "g_mod:MODEL:brute", "status": "DONE", "scope": "s", "changed_files": [], "checks_run": [], "evidence": {"level": "STATIC", "pointer": "m"},
                "risks": [], "unknowns": [], "needs_user": [], "next_agent": "coder", **extra}

    def run_model(self, **extra):
        from mod_orchestra.dispatch import dispatch
        from mod_orchestra.provider import FakeProvider
        with patch("mod_orchestra.models.install_model", return_value={"installed": [], "face": None}):
            return dispatch(self.store, "g_mod", task_id="g_mod:MODEL:brute", provider=FakeProvider("```handoff\n" + json.dumps(self.handoff(**extra)) + "\n```"))

    def test_the_notes_are_recorded_from_the_handoff_without_anyone_asking(self):
        from mod_orchestra.feedback import latest_design_notes, model_gallery
        out = self.run_model(design_notes=self.NOTES)
        self.assertEqual(out["task_state"], "DONE")
        notes = latest_design_notes(self.store, "g_mod", "brute")
        self.assertEqual((notes["takes"], notes["chosen"], notes["why"]), (self.NOTES["takes"], 1, self.NOTES["why"]))
        self.assertEqual(next(g for g in model_gallery(self.store, "g_mod") if g["mob"] == "brute")["design_notes"]["chosen"], 1)

    def test_missing_or_malformed_notes_never_fail_a_model(self):
        from mod_orchestra.feedback import latest_design_notes, record_design_notes
        for notes in (None, "three ideas", {"takes": "one"}, {"takes": ["only one"]}, {"takes": [" ", ""]}):
            self.assertIsNone(record_design_notes(self.store, "g_mod", "brute", {"design_notes": notes} if notes is not None else {}, "r"))
        self.assertEqual(self.run_model(design_notes={"takes": "nonsense"})["task_state"], "DONE"); self.assertIsNone(latest_design_notes(self.store, "g_mod", "brute"))

    def test_the_notes_are_fitted_not_trusted(self):
        from mod_orchestra.feedback import record_design_notes
        out = record_design_notes(self.store, "g_mod", "brute", {"design_notes": {"takes": [f"take {i} " + "x" * 400 for i in range(8)], "chosen": 9, "why": "w" * 900}}, "r")
        self.assertEqual(len(out["takes"]), 5); self.assertTrue(all(len(t) <= 220 for t in out["takes"])); self.assertIsNone(out["chosen"]); self.assertLessEqual(len(out["why"]), 400)
        self.assertIsNone(record_design_notes(self.store, "g_mod", "brute", {"design_notes": {"takes": ["a", "b"], "chosen": True}}, "r")["chosen"])

    def test_options_alone_are_a_valid_redesign_and_nothing_at_all_is_not(self):
        from mod_orchestra.feedback import give_model_feedback
        for kw in ({"scope": "skin"}, {"scope": "shape"}, {"mood": {"grotesque": 0.9}}, {"text": "bigger"}):
            self.assertEqual(give_model_feedback(self.store, "g_mod", "brute", **kw)["task"], "g_mod:MODEL:brute")
        with self.assertRaisesRegex(InputError, "Say what should change"):
            give_model_feedback(self.store, "g_mod", "brute")
        with self.assertRaisesRegex(InputError, "scope must be"):
            give_model_feedback(self.store, "g_mod", "brute", "x", scope="everything")
        with self.assertRaisesRegex(InputError, "2-24 letters|0 to 1"):
            give_model_feedback(self.store, "g_mod", "brute", "x", mood={"grotesque": 4})

    def test_a_take_must_be_one_the_designer_actually_explored(self):
        from mod_orchestra.feedback import give_model_feedback
        with self.assertRaisesRegex(InputError, "no design notes yet"):
            give_model_feedback(self.store, "g_mod", "brute", take=2)
        self.run_model(design_notes=self.NOTES)
        for bad in (0, 4, True, "2"):
            with self.assertRaisesRegex(InputError, "number from 1 to 3"):
                give_model_feedback(self.store, "g_mod", "brute", take=bad)
        self.assertEqual(give_model_feedback(self.store, "g_mod", "brute", take=2)["state"], "READY")

    def test_the_designer_reads_every_option_as_a_sentence(self):
        from mod_orchestra.feedback import feedback_context, give_model_feedback
        self.run_model(design_notes=self.NOTES)
        give_model_feedback(self.store, "g_mod", "brute", "keep the grotesque feel", scope="skin", take=2, mood={"grotesque": 0.9, "toon": 0})
        text = feedback_context(self.store, "g_mod", "brute")
        for needle in ("keep the grotesque feel", "Change ONLY the skin and face", "keep the geometry and the animations exactly as they are",
                       'The user prefers take 2 from your own design notes: "a lean sprinter with long jaw"', "adjusted the mood: extremely grotesque (0.9), not at all toon (0)"):
            self.assertIn(needle, text)
        give_model_feedback(self.store, "g_mod", "brute", scope="shape")
        self.assertIn("Change ONLY the shape", feedback_context(self.store, "g_mod", "brute")); self.assertEqual(feedback_context(self.store, "g_mod", "nobody"), "")

    def test_the_mood_is_saved_to_the_mob_and_the_art_stays_as_it_was(self):
        from mod_orchestra.content import list_art, set_art, set_mood
        from mod_orchestra.feedback import give_model_feedback
        before = list_art(self.store, "g_mod")["mob:brute"]; self.assertEqual(before["source"], "derived")
        give_model_feedback(self.store, "g_mod", "brute", mood={"grotesque": 0.7})
        after = list_art(self.store, "g_mod")["mob:brute"]
        self.assertEqual((after["mood"], after["concept"], after["tags"]), ({"grotesque": 0.7}, before["concept"], before["tags"]))
        set_art(self.store, "g_mod", "mob", "brute", concept="a hulking mutant")
        set_mood(self.store, "g_mod", "mob", "brute", {"cute": 0.1}); self.assertEqual(list_art(self.store, "g_mod")["mob:brute"]["concept"], "a hulking mutant")
        set_mood(self.store, "g_mod", "mob", "brute", {}); self.assertEqual(list_art(self.store, "g_mod")["mob:brute"]["mood"], {})
        for kind, ident in (("mob", "ghost"), ("set", "ghost"), ("food", "ghost"), ("item", "ghost"), ("tool", "x")):
            with self.assertRaises(InputError):
                set_mood(self.store, "g_mod", kind, ident, {"x1": 0.5})

    def test_the_gallery_and_the_route_carry_the_options(self):
        from mod_orchestra.feedback import give_model_feedback, model_gallery
        give_model_feedback(self.store, "g_mod", "brute", "x", scope="skin", mood={"grotesque": 0.5})
        g = next(g for g in model_gallery(self.store, "g_mod") if g["mob"] == "brute")
        self.assertEqual(g["mood"], {"grotesque": 0.5}); self.assertEqual((g["feedback"][0]["scope"], g["feedback"][0]["mood"]), ("skin", {"grotesque": 0.5}))
