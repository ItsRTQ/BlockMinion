"""Content of the mod beyond the spec: what a coder declared, and what is found in the code and tracked by nothing."""
import json
import textwrap
import unittest
from pathlib import Path

from mod_orchestra import made
from mod_orchestra.model3d import projectile_assets
from mod_orchestra.modmap import map_text, mod_map, request_change
from mod_orchestra.state import StateError
from mod_orchestra.validation import InputError

from test_art_requests import Base, GLOB

JAVA = "src/main/java/com/x/s"


class Registry(Base):
    def art(self, assets, card="acid_spit"):
        from mod_orchestra.artreq import request_art
        return request_art(self.store, "s_mod", "s_mod:FEATURE:acid_spit", card, assets)

    def test_a_projectile_declared_long_ago_is_still_known(self):
        self.art([GLOB])
        self.assertIn("acid_glob", projectile_assets(self.store, "s_mod"))
        for i in range(700):    # a long project: the declaration is far outside the newest 500 events
            self.store.add_event("s_mod", "controller", "NOISE", {"i": i})
        self.assertNotIn("ART_REQUESTED", [e["kind"] for e in self.store.events("s_mod", 500)], "it really is out of the window")
        got = projectile_assets(self.store, "s_mod")
        self.assertEqual((got["acid_glob"]["card"], got["acid_glob"]["path"], got["acid_glob"]["for"]), ("acid_spit", GLOB["path"], ["spitter"]))

    def test_a_project_from_before_the_registry_is_backfilled_from_its_whole_history(self):
        self.store.add_event("s_mod", "controller", "ART_REQUESTED", {"task": "t", "card": "acid_spit", "assets": [GLOB, {"id": "burn", "kind": "effect_icon", "path": "p.png", "what": "the burn icon", "for": []}]})
        for i in range(600):
            self.store.add_event("s_mod", "controller", "NOISE", {"i": i})
        self.assertIsNone(self.store.get_setting("s_mod", made.SETTING, None))
        e = made.entries(self.store, "s_mod")
        self.assertEqual({k: v["kind"] for k, v in e.items()}, {"acid_glob": "projectile", "burn": "effect"})
        self.assertTrue(self.store.get_setting("s_mod", made.SETTING)["backfilled"])
        self.assertNotIn("the burn icon", json.dumps([x for x in self.store.events("s_mod", 500) if x["kind"] == "SETTING_CHANGED"]), "the registry is not copied into events")

    def test_made_content_is_a_card_of_the_map_linked_to_what_made_it_and_to_what_uses_it(self):
        self.art([GLOB])
        m = mod_map(self.store, "s_mod"); cards = {c["id"]: c for c in m["cards"]}
        c = cards["acid_glob"]
        self.assertEqual((c["kind"], c["title"], c["owner"], c["made"]["feature"], c["made"]["source"]), ("projectile", "Acid glob", "coder", "acid_spit", "declared"))
        self.assertIn(GLOB["path"], c["files"]); self.assertIn("glob of acid", c["description"])
        self.assertIn({"from": "acid_spit", "to": "acid_glob", "kind": "makes"}, m["edges"]); self.assertIn({"from": "spitter", "to": "acid_glob", "kind": "uses"}, m["edges"])
        self.assertEqual(len([x for x in m["cards"] if x["id"] == "acid_glob"]), 1)
        self.assertIn("acid_glob", map_text(self.store, "s_mod"), "the agents' packet knows it exists")
        brief = self.store.task_instructions(request_change(self.store, "s_mod", "acid_glob", "make it glow")["task"])
        self.assertIn("Change request on feature card `acid_glob` (projectile)", brief); self.assertIn("acid_spit --makes--> acid_glob", brief)

    def test_what_a_feature_says_it_produces_is_tracked_and_the_spec_stays_what_it_is(self):
        made.record_produces(self.store, "s_mod", "acid_spit", ["acid_pool", "spitter", "Bad Id", "x"])
        e = made.entries(self.store, "s_mod"); self.assertEqual(sorted(e), ["acid_pool", "spitter"]); self.assertEqual(e["acid_pool"]["kind"], "content")
        cards = {c["id"]: c for c in mod_map(self.store, "s_mod")["cards"]}
        self.assertEqual(cards["spitter"]["kind"], "mob", "an id the spec already has stays that card"); self.assertEqual(cards["acid_pool"]["made"]["feature"], "acid_spit")
        self.art([{**GLOB, "id": "acid_pool", "kind": "entity", "what": "the pool"}])
        self.assertEqual(made.entries(self.store, "s_mod")["acid_pool"]["kind"], "entity", "a later declaration says what it is")
        made.record_produces(self.store, "s_mod", "acid_spit", ["acid_pool"])
        self.assertEqual(made.entries(self.store, "s_mod")["acid_pool"]["kind"], "entity", "and a bare id does not forget it")


class Reading(unittest.TestCase):
    def inv(self, source, mod_id="s_mod"):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "src/main/java/a/B.java"; f.parent.mkdir(parents=True); f.write_text(textwrap.dedent(source), encoding="utf8")
            return [(x["registry"], x["id"], x["line"]) for x in made.inventory(Path(td), mod_id)]

    def test_registrations_are_read_in_the_ways_they_are_written(self):
        got = self.inv('''
            class B {
              static final EntityType<Glob> GLOB = Registry.register(BuiltInRegistries.ENTITY_TYPE, id("acid_glob"),
                  EntityType.Builder.<Glob>of(Glob::new, MobCategory.MISC).sized(0.25f, 0.25f).build("acid_glob"));
              static final MobEffect BURN = Registry.register(BuiltInRegistries.MOB_EFFECT, ResourceLocation.fromNamespaceAndPath(MOD_ID, "burn"), new Burn());
              static final Holder<MobEffect> CHILL = Registry.registerForHolder(BuiltInRegistries.MOB_EFFECT, ResourceLocation.fromNamespaceAndPath("s_mod", "chill"), new Chill());
              static final Item SHARD = Registry.register( BuiltInRegistries.ITEM , ResourceLocation.parse("s_mod:shard") , new Item(new Item.Properties()));
              private static SoundEvent sound(String name) { ResourceLocation rl = id(name); return Registry.register(BuiltInRegistries.SOUND_EVENT, rl, SoundEvent.createVariableRangeEvent(id(name))); }
              static final SoundEvent HISS = sound("hiss"), POP = sound("pop");
            }''')
        self.assertEqual([(r, i) for r, i, _ in got], [("ENTITY_TYPE", "acid_glob"), ("MOB_EFFECT", "burn"), ("MOB_EFFECT", "chill"), ("ITEM", "shard"), ("SOUND_EVENT", "hiss"), ("SOUND_EVENT", "pop")])
        self.assertEqual(got[0][2], 3, "with the line it is on")

    def test_it_reports_only_what_it_can_read_for_sure(self):
        got = self.inv('''
            class B {
              // Registry.register(BuiltInRegistries.ITEM, id("commented_out"), null);
              /* Registry.register(BuiltInRegistries.ITEM, id("in_a_block_comment"), null); */
              static final String DOC = "Registry.register(BuiltInRegistries.ITEM, id(\\"in_a_string\\"), x)";
              static { Registry.register(BuiltInRegistries.CREATIVE_MODE_TAB, TAB_KEY, TAB); }                 // the id is not a literal: not reported
              static { Registry.register(BuiltInRegistries.ITEM, ResourceLocation.withDefaultNamespace("stick"), X); Registry.register(BuiltInRegistries.ITEM, ResourceLocation.parse("minecraft:apple"), X); }
              static { Registry.register(BuiltInRegistries.ITEM, ResourceLocation.fromNamespaceAndPath("other_mod", "thing"), X); }
              void log(String name) { System.out.println(name); }                                                // a helper that registers nothing
              void use() { log("not_content"); register("free_call"); }
              static Item tip(String tooltip, ResourceLocation where) { return Registry.register(BuiltInRegistries.ITEM, where, new Tip(tooltip)); }   // the String is not the id
              static final Item T = tip("not_an_id", KEY);
              static { Registry.register(BuiltInRegistries.ITEM, id("real_one"), X); }
            }''')
        self.assertEqual([(r, i) for r, i, _ in got], [("ITEM", "real_one")])

    def test_it_reads_any_mod_not_only_this_tools(self):
        self.assertEqual(self.inv('class B { static { Registry.register(BuiltInRegistries.BLOCK, ResourceLocation.fromNamespaceAndPath("farmersdelight", "stove"), X); } }', mod_id=None), [("BLOCK", "stove", 1)])
        self.assertEqual(self.inv('class B { }'), [])


class Scan(Base):
    def write(self, name, source):
        f = Path(self.store.project("s_mod")["root"]) / JAVA / name; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(textwrap.dedent(source), encoding="utf8"); return f

    def test_a_fresh_project_has_nothing_untracked(self):
        out = made.scan(self.store, "s_mod")
        self.assertEqual(out["untracked"], [], "everything the generator registers is known: " + json.dumps(out["untracked"])[:300]); self.assertGreater(out["generated"], 0); self.assertEqual(out["registered"], out["generated"])

    def test_what_a_coder_left_in_the_code_is_found_adopted_or_ignored(self):
        self.write("entity/Stuff.java", '''
            class Stuff {
              static final Object GLOB = Registry.register(BuiltInRegistries.ENTITY_TYPE, ResourceLocation.fromNamespaceAndPath("s_mod", "acid_glob"), null);
              static final Object POOL = Registry.register(BuiltInRegistries.ENTITY_TYPE, ResourceLocation.fromNamespaceAndPath("s_mod", "acid_pool"), null);
              static final Object POOL_ITEM = Registry.register(BuiltInRegistries.ITEM, ResourceLocation.fromNamespaceAndPath("s_mod", "acid_pool"), null);
              static final Object HISS = Registry.register(BuiltInRegistries.SOUND_EVENT, ResourceLocation.fromNamespaceAndPath("s_mod", "hiss"), null);
            }''')
        from mod_orchestra.artreq import request_art
        request_art(self.store, "s_mod", "s_mod:FEATURE:acid_spit", "acid_spit", [GLOB])      # the glob was declared: it is tracked
        out = made.scan(self.store, "s_mod")
        self.assertEqual([(e["id"], e["kind"], e["registries"]) for e in out["untracked"]], [("acid_pool", "entity", ["ENTITY_TYPE", "ITEM"]), ("hiss", "sound", ["SOUND_EVENT"])])
        self.assertEqual(out["untracked"][0]["places"][0]["file"], JAVA + "/entity/Stuff.java"); self.assertEqual(out["untracked"][0]["places"][0]["line"], 4)
        for wrong, why in (({"cid": "nope_nothing"}, "Nothing registered"), ({"cid": "acid_pool", "card": "ghost"}, "No feature card"), ({"cid": "acid_pool", "kind": "weapon"}, "kind must be"), ({"cid": "spitter"}, "already a card"), ({"cid": "../x"}, "Not a content id")):
            with self.assertRaisesRegex(InputError, why):
                made.adopt(self.store, "s_mod", wrong.pop("cid"), **wrong)
        got = made.adopt(self.store, "s_mod", "acid_pool", card="acid_spit", what="the pool the glob leaves")
        self.assertEqual((got["kind"], got["source"], got["card"], got["registry"]), ("entity", "found", "acid_spit", "ENTITY_TYPE"))
        cards = {c["id"]: c for c in mod_map(self.store, "s_mod")["cards"]}; self.assertEqual(cards["acid_pool"]["made"], {"source": "found", "feature": "acid_spit", "registry": "ENTITY_TYPE"})
        made.ignore(self.store, "s_mod", "hiss")
        again = made.scan(self.store, "s_mod"); self.assertEqual(again["untracked"], []); self.assertEqual(again["ignored"], ["hiss"])
        made.ignore(self.store, "s_mod", "hiss", False); self.assertEqual([e["id"] for e in made.scan(self.store, "s_mod")["untracked"]], ["hiss"])
        self.assertEqual([e["id"] for e in made.view(self.store, "s_mod")["entries"]], ["acid_glob", "acid_pool"])

    def test_without_a_baseline_nothing_is_listed(self):
        from unittest.mock import patch
        with patch("mod_orchestra.fabric._generate_into", side_effect=RuntimeError("no template")):
            with self.assertRaisesRegex(StateError, "nothing was listed"):
                made.scan(self.store, "s_mod")


if __name__ == "__main__":
    unittest.main()
