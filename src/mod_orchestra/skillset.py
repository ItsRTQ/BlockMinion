"""Which skills a coder run is given: the ones its task touches, not all of them every time.

The coder's role lists fifteen skills and every run used to carry all of them (most of its prompt), whatever the task.
A task that is a FEATURE or a CHANGE says what it is about in the user's own words; this module reads that part of the
brief (never the fixed rules that follow it, which name every kind of thing) and picks:

- the core, always: how the coder works, GameTests, and event hooks (nearly every mechanic is "when X happens, do Y");
- each topical skill whose subject the request mentions.

The rest are not lost: the prompt lists them by name with one line each, and the coder gets any of them in full with the
`orchestra_skill` tool before writing the part that needs it. Picking is generous on purpose: a skill loaded and not
needed costs a little text, a skill needed and not loaded costs a wrong guess at an API.

A task whose brief has no such part (the wiring tasks the controller writes itself, and every other role) gets `None`:
the role's own list, exactly as before.
"""
from __future__ import annotations

import re

from pathlib import Path

RESOURCES = Path(__file__).resolve().parent / "resources" / "claude"

CORE = ("coder", "gametest", "events")

# The fixed sentence that follows the user's part of each brief (`modmap.feature_instructions`, `modmap.request_change`).
# The builders use these very constants, so the split cannot drift from the text.
FEATURE_RULES_START = "Write one @GameTest per acceptance criterion that can be exercised server-side"
CAPABILITY_RULES_START = "This is a CAPABILITY carried by: "
CHANGE_RULES_START = "Make exactly this change and nothing else."
MULTI_CHANGE_RULES_START = "This is one change for several pieces:"
REQUEST_ENDS = (CAPABILITY_RULES_START, FEATURE_RULES_START, CHANGE_RULES_START, MULTI_CHANGE_RULES_START)

# skill -> what a request that needs it talks about. Whole words, any case.
TOPICS: dict[str, str] = {
    "recipes": r"craft\w*|recipes?|smelt\w*|furnaces?|ingredients?|smithing|stonecutt\w*|creative tab|drops?",
    "gui": r"screens?|menus?|gui|inventor(?:y|ies)|slots?|windows?|containers?|backpacks?|chests?|stations?|interfaces?|buttons?|storage|workbench\w*",
    "client-ui": (r"keys?|keybind\w*|keyboard|hotkeys?|hud|overlays?|bars?|press(?:es|ed|ing)?|client\w*|packets?|network\w*|sync\w*|payloads?|render\w*|"
                  r"on[- ]screen|display(?:s|ed)?|crosshairs?|scopes?|zoom\w*|indicators?|mouse|scroll\w*|(?<!right[ -])click\w*"),
    "commands": r"commands?|brigadier|permissions?|operators?|cheats?|/[a-z][a-z0-9_]{2,}(?![/.])",   # `/heal`, never a piece of a path
    "loot-and-trades": r"loot\w*|villagers?|trad(?:e|es|er|ers|ing)|dungeons?|chests?|drops?|fishing|barter\w*",
    "polish": r"particles?|animated textures?|mcmeta|advancements?|achievements?|config\w*|settings?|options?|glow\w*|trails?|sparkl\w*|smoke",
    "data": (r"mana|levels?|cooldowns?|persist\w*|sav(?:e|es|ed|ing)|stor(?:e|es|ed|ing)|remember\w*|per[- ]player|attachments?|components?|counters?|"
             r"stats?|xp|experience|energy|charg(?:e|es|ed|ing)|ammo\w*|durab\w*|nbt|progress\w*|unlock\w*|scores?|points?"),
    "effects": (r"effects?|potions?|buffs?|debuffs?|brew\w*|enchant\w*|poison\w*|burn\w*|slow\w*|regenerat\w*|wither\w*|status|heal\w*|speed(?! \d)|strength|"
                r"weak\w*|blind\w*|stun\w*|freez\w*|bleed\w*|invisib\w*|night vision|haste|resist\w*"),
    "items": (r"items?|right[- ]click\w*|throw\w*|thrown|projectiles?|wands?|grenades?|tooltips?|fuel|durab\w*|shoot\w*|shots?|fir(?:e|es|ed|ing)|weapons?|"
              r"tools?|charms?|bows?|guns?|launch\w*|cooldowns?|swords?|ammo\w*|reload\w*|bullets?|arrows?|spits?|spitting|spat|spells?|cast\w*|held|swing\w*|food|eat\w*|consum\w*"),
    "worldgen": (r"ores?|biomes?|structures?|dimensions?|world ?gen\w*|natural(?:ly)? spawn\w*|spawns? (?:in|at|naturally)|caves?|veins?|jigsaw|terrain|"
                 r"underground|nether|villages?|ruins?|temples?|towers?|portals?"),
    "mixins": (r"mixins?|inject\w*|vanilla (?:behaviou?r|mechanics?|class\w*|methods?|code)|(?:overrid\w*|chang\w*|modif\w*|replac\w*) (?:how )?vanilla|hook\w*|"
               r"player (?:model|render\w*|movement|physics)|gravity"),
    "minimap": r"mini-?maps?|map hud|top[- ]down map|radar",
}
# The same subjects in Spanish: a request is worded in the user's language (the coordinator answers in it and words the plan's
# steps from the user's own message), and a request that matches nothing would load the core alone.
TOPICS_ES: dict[str, str] = {
    "recipes": r"recetas?|craftea\w*|fabric\w*|hornos?|fund(?:e|en|ir|ido)|ingredientes?|suelt\w*|dropea\w*",
    "gui": r"pantallas?|men[uú]s?|inventarios?|ranuras?|ventanas?|contenedor\w*|mochilas?|cofres?|bot[oó]n|botones|almacen\w*|interfaz",
    "client-ui": r"teclas?|atajos?|barras?|presion\w*|puls(?:a|ar|an|ando)|en pantalla|mirilla|punto de mira|clics?|rat[oó]n|indicador\w*",
    "commands": r"comandos?|permisos?",
    "loot-and-trades": r"bot[ií]n|aldeanos?|comerci\w*|intercambi\w*|mazmorras?|cofres?|pesca",
    "polish": r"part[ií]culas?|logros?|configura\w*|ajustes?|opci[oó]n|opciones|brill\w*|humo|estelas?",
    "data": (r"man[aá]|nivel|niveles|enfriamiento|guard\w*|persist\w*|recuerd\w*|por jugador|contador\w*|estad[ií]sticas?|experiencia|energ[ií]a|carg\w*|"
             r"munici[oó]n|durabilidad|progreso|desbloque\w*|puntos?|puntuaci[oó]n"),
    "effects": (r"efectos?|poci[oó]n|pociones|encant\w*|venen\w*|quem\w*|ralentiz\w*|lent[oa]s?|regenera\w*|cur(?:a|ar|an|ación|acion)|velocidad(?! \d)|fuerza|"
                r"debilidad|ceg\w*|aturd\w*|congel\w*|sangr\w*|invisib\w*|visi[oó]n nocturna|resistencia"),
    "items": (r"objetos?|[ií]tems?|clic derecho|lanz\w*|arroj\w*|proyectil\w*|varitas?|granadas?|combustible|durabilidad|dispar\w*|armas?|herramientas?|arcos?|"
              r"espadas?|munici[oó]n|recarg\w*|balas?|flechas?|escup\w*|hechizos?|comida|com(?:e|er|en)|consum\w*"),
    "worldgen": r"menas?|minerales?|biomas?|estructuras?|dimensi[oó]n|dimensiones|cuevas?|vetas?|terreno|subterr[aá]ne\w*|aldeas?|ruinas?|templos?|torres?|portales",
    "mixins": r"inyect\w*|comportamiento vanilla|gravedad",
    "minimap": r"minimapas?",
}
_LETTER = "A-Za-z0-9áéíóúñüÁÉÍÓÚÑÜ"
_COMPILED = {name: re.compile(rf"(?<![{_LETTER}])(?:" + pattern + "|" + TOPICS_ES[name] + rf")(?![{_LETTER}])", re.I) for name, pattern in TOPICS.items()}


def request_part(brief: str) -> str | None:
    """The user's part of a FEATURE or CHANGE brief (the card and the request), or None when the brief is not one of those."""
    cut = [i for i in (brief.find(marker) for marker in REQUEST_ENDS) if i >= 0]
    if not cut:
        return None
    head = brief[:min(cut)]
    return head.split("## Task-specific instructions", 1)[-1]


def choose(text: str) -> list[str]:
    """The topical skills a request touches, in the order the tool lists them."""
    return [name for name, pattern in _COMPILED.items() if pattern.search(text or "")]


def for_task(role: str, brief: str) -> list[str] | None:
    """The skills to load for this run, or None for "the role's own list" (every role but the coder, and every coder task
    that is not a feature or a change in the user's words)."""
    if role != "coder":
        return None
    part = request_part(brief or "")
    if part is None:
        return None
    return list(CORE) + choose(part)


def skill_text(name: str) -> str | None:
    """A topical skill in full (what `orchestra_skill` returns). Role skills are not served: they are roles, not recipes."""
    if name not in TOPICS and name not in CORE:
        return None
    path = RESOURCES / "skills" / name / "SKILL.md"
    return path.read_text(encoding="utf8") if path.is_file() else None


def _about(name: str) -> str:
    text = skill_text(name) or ""
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    line = (m.group(1).strip() if m else name).split(". ")[0].rstrip(".")
    return line[:150]


def later_block(names: list[str]) -> str:
    """For the prompt: the skills this run was not given, and how to get one."""
    names = [n for n in names if n in TOPICS]
    if not names:
        return ""
    return ("\n\n# Skills not loaded for this task\n"
            "These exist and this task did not seem to need them. If it does, get the skill BEFORE you write that part: call the "
            "`orchestra_skill` tool with its name and follow what it says. Never guess an API that one of them covers.\n"
            + "\n".join(f"- `{n}`: {_about(n)}" for n in names))
