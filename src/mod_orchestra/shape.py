"""How the coder shapes what it builds, said the same way in every brief that asks it for behaviour.

The aim is that the next change is small: one more piece of the same kind, or one value tuned, touches one small place.
It is worded for any mod (a rule here must hold for a tool, a creature, a door, a spell): no examples of particular content,
because every concrete example an agent was ever given came back in its output.
"""

CODER_SHAPE_RULE = [
    "Shape (build it so the next change is small):",
    "- Look first at how this project already does the same kind of thing: a base class, a helper, a registry or a data table that the neighbours of this piece use.",
    "  If there is one, extend or configure it. Never add a second way of doing the same thing beside it.",
    "- Behaviour that several pieces share with different numbers lives ONCE (a base class, a component or a helper that takes its values as parameters or reads them",
    "  from one table). Each piece contributes only what is its own: its values, its name, its look. A piece is a few lines of configuration, never a copy of the logic.",
    "- Notice repetition yourself, even when the request names a single piece: if what you are about to write already exists in a sibling with other numbers, move the",
    "  common part to one place and make both use it when that is a small, safe step. When it is not, make the requested change and say in `risks` what is duplicated",
    "  and where, so it can be planned as its own step.",
    "- A change asked for one piece must not change its siblings. If the behaviour is shared, give that piece its own value or switch; do not edit the shared default",
    "  unless the request is about all of them.",
    "- The values a person will want to tune (amounts, durations, rates, ranges, costs) are named in one place per piece, not scattered as literals through the logic.",
    "- Do not build ahead: no parameter, option or layer that nothing uses yet.",
]



def skill_section() -> str:
    """The same rule as a section of the coder's skill: one bullet per line."""
    bullets: list[str] = []
    for line in CODER_SHAPE_RULE[1:]:
        if line.startswith("- "):
            bullets.append(line)
        else:
            bullets[-1] += " " + line.strip()
    return "## Shape\nBuild it so the next change is small.\n" + "\n".join(bullets) + "\n"
