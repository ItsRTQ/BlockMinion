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

## Creative freedom: what is left
- Painter as a toolbox of generic operations (fill, noise, gradient, scatter, line) with no presets and no suggested values; today it is presets (`flesh`, `rotten`, `hide`, `cloth`) plus free hand painting.
- Mood dials and reference images in the icons and armor redesign dialogs (today only mobs have them).
- A way to measure how different two or three designs of the same prompt are (proportions, palette) so variety can be checked and not only hoped for.
- Proportion dials (head size, shoulder and limb mass, hunch) over the existing body plans, if the scaffold turns out to be the main reason designs look alike. Per-bone scale (GeckoLib `GeoBone.setScaleX/Y/Z` at render time) is the cheap way in: like `Mob.scale`, it touches neither the geometry nor the skin.

## Editing models after generation: what is left
- More edits without an agent next to `edit-model --scale`: per-bone scale (above), separate width/height scale (`withScale(w, h)` in the renderer plus `EntityDimensions`), and the interpreter reading sizes from the user's words ("a giant", "tiny").
- Install my Blockbench edits for 3D items and projectiles (export, validate without the render, install as a user revision, re-wire actions); today they can be opened but edits there do not reach the game.
- Player animations, later: PAL's first-person mode (THIRD_PERSON_MODEL) as an alternative to fp_ parts, player animations not tied to an item (emotes, movement), and a player rig with bend helpers.
- 3D blocks, later: a collision/selection shape that follows the model, a facing property (GeoBlockRenderer turns by FACING when the block has one), 3D block items in the inventory, and block variants (stairs, slabs) of a 3D block.
- 3D items, later: enchantment glint on the 2D inventory icon of a 3D item, 3D block items, Modify for 3D items, an option to make every weapon 3D on the first run, hold previews in textured colour, and a left-hand preview.
- Art for coder-made content, later: projectiles as spec content (seen and edited in Spec before generation, A of the original proposal), 3D GeckoLib projectiles and entity models requested by the coder (today only flat textures), and showing pending and painted coder art on the feature card.
- Bring back an earlier version of a model: every version now keeps its `.bbmodel`, geo and animation; a "use this version" button would reinstall one (and a side-by-side render of before and after a modification).
- Recolour without an agent: the texture's real palette as chips, change one colour and keep each pixel's lightness (shading and detail stay).
- Use my model, later: per-face UV models, Molang expressions in keyframes, and a model whose bones the entity code expects under other names (held_item).
- A general `regenerate` for projects made by an older generator: rewrite only the files whose hash is still the generator's, and hand the rest to the coder as a diff. `edit-model` applies that rule to one line of one file.
- Mod Map 2.0 follow-ups (2026-11-13): persist the automatic cell of each card (today remembered per session, so a reload can move cards the user never placed when a card is added); nest a folder by dropping it on another (today: "Move into…" in its inspector); curved or routed bundles when several share an axis; a "classic" flat view if anyone misses it; touch pinch; rule editor for user-defined tag inference; AI-suggested classification kept reviewable (nothing uses an agent to classify today); `craftctl` commands for folders.
