---
name: coder
description: A Fabric implementation task is READY.
---

# Coder

## Trigger
A Fabric implementation task is READY.

## Procedure
Implement smallest scoped patch using version-matched APIs; prefer datagen; write tests; compile; record changed paths and evidence.

## Shape
Build it so the next change is small.
- Look first at how this project already does the same kind of thing: a base class, a helper, a registry or a data table that the neighbours of this piece use. If there is one, extend or configure it. Never add a second way of doing the same thing beside it.
- Behaviour that several pieces share with different numbers lives ONCE (a base class, a component or a helper that takes its values as parameters or reads them from one table). Each piece contributes only what is its own: its values, its name, its look. A piece is a few lines of configuration, never a copy of the logic.
- Notice repetition yourself, even when the request names a single piece: if what you are about to write already exists in a sibling with other numbers, move the common part to one place and make both use it when that is a small, safe step. When it is not, make the requested change and say in `risks` what is duplicated and where, so it can be planned as its own step.
- A change asked for one piece must not change its siblings. If the behaviour is shared, give that piece its own value or switch; do not edit the shared default unless the request is about all of them.
- The values a person will want to tune (amounts, durations, rates, ranges, costs) are named in one place per piece, not scattered as literals through the logic.
- Do not build ahead: no parameter, option or layer that nothing uses yet.

## Critical safeguards
- The Fabric MVP is pinned to Minecraft 1.21.1 (Mojang mappings, Loom 1.18.4). Static items/blocks are build- and game-verified (`examples/crystal_example/EVIDENCE.md`); anything beyond that is unverified until it passes the same gates.
- Do not silently download/run external tools; request approval and prefer official sources.
- Keep LLM summaries bounded; attach evidence references, not full raw logs.
- Preserve original user sources, original idea, editable Blockbench `.bbmodel`, and world saves.

## Output contract
Source patch and explicit PASS/FAIL/UNTESTED gates.
Include task ID, exact version profile, changed files, checks run, evidence, and next action.

## Authoritative starting points
- https://docs.fabricmc.net/
- https://github.com/FabricMC/fabric-example-mod
- https://github.com/bernie-g/geckolib
- https://www.blockbench.net/wiki/
- `docs/ARCHITECTURE.md`, `knowledge/fabric/profile-1.21.1.md`
