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
- Rig library follow-ups (jointed limbs and the attack clip landed 2026-11-04): a third joint (hand/foot) and a `death` clip with `hold_on_last_frame` + entity removal delay; UV-rectangle opacity check against the PNG in `validate_model_files`; optional `body_plan` inference from the interpreter's mob text (only with a zero-false-positive vocabulary); "import your own .bbmodel" from the UI (decided 2026-11-04: v2).
- Animation states beyond idle/walk/attack: `run` (speed threshold), `hold` state clips with part visibility via scale 0 (carrying, sitting), and an optional `emote` one-shot the controller can trigger from a command; learned from community models on 2026-11-05.
- Skins: patterns beyond plain zones and bands (plates, straps, scales, fur tufts), a mirror of the painter for non-head faces (snout, beak, visor), a held-item texture check, and re-painting existing mobs from the UI without a MODEL task.
- Art direction follow-ups: variant masks per kind (several sword/axe/helmet silhouettes chosen from the tags) so the placeholders are not one template before a designer runs; art sheets for enchantments, structures, biomes and dimensions; an interpreter pass that writes sheets for projects whose spec predates them (today the derivation fills in).
- Icons: design the icons of items added after generation automatically too (today they get the placeholder until Redesign is used), a per-project switch to turn the automatic first design off, and a before/after view of a redesign in the contact sheet.
- Behaviors: edit or add a behavior from the Spec tab (today the answer box asks the interpreter to change it, and the Mod Map adds cards by hand after generation), a cost estimate per behavior before approving, and a spec with only behaviors (a mod with no generated content) once the generator supports an empty scaffold.

