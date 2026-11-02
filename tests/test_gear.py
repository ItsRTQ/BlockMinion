"""Tool/armor sets (materials) and foods: spec, generator output, post-generation add, listing."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.config import SUPPORTED_PROFILE
from mod_orchestra.gear import gear_recipes, tier_java
from mod_orchestra.spec import Food, Material, interpret, read_spec
from mod_orchestra.specedit import add_food, add_material
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError

IDEA = "items: ruby; blocks: ruby ore; tab: Ruby"
MAT = dict(identifier="ruby", label="Ruby", ingredient="ruby", tools=["sword", "pickaxe"], armor=["helmet", "boots"], durability=1200, mining_speed=8.0,
           attack_damage_bonus=3.0, mining_level="diamond", enchantability=12, armor_defense=(3, 8, 6, 3), armor_durability=30, toughness=2.0)
FOOD = dict(identifier="ruby_apple", label="Ruby Apple", nutrition=6, saturation=1.2, effects=[{"effect": "minecraft:regeneration", "duration": 100, "amplifier": 1, "chance": 1.0}], always_edible=True)


class SpecLevel(unittest.TestCase):
    def base(self):
        return interpret(name="R", mod_id="r_mod", package="com.x.r", idea=IDEA, profile=SUPPORTED_PROFILE).to_dict()

    def test_material_items_join_local_ids_and_recipes_are_standard(self):
        s = read_spec(self.base() | {"materials": [MAT]})
        self.assertEqual(sorted(s.local_ids()), ["ruby", "ruby_boots", "ruby_helmet", "ruby_ore", "ruby_pickaxe", "ruby_sword"])
        r = {x.id: x for x in gear_recipes(s)}
        self.assertEqual(r["ruby_sword"].pattern, ("X", "X", "S")); self.assertEqual(r["ruby_sword"].key, {"X": "ruby", "S": "minecraft:stick"})
        self.assertEqual(r["ruby_helmet"].pattern, ("XXX", "X X"))
        t = tier_java(s, s.materials[0])
        self.assertIn("INCORRECT_FOR_DIAMOND_TOOL", t); self.assertIn("Ingredient.of(ModMain.RUBY)", t); self.assertIn("getUses() { return 1200; }", t)

    def test_validation(self):
        for bad, msg in [(MAT | {"tools": [], "armor": []}, "at least one"), (MAT | {"mining_level": "obsidian"}, "mining_level"),
                         (MAT | {"ingredient": "emerald"}, "Unknown local ingredient"), (MAT | {"armor_defense": (1, 2)}, "four values"),
                         (MAT | {"tools": ["hammer"]}, "Unknown tool kind")]:
            with self.assertRaisesRegex(InputError, msg):
                read_spec(self.base() | {"materials": [bad]})
        with self.assertRaisesRegex(InputError, "collides"):
            read_spec(self.base() | {"materials": [MAT], "foods": [{"identifier": "ruby_sword", "label": "x"}]})
        with self.assertRaisesRegex(InputError, "vanilla id"):
            read_spec(self.base() | {"foods": [FOOD | {"effects": [{"effect": "regen"}]}]})
        with self.assertRaisesRegex(InputError, "nutrition"):
            read_spec(self.base() | {"foods": [FOOD | {"nutrition": 40}]})

    def test_vanilla_ingredient_and_tag(self):
        s = read_spec(self.base() | {"materials": [MAT | {"ingredient": "minecraft:diamond"}]})
        self.assertIn('BuiltInRegistries.ITEM.get(ResourceLocation.fromNamespaceAndPath("minecraft", "diamond"))', tier_java(s, s.materials[0]))
        s = read_spec(self.base() | {"materials": [MAT | {"ingredient": "#minecraft:planks"}]})
        self.assertIn("TagKey.create(Registries.ITEM", tier_java(s, s.materials[0]))


class Generated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="R", mod_id="r_mod", package="com.x.r", idea=IDEA)
        add_material(self.store, "r_mod", identifier="ruby", label="Ruby", ingredient="ruby", tools=["sword", "pickaxe", "axe", "shovel", "hoe"], armor=["helmet", "chestplate", "leggings", "boots"],
                     durability=1200, mining_speed=8.0, attack_damage_bonus=3.0, mining_level="diamond", enchantability=12, armor_defense=(3, 8, 6, 3), armor_durability=30, toughness=2.0)
        add_food(self.store, "r_mod", **FOOD)
        workflow.plan_project(self.store, "r_mod"); workflow.approve_spec(self.store, "r_mod"); workflow.generate_project(self.store, "r_mod")
        self.root = Path(proj["root"]); self.res = self.root / "src/main/resources"

    def test_java_and_resources(self):
        main = (self.root / "src/main/java/com/x/r/ModMain.java").read_text()
        for needle in ("Registry.registerForHolder(BuiltInRegistries.ARMOR_MATERIAL", "new ArmorMaterial(Util.make(new EnumMap<>(ArmorItem.Type.class)",
                       "SwordItem.createAttributes(RubyTier.INSTANCE, 3, -2.4F)", "PickaxeItem.createAttributes(RubyTier.INSTANCE, 1.0F, -2.8F)", "new ArmorItem(RUBY_ARMOR_MATERIAL, ArmorItem.Type.CHESTPLATE",
                       'new ArmorMaterial.Layer(id("ruby"))', 'FoodProperties.Builder().nutrition(6).saturationModifier(1.2F).effect(new MobEffectInstance(BuiltInRegistries.MOB_EFFECT.getHolder(ResourceLocation.fromNamespaceAndPath("minecraft", "regeneration")).orElseThrow(), 100, 1), 1.0F).alwaysEdible()',
                       "CreativeModeTabs.TOOLS_AND_UTILITIES", "CreativeModeTabs.COMBAT", "CreativeModeTabs.FOOD_AND_DRINKS", "output.accept(RUBY_SWORD);", "output.accept(RUBY_APPLE);"):
            self.assertIn(needle, main, needle)
        self.assertTrue((self.root / "src/main/java/com/x/r/gear/RubyTier.java").is_file())
        self.assertEqual(json.loads((self.res / "assets/r_mod/models/item/ruby_sword.json").read_text())["parent"], "item/handheld")
        self.assertEqual(json.loads((self.res / "assets/r_mod/models/item/ruby_helmet.json").read_text())["parent"], "item/generated")
        for png in ("textures/item/ruby_sword.png", "textures/item/ruby_apple.png", "textures/models/armor/ruby_layer_1.png", "textures/models/armor/ruby_layer_2.png"):
            self.assertTrue((self.res / "assets/r_mod" / png).is_file(), png)
        self.assertEqual(sorted(p.stem for p in (self.res / "data/r_mod/recipe").glob("ruby_*.json")), ["ruby_axe", "ruby_boots", "ruby_chestplate", "ruby_helmet", "ruby_hoe", "ruby_leggings", "ruby_pickaxe", "ruby_shovel", "ruby_sword"])
        lang = json.loads((self.res / "assets/r_mod/lang/en_us.json").read_text())
        self.assertEqual(lang["item.r_mod.ruby_chestplate"], "Ruby Chestplate"); self.assertEqual(lang["item.r_mod.ruby_apple"], "Ruby Apple")

    def test_listing_and_post_generation_add(self):
        from mod_orchestra.content import list_features, add_material_any, add_food_any
        from mod_orchestra.fabric import validate_generated
        kinds = {f["identifier"]: f["kind"] for f in list_features(self.store, "r_mod")}
        self.assertEqual((kinds["ruby_sword"], kinds["ruby_helmet"], kinds["ruby_apple"], kinds["ruby"]), ("tool", "armor", "food", "item"))
        out = add_material_any(self.store, "r_mod", identifier="opal", label="Opal", ingredient="minecraft:emerald", tools=["sword"], armor=[], durability=300)
        self.assertTrue(out["generated"]); self.assertEqual(out["task"], "r_mod:ADD_MATERIAL:opal")
        self.assertTrue((self.root / "src/main/java/com/x/r/gear/OpalTier.java").is_file()); self.assertTrue((self.res / "data/r_mod/recipe/opal_sword.json").is_file())
        self.assertIn("OPAL_SWORD", self.store.task_instructions("r_mod:ADD_MATERIAL:opal")); self.assertIn("OpalTier", self.store.task_instructions("r_mod:ADD_MATERIAL:opal"))
        out = add_food_any(self.store, "r_mod", identifier="opal_pie", label="Opal Pie", nutrition=8)
        self.assertEqual(out["task"], "r_mod:ADD_FOOD:opal_pie"); self.assertIn("OPAL_PIE", self.store.task_instructions("r_mod:ADD_FOOD:opal_pie"))
        self.assertEqual(validate_generated(self.root)["status"], "PASS")
        with self.assertRaisesRegex(InputError, "already exists"):
            add_material_any(self.store, "r_mod", identifier="opal", label="O", ingredient="ruby", tools=["axe"], armor=[])


if __name__ == "__main__":
    unittest.main()
