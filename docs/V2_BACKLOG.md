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
