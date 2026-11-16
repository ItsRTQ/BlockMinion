---
name: interpreter
description: New project idea, change request, or ambiguous user wish.
---

# Interpreter

## Trigger
New project idea, change request, or ambiguous user wish.

## Procedure
1. Read the user's idea (and any `[user answer]` lines appended to it). Keep their wording for labels; derive snake_case identifiers.
2. Map every wish onto what the generator supports: items, blocks, one creative tab, crafting (shaped/shapeless) and cooking recipes, block drops. Use the `recipes` skill for standard patterns and vanilla ids.
3. Anything unsupported (mobs, biomes, dimensions, armor/tool stats, GUIs, commands) goes to `unknowns`, never faked as an item; ask about it only if it blocks the rest.
4. Choose vanilla-like defaults and list them in `assumptions` (ore → gem with Fortune/Silk Touch, 9 gems ↔ 1 block, smelting 0.7 xp). Ask at most three questions, only when the answer changes files.
5. Return the proposal under `spec` in the handoff (shape given in the task instructions) with status WAITING_USER. The controller validates it and stores it as DRAFT; the user answers or approves in the tool. You never edit files or the database.

## Critical safeguards
- The Fabric MVP is pinned to Minecraft 1.21.1 (Mojang mappings, Loom 1.18.4). Static items/blocks are build- and game-verified (`examples/crystal_example/EVIDENCE.md`); anything beyond that is unverified until it passes the same gates.
- Do not silently download/run external tools; request approval and prefer official sources.
- Keep LLM summaries bounded; attach evidence references, not full raw logs.
- Preserve original user sources, original idea, editable Blockbench `.bbmodel`, and world saves.

## Output contract
A versioned ModSpec with acceptance criteria and explicit unresolved questions.
Include task ID, exact version profile, changed files, checks run, evidence, and next action.

## Authoritative starting points
- https://docs.fabricmc.net/
- https://github.com/FabricMC/fabric-example-mod
- https://github.com/bernie-g/geckolib
- https://www.blockbench.net/wiki/
- `docs/ARCHITECTURE.md`, `knowledge/fabric/profile-1.21.1.md`
