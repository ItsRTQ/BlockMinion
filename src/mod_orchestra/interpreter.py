"""R3: conversational interpreter (v1 criterion 1).

The interpreter role turns free text into a validated schema-2 spec. It runs as an ordinary
bounded worker on the <project>:SPEC task; its handoff carries a `spec` proposal and up to
three `questions`. The controller validates the proposal with the same rules as
`craftctl add-recipe/add-drop/set-tab`, stores it as the DRAFT spec, and waits for the user:
answers are appended to the idea (`craftctl answer`), approval is `craftctl approve-spec`.
The worker never writes the database and never widens scope on its own.
"""
from __future__ import annotations
import re
import json
from .spec import Spec, read_spec, SCHEMA_VERSION, RECIPE_KINDS
from .state import Store, StateError
from .validation import InputError

MAX_QUESTIONS = 3

SPEC_INSTRUCTIONS = f"""
## Your job on this task (interpreter)
Turn the user's idea into a complete, concrete spec for a Fabric 1.21.1 mod using ONLY what the generator
supports: items, blocks, a creative tab, crafting/smelting recipes, block drops, tool/armor sets from a material
(sword, pickaxe, axe, shovel, hoe, helmet, chestplate, leggings, boots with vanilla-like numbers), foods, and simple mobs (a GeckoLib
entity with idle + walk animations, basic AI — passive wanders, neutral fights back when hurt, hostile attacks players —, spawn egg, loot on death with counts and chance). Preserve the user's
intent and wording; do not add content they did not ask for; do not drop content they did ask for.
Mechanics the generator cannot express (a mob infecting or converting others, projectiles and spit attacks, new status effects, custom AI and targeting rules,
mobs that break blocks or jump unusually high, bosses with phases, GUIs, commands, events) are NOT dropped and NOT faked as items: write each as a `behavior` (below), which
the coder implements after generation and proves with GameTests. Use `unknowns` only for wishes that no behavior could describe, and ask about them only if they block the rest.

Ask at most {MAX_QUESTIONS} questions, and only when the answer changes files the user DID ask for: ambiguous
counts, missing ingredients for a recipe the user implied, or which block an ore should drop from. Never ask
whether to ADD something they did not mention (extra recipes, variants, deepslate ores, a tab): if they did
not ask for it, leave it out and note it once under `assumptions`. A clear idea deserves zero questions. Prefer sensible vanilla
defaults (ore → 1 gem, Fortune, Silk Touch; 9 gems ↔ 1 block; smelting 0.7 xp / 200 ticks) and state them
in `assumptions` instead of asking. Write everything in English identifiers (snake_case) even if the user
wrote in Spanish; keep labels in the user's language.

Put the proposal in the handoff under `spec` with EXACTLY this shape (schema_version {SCHEMA_VERSION}):
```json
{{"features": [{{"kind": "item|block", "identifier": "snake_case", "label": "Display Name", "tool": "pickaxe|axe|shovel|hoe|none (blocks)", "mining_level": "wood|stone|iron|diamond|netherite (blocks)", "variants": ["stairs","slab","fence","wall"] (blocks, optional)}}],
  "tab": "Tab Label or null", "tab_icon": "identifier of one feature or null",
  "recipes": [{{"id": "snake_case", "kind": "{'|'.join(RECIPE_KINDS)}", "result": "identifier or minecraft:id",
               "count": 1, "pattern": ["RRR"," S "," S "], "key": {{"R": "identifier", "S": "minecraft:stick"}},
               "ingredients": ["identifier", "minecraft:id", "#minecraft:tag"], "experience": 0.7, "cooking_time": 200}}],
  "drops": [{{"block": "identifier", "item": "identifier or minecraft:id", "count_min": 1, "count_max": 1, "fortune": true, "silk_touch": true}}],
  "mobs": [{{"identifier": "snake_case", "label": "Display Name", "behavior": "passive|neutral|hostile", "health": 10, "speed": 0.25,
            "width": 0.8, "height": 0.9, "attack_damage": 3, "drops": [{{"item": "identifier or minecraft:id", "count_min": 1, "count_max": 1, "chance": 1.0}}], "egg_colors": [9075153, 15128831], "body_plan": "quadruped|biped|bird|fish|serpent|insect|primate", "held_item": "",
            "spawn": {{"biomes": ["overworld" or "#minecraft:is_forest" or "minecraft:plains"], "weight": 10, "min_group": 1, "max_group": 3}} or null for egg-only}}],
  "materials": [{{"identifier": "ruby", "label": "Ruby", "ingredient": "ruby or minecraft:diamond", "tools": ["sword","pickaxe","axe","shovel","hoe"],
                 "armor": ["helmet","chestplate","leggings","boots"], "durability": 1200, "mining_speed": 8.0, "attack_damage_bonus": 3.0,
                 "mining_level": "wood|stone|iron|diamond|netherite", "enchantability": 12, "armor_defense": [3, 8, 6, 3], "armor_durability": 30,
                 "toughness": 2.0, "knockback_resistance": 0.0, "recipes": true, "armor_style": "textured|3d (3d only when the user describes sculpted shapes: crests, pauldrons, horns)"}}],
  "foods": [{{"identifier": "ruby_apple", "label": "Ruby Apple", "nutrition": 6, "saturation": 1.2,
             "effects": [{{"effect": "minecraft:regeneration", "duration": 100, "amplifier": 0, "chance": 1.0}}], "always_edible": false, "fast": false}}],
  "sounds": [{{"identifier": "critter_chirp", "label": "Critter chirps", "category": "neutral"}}],
  "enchantments": [{{"identifier": "gem_edge", "label": "Gem Edge", "kind": "damage|protection|fire_aspect", "max_level": 3, "items": "#minecraft:enchantable/weapon", "weight": 5}}],
  "structures": [{{"identifier": "gem_shrine", "label": "Gem Shrine", "layers": [["SSS","SSS","SSS"],["S.S","...","S.S"],["GGG","G.G","GGG"]], "legend": {{"S": "minecraft:stone_bricks", "G": "gem_block"}}, "spacing": 32, "separation": 8, "biomes": ["overworld"], "step": "surface_structures"}}],
  "biomes": [{{"identifier": "gem_fields", "label": "Gem Fields", "base": "plains|forest|desert|taiga|snowy_plains|swamp", "temperature": 0.8, "downfall": 0.4, "sky_color": "#78A7FF", "fog_color": "#C0D8FF", "water_color": "#3F76E4", "grass_color": "", "foliage_color": "", "mobs": ["local mob ids"]}}],
  "dimensions": [{{"identifier": "gem_realm", "label": "Gem Realm", "biomes": ["gem_fields"], "sky": "overworld|nether|end", "fixed_time": -1, "noise": "minecraft:overworld|minecraft:floating_islands|minecraft:caves|minecraft:amplified"}}],
  "ores": [{{"block": "crystal_ore", "vein_size": 9, "veins_per_chunk": 8, "min_y": -64, "max_y": 64, "biomes": ["overworld"], "discard_on_air": 0.0}}],
  "theme": "2-4 sentences: visual brief for all art in this mod — era/culture, palette (3-5 colours with hex), materials, motifs, mood (e.g. 'Egyptian royal: gold #e3b341 with lapis #2b4fa3 bands, falcon and sun motifs, polished stone; heavy, ceremonial')",
  "assumptions": ["..."]}}
```
Material reference numbers: iron = durability 250 / speed 6 / bonus 2 / level iron / ench 14 / defense 2,6,5,2 / armor dur 15;
diamond = 1561 / 8 / 3 / diamond / 10 / 3,8,6,3 / 33 / toughness 2; netherite = 2031 / 9 / 4 / netherite / 15 / 3,8,6,3 / 37 / toughness 3 / kb 0.1.
A material's items are named <material>_<kind> and must not collide with other content.
Rules the controller enforces (a violation fails your handoff): identifiers unique and snake_case (2-50 chars);
recipe ingredients/results must be features of this mod, `minecraft:` ids or `#minecraft:` tags; shaped patterns
1-3 rows of equal width (1-3 chars, space = empty) and every symbol in `key`; cooking recipes have exactly one
ingredient; one drop rule per block, and the block must be one of the features; the tab icon must be a feature;
mob identifiers must not collide with items/blocks (their spawn egg is <id>_spawn_egg); mob health 1-1024, speed 0.05-1.5.
Ores and stone-like blocks: tool pickaxe and a mining_level (iron for valuable ores); wood/plants: axe/hoe; soil: shovel.
Structures: small (≤ 9x9x9) text-layer builds, bottom layer first, '.' = air; custom biomes only live in custom dimensions (vanilla overworld biome injection is not supported); a dimension gets a key item automatically.
Every block named "ore" gets an `ores` worldgen entry (reference: iron 9/10 per chunk y -64..72; diamond 8/7 y -64..16 discard 0.7; emerald rare 3/1 mountains).
Mobs the user describes as living somewhere ("in forests", "at night in caves") get a `spawn`; otherwise null (egg only).
Every mob gets a `body_plan`, the base rig its model starts from: humanoids (orcs, goblins, zombies, villagers, golems, knights) biped;
four-legged animals (wolves, deer, cows, cats) quadruped; birds and bats bird; fish, whales, sharks fish; snakes and worms serpent;
spiders, beetles, crabs and other many-legged creatures insect; apes, gorillas, chimpanzees and other knuckle-walking primates primate. Pick by the creature's body, not its size; omit only when unsure (quadruped).
Behaviors (`"behaviors"` in the spec, a list; empty when the idea has only content): each is `{{"title": "3-60 characters, plain", "description": "what must happen, in the user's terms, with EVERY number the user gave (80 health, 4 blocks, deepslate but not obsidian)",
"acceptance": ["1-12 observable criteria, each provable by one server-side GameTest, e.g. 'a villager hit by a runner converts into one of the three variants after the infection time'"], "affects": ["identifiers of the mobs/items/sets it is about"], "after": ["titles of behaviors it builds on"], "kind": "capability|mechanic"}}`.
A behavior is a `capability` when it is something mobs CARRY (infection, a freezing touch, an explosion on death, a regeneration aura): `affects` then lists exactly the mobs that carry it, which the user sees as checkboxes and corrects, and it is built once as a
reusable component wired to each carrier. Everything else (one mob's movement, one projectile, a one-off rule) is a `mechanic`. Describe in a capability how each carrier applies it when they differ (a melee hit, a projectile); a delivery that is a mechanic of its own (a
spit projectile) is a separate behavior that comes `after` the capability.
Group related mechanics into 3-6 coherent behaviors (a whole infection system in one, a ranged attack with its effect in another, one mob's block-breaking and jumping in another), never one per sentence and never one giant card.
Order them so that foundations come first. Use `after` ONLY when a behavior needs code or an effect that another one creates (the acid needs the infection system); independent mechanics, such as one mob's movement versus its attacks or two different mobs, must not wait for each other.
Say WHEN every mechanic triggers (on hit, on death, after a delay) and what every new effect, projectile or state DOES in numbers (damage per second, duration, speed, range), with a criterion that proves it: a behavior that only names an effect leaves the coder to invent it.
Infer the mechanism that makes the idea hang together. What the user says explicitly always wins: if they limit something ("only the Spitter spits", "just the Brute breaks blocks"), only those have it, and a description of one member doing something never limits the others by itself.
Where the user did not limit it, a capability given to a whole group ("these zombies can infect ...", "all the golems repair ...") belongs to every member of that group.
When the idea introduces a new status effect and ties a consequence to it (a mob that dies under it transforms, drops something or changes state), that effect IS how the group does the thing: put the effect and its
consequence in ONE foundation behavior, then give every member the user says can do it its own way of applying it (melee hit, projectile, aura) in a behavior that comes `after` the foundation. Never leave a member
without the capability, and never let a member bypass the effect with a shortcut of your own. List every inference like this under `assumptions`, so the user can see how far you went.
If the idea allows two readings that would build different things (infect on hit versus convert on death), state the reading you chose as the FIRST assumption. When the user says something happens "at random", add a criterion that over many trials every outcome appears. Do not invent mechanics the user did not describe; where the user left a number open (infection time, damage), pick a sensible one, put it in the description
and list it under `assumptions`. Mobs a behavior is about must still be listed under `mobs` with their stats; a behavior never replaces the mob.
Field limits (a proposal that breaks a structural one is rejected and you are asked to resend it; cosmetic text is trimmed to fit): art.concept 320 characters, art.silhouette 60 (a short phrase, not a sentence),
each tag 2-48 characters and at most 16 tags, each art.pieces text 320; behavior title 3-60 characters, description 20-1500, 1-12 criteria of 5-300 characters each, at most 12 behaviors; theme 600 characters.
Art direction (`art`): every feature, tool/armor set (material), food and mob takes an `"art"` object so the designer paints something specific to it, never a stock icon:
`{{"concept": "one or two sentences: what it is and how it looks, in this mod's world", "tags": ["6-10 concrete visual cues"], "silhouette": "optional shape phrase"}}`.
A material's `art` also carries `"pieces": {{"sword": "its own sentence", "pickaxe": "...", "helmet": "...", ...}}` with a different shape idea for every piece of the set.
Draw the cues from the user's idea and from your `theme`: shapes (serrated edge, hooked beak), materials (hammered iron, bone, leather lashing), colours (rust red, ash grey),
wear (chipped, patched, soot-stained) and symbols; never mood words (epic, cool, powerful) and never generic ones (shiny, nice). Things in one set share palette and motifs but not silhouette.
Example, tool set of an ork warband: `"art": {{"concept": "crude black-iron weapons beaten out in a hurry, wrapped in leather and decorated with the bones of past victims", "tags": ["serrated edge", "bone teeth", "hammered iron", "leather lashing", "rust red", "chipped"], "pieces": {{"sword": "a notched cleaver with bone teeth lashed along the edge", "axe": "a slab of iron on a gnarled haft with a skull knob", "helmet": "a dented bucket helm with a horn bolted on one side"}}}}`.
A biped carries the best weapon or tool among its drops (sword, axe, pickaxe, shovel, hoe) in its right hand, drawn on the model; leave `held_item` "" for that,
"none" for empty hands, or an item id to choose which item it holds.
Also put the questions (if any) under `questions`, as a list of plain sentences addressed to the user.
Use status WAITING_USER (the user must answer or approve); never DONE. Do not create or edit any files.

HARD REQUIREMENT: the `spec` object MUST be a key INSIDE the ```handoff JSON block. Prose, tables or a
summary outside the block are ignored by the controller; a handoff without `spec` is rejected and the run
is wasted. Keep explanations short and put them under `assumptions`/`unknowns`.
"""


_BAD_CHARS = re.compile(r"[\x00-\x1f<>{}\[\]\\]")


def _fit(text, limit: int) -> tuple[str, bool]:
    """Plain text of at most `limit` characters: control and bracket characters become spaces, spaces collapse, a long text is cut at a word boundary."""
    t = re.sub(r"\s+", " ", _BAD_CHARS.sub(" ", str(text or ""))).strip()
    if len(t) <= limit:
        return t, False
    cut = t[:limit]
    if " " in cut and cut.rfind(" ") >= int(limit * 0.6):
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-"), True


def _fit_art(art, label: str, notes: list[str], piece_kinds: tuple = ()):
    """The cosmetic art fields of an agent's proposal, fitted to their limits (the user's own edits stay strict): the proposal is not rejected over a long phrase."""
    if isinstance(art, str):
        art = {"concept": art}
    if not isinstance(art, dict):
        return art
    out = dict(art)
    for key, limit in (("concept", 320), ("silhouette", 60)):
        if key in out:
            out[key], cut = _fit(out[key], limit)
            if cut:
                notes.append(f"{label} art.{key} to {limit} characters")
    if "tags" in out:
        raw = out["tags"] if isinstance(out["tags"], (list, tuple)) else re.split(r"[,;\n]", str(out["tags"]))
        tags, seen = [], set()
        for t in raw:
            fitted, cut = _fit(t, 48)
            if cut:
                notes.append(f"{label} a tag to 48 characters")
            if len(fitted) >= 2 and fitted.lower() not in seen:
                seen.add(fitted.lower()); tags.append(fitted)
        if len(tags) > 16:
            notes.append(f"{label} art.tags to 16 tags")
        out["tags"] = tags[:16]
    if isinstance(out.get("pieces"), dict):
        pieces = {}
        for k, v in out["pieces"].items():
            if piece_kinds and k not in piece_kinds:
                notes.append(f"{label} art.pieces.{k} dropped (not a piece of this set)")
                continue
            pieces[k], cut = _fit(v, 320)
            if cut:
                notes.append(f"{label} art.pieces.{k} to 320 characters")
        out["pieces"] = pieces
    return out


def fit_proposal(proposal: dict) -> tuple[dict, list[str]]:
    """Fit the cosmetic text of an agent's proposal (art sheets, behavior descriptions and criteria) to the spec's limits and return what was trimmed.
    Structure, identifiers, numbers and titles are never touched: a real mistake there is still rejected, with its reason, for the agent to fix."""
    import copy
    p, notes = copy.deepcopy(proposal), []
    for key, label in (("features", "item"), ("foods", "food"), ("mobs", "mob")):
        for e in p.get(key) or []:
            if isinstance(e, dict) and e.get("art") is not None:
                e["art"] = _fit_art(e["art"], f"{label} {e.get('identifier', '?')}", notes)
    for m in p.get("materials") or []:
        if isinstance(m, dict) and m.get("art") is not None:
            m["art"] = _fit_art(m["art"], f"material {m.get('identifier', '?')}", notes, tuple(m.get("tools") or ()) + tuple(m.get("armor") or ()))
    for b in p.get("behaviors") or []:
        if not isinstance(b, dict):
            continue
        if "description" in b:
            b["description"], cut = _fit(b["description"], 1500)
            if cut:
                notes.append(f"behavior {b.get('title', '?')} description to 1500 characters")
        if isinstance(b.get("acceptance"), (list, tuple)):
            fitted = []
            for a in b["acceptance"]:
                text, cut = _fit(a, 300)
                if cut:
                    notes.append(f"a criterion of behavior {b.get('title', '?')} to 300 characters")
                if len(text) >= 5:
                    fitted.append(text)
            if len(fitted) > 12:
                notes.append(f"behavior {b.get('title', '?')} criteria to 12")
            b["acceptance"] = fitted[:12]
    return p, notes


def spec_from_proposal(current: dict, proposal: dict) -> Spec:
    """Merge a worker's proposal onto the project's identity fields and validate it as a real spec."""
    if not isinstance(proposal, dict):
        raise InputError("spec proposal must be an object")
    proposal, trimmed = fit_proposal(proposal)
    raw = {
        "schema_version": SCHEMA_VERSION, "name": current["name"], "mod_id": current["mod_id"], "package": current["package"],
        "idea": current["idea"], "profile": current["profile"],
        "features": proposal.get("features", []), "recipes": proposal.get("recipes", []), "drops": proposal.get("drops", []),
        "tab": proposal.get("tab"), "tab_icon": proposal.get("tab_icon"), "mobs": proposal.get("mobs", []),
        "materials": proposal.get("materials", []), "foods": proposal.get("foods", []), "theme": proposal.get("theme", ""), "sounds": proposal.get("sounds", []), "ores": proposal.get("ores", []), "enchantments": proposal.get("enchantments", []),
        "structures": proposal.get("structures", []), "biomes": proposal.get("biomes", []), "dimensions": proposal.get("dimensions", []),
        "behaviors": proposal.get("behaviors", []),
        "questions": [], "assumptions": [str(a) for a in proposal.get("assumptions", [])][:12],
    }
    if trimmed:   # visible to the user with the other assumptions
        shown = "; ".join(trimmed[:6]) + (f"; and {len(trimmed) - 6} more" if len(trimmed) > 6 else "")
        raw["assumptions"] = raw["assumptions"][:11] + [f"Trimmed to fit the spec's limits (the wording was kept): {shown}."]
    spec = read_spec(raw)
    from .spec import has_content
    if not has_content(spec):
        raise InputError("spec proposal has no items, blocks, mobs, materials, foods, enchantments, structures, biomes, dimensions or sounds")
    from .spec import check_java_name_collisions
    check_java_name_collisions(spec.features)
    return spec


def apply_interpretation(store: Store, pid: str, handoff: dict, run_id: str) -> dict:
    """Validate and store the interpreter's proposal; return what the user must do next."""
    questions = [str(q).strip() for q in (handoff.get("questions") or []) if str(q).strip()]
    if len(questions) > MAX_QUESTIONS:
        raise InputError(f"interpreter asked {len(questions)} questions; the limit is {MAX_QUESTIONS}")
    proposal = handoff.get("spec")
    if proposal is None:
        raise InputError("interpreter handoff has no `spec` proposal")
    current = store.project(pid)["spec"]
    spec = spec_from_proposal(current, proposal)
    stored = spec.to_dict() | {"questions": questions}
    store.replace_spec(pid, stored, actor=f"run:{run_id}", reason="interpreter proposal")
    summary = {"features": [f"{f.kind}:{f.identifier}" for f in spec.features], "recipes": [r.id for r in spec.recipes],
               "drops": [f"{d.block}->{d.item}" for d in spec.drops], "tab": spec.tab, "mobs": [f"{m.identifier} ({m.behavior})" for m in spec.mobs],
               "materials": [m.identifier for m in spec.materials], "foods": [f.identifier for f in spec.foods], "questions": questions,
               "assumptions": spec.assumptions}
    store.add_event(pid, "controller", "SPEC_PROPOSED", {"run": run_id, **summary})
    next_steps = ([f'craftctl answer {pid} "<your answer to: {q}>"' for q in questions] or []) + [f"craftctl approve-spec {pid}"]
    return summary | {"needs_user": next_steps}


def answer(store: Store, pid: str, text: str) -> dict:
    """USER-ONLY: append an answer to the idea and reopen the SPEC task for another interpreter pass."""
    text = text.strip()
    if not text:
        raise InputError("Answer is empty")
    proj = store.project(pid)
    if proj["status"] not in ("IDEA", "PLAN_READY"):
        raise StateError("The idea cannot change once source is generated")
    spec = dict(proj["spec"])
    questions = spec.get("questions") or []
    spec["idea"] = spec["idea"].rstrip() + "\n\n[user answer] " + text
    spec["questions"] = []
    store.replace_spec(pid, spec, actor="user", reason="answer")
    store.add_event(pid, "user", "ANSWER", {"text": text[:300], "answered": questions[:3]})
    task_id = f"{pid}:SPEC"
    state = next((t["state"] for t in store.tasks(pid) if t["id"] == task_id), None)
    if state in ("WAITING_USER", "FAILED", "BLOCKED", "DONE"):
        if state == "DONE":
            with store.tx() as con:
                con.execute("UPDATE tasks SET state='READY',version=version+1,lease_owner=NULL,lease_expiry=NULL WHERE id=?", (task_id,))
        else:
            store.requeue(task_id, "answer given")
    return {"project": pid, "idea_appended": True, "spec_task": task_id, "next": f"craftctl dispatch {pid} --task {task_id}"}
