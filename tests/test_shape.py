"""The coder is told the same thing about shape wherever it is asked for behaviour: build shared behaviour once, let each piece
contribute its own values, notice repetition, and never change a sibling that was not asked about."""
import re
import unittest
from pathlib import Path

from mod_orchestra.modmap import request_change, request_feature
from mod_orchestra.shape import CODER_SHAPE_RULE, skill_section

from test_art_requests import Base

ROOT = Path(__file__).resolve().parents[1]
RULE = "\n".join(CODER_SHAPE_RULE)


class Shape(Base):
    def test_every_brief_that_asks_the_coder_for_behaviour_carries_the_rule(self):
        feature = self.store.task_instructions(request_feature(self.store, "s_mod", title="Sticky floor", description="walking on it slows you", acceptance=["it slows"])["task"])
        one = self.store.task_instructions(request_change(self.store, "s_mod", "acid_spit", "make it travel farther")["task"])
        self.assertIn(RULE, feature); self.assertIn(RULE, one)
        self.assertIn("Make exactly this change and nothing else.", one, "a change on one card is still exactly that change")
        self.assertIn("A change asked for one piece must not change its siblings.", one)
        for brief in (feature, one):
            self.assertLess(brief.index("Shape (build it so the next change is small):"), brief.index("Art: this mod never borrows vanilla visuals"), "shape before art: it decides the structure")

    def test_a_change_across_several_cards_is_built_once(self):
        cards = [c for c in ("acid_spit", "spitter") if c]
        many = self.store.task_instructions(request_change(self.store, "s_mod", cards[0], "hit harder", [cards[1]])["task"])
        self.assertIn(RULE, many); self.assertIn("build the behaviour once and let each card contribute only its own values", many)
        self.assertNotIn("Make exactly this change and nothing else.", many)

    def test_the_rule_is_worded_for_any_mod(self):
        # every concrete example an agent was given came back in its output: the rule names no particular kind of content
        text = (RULE + skill_section()).lower()
        for word in ("weapon", "gun", "rifle", "ammo", "magazine", "reload", "bullet", "sword", "wand", "musket", "zombie", "ore", "potion", "boss"):
            self.assertIsNone(re.search(rf"\b{word}s?\b", text), word)
        for must in ("lives once", "notice repetition yourself", "must not change its siblings", "do not build ahead", "in `risks`"):
            self.assertIn(must, text)

    def test_the_coder_skill_says_the_same_in_both_copies(self):
        section = skill_section()
        self.assertEqual(section.count("\n- "), 6); self.assertNotIn("\n  ", section)
        for path in (".claude/skills/coder/SKILL.md", "src/mod_orchestra/resources/claude/skills/coder/SKILL.md"):
            text = (ROOT / path).read_text(encoding="utf8")
            self.assertIn(section, text, path); self.assertLess(text.index("## Shape"), text.index("## Critical safeguards"))


if __name__ == "__main__":
    unittest.main()
