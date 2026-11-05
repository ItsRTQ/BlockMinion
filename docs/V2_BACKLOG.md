# v2 backlog

Ideas that do not advance a v1 criterion (`docs/V1_DEFINITION.md`). Nothing here is built before `v1.0.0`.

- R7 World Builder: biomes, features, structures, dimensions, seed testing.
- R9 First-run setup wizard, desktop packaging.
- R10 Distribution, auto-update, telemetry opt-in, beta program.
- R11 NeoForge / newer Minecraft profiles.
- Mobs beyond "simple": bosses, phases, custom AI, custom sounds, variants, natural spawning.
- MCP Resources/Prompts (M6), official MCP SDK migration (M7).
- Guard hardening against indirection (A7) beyond the controller boundary.
- Evidence carry-over by artifact hash: when a rebuilt JAR's SHA-256 equals one already CLIENT/CONTENT-verified, inherit that evidence instead of asking the user to re-test (identical artifact ⇒ identical behaviour).
- Session cost telemetry: per-session agent spend summary (`craftctl costs`) to tune orchestrate budgets from data (2026-10-21 session: ≈$6.60; repairs $0.40–0.62 each; one unguarded qa run $2.11, since prevented by E1).
- Blockbench live editing via sosadly/blockbench-mcp (create_rig, generate_animation) as a designer-in-the-loop path; adhi-jp as MIT live alternative. Decision 2026-10-22: v1 uses the jasonjgardner headless server only (see knowledge/blockbench/mcp-audit.md).
- **Mod Map** (branch `v2/mod-map`, not merged before v1.0.0): feature cards + derivation graph; change requests scoped to a card; custom feature requests with acceptance criteria. First step of carril 2; next: GUI/networking/data skills and a GameTest harness so custom features get automated checks.
- 3D `java_block` items/blocks in the generator (held weapons, furniture blocks): emit `models/item|block/*.json` with the 1.21.1 element/rotation/display validators and the handheld/block presets from `knowledge/blockbench/formats-java-1.21.1.md`; GeckoLib `GeoItemRenderer` path (`builtin/entity` + `BuiltinItemRendererRegistry`) for animated items.
- GeckoLib locators + `particle_effects`/`sound_effects` keyframes (footstep dust, attack sparks) in the blockbench server and skill.
- Profile migration notes for 1.21.4+: client item definitions (`assets/<ns>/items/*.json`, `minecraft:item_model`) replace `overrides`; `EntityModel<EntityRenderState>` for any vanilla `ModelPart` code; see §8 of the formats note.
- Rig library follow-ups: `jointed_leg()` helper (2–3 segment limbs, the main source of bone count in finished community creatures); `animation.<mob>.attack` for hostile mobs via `triggerAnim` plus optional extra clips accepted by the validator; optional `body_plan` inference from the interpreter's mob text (only with a zero-false-positive vocabulary); "import your own .bbmodel" from the UI (decided 2026-11-04: v2).

