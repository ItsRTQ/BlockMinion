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
        for needle in ('"art"', "visual cues", "pieces", "never mood words", "serrated edge"):
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
