# Roadmap and engineering backlog (historical)

> **Superseded 2026-10-19.** This file is kept as the v0.1.0 planning history. The forward plan is `docs/DEVELOPMENT_PATH.md` (releases R0–R11); milestones below map roughly M0→R0, M1→R1, M2→R1/R2, M3→R2–R5, M4→R6, M5→R7, M6→R9–R10.

**Legend:** DONE = implemented and locally unit-tested; PROTOTYPE = partially functional; PLANNED = not shipped. Exit criteria are independent evidence, not AI confidence.

## M0 — Repository + audited design (DONE)

- [x] GitHub-ready Python package with MIT license (until the licensing transition; see CHANGELOG.md), CI, standard-library runtime, CLI and browser UI.
- [x] Preserve the original v2 design and user-selected hybrid/Fabric/approval decisions.
- [x] Agent registry/skill playbooks (11 Claude agents, 12 skills), bounded Footprint summary.
- [x] Metadata-only first-run doctor (Java, Gradle, Git, Blockbench, game launcher paths).
- [x] Static source generation and positive/negative Python tests.

## M1 — Trusted controller alpha (PROTOTYPE)

- [x] SQLite persistent projects, events, DAG tasks, one-owner leases, optimistic versions.
- [x] Strict new-workspace generation; no overwrite; source hash manifests.
- [x] One-use argument-bound build approval, human CLI/UI decision.
- [x] Bounded Gradle log capture and exit status.
- [x] Basic deterministic error-pattern classification and searchable local Markdown knowledge.
- [x] Capability registry and bounded Claude Code handoff packets (do not yet spawn agents).
- [x] Read/plan/generate MCP surface, no approval-granting tool.
- [ ] Real OS-enforced build/agent process isolation and network restrictions.
- [ ] Atomic staging + crash-safe recovery for partial workspace creation.
- [ ] Worker heartbeat/requeue + idempotency reconciler integration.
- [ ] Agent write scopes, independent worktrees, serialized integration.
- [ ] Model-provider adapter and actual task-dispatch runtime.

## M2 — Verified first Fabric mod (PLANNED)

- [ ] Execute real Gradle wrapper bootstrap, compile target profile and resolve API differences from actual compiler evidence.
- [ ] Select a supported Minecraft/Fabric/GeckoLib compatibility profile and cryptographically pin provenance.
- [ ] Run isolated Minecraft client + dedicated server and record a screenshot/log of each item/block.
- [ ] Proven Gradle sources and signed/hashed wrapper managed by setup wizard.
- [ ] Instrument continuous build output and progress in UI.
- [ ] Replace freeform parser with language-model-assisted interpreter + structured schemas and approvals.
- [ ] Generalized planning from approved ModSpec with scoped tasks and source patches.

**Exit:** 10/10 clean projects with basic items and blocks compile, launch, place/use; zero overwrite of user workspaces.

## M3 — Reliable agentic implementation (PLANNED)

- [ ] Model adapter for Claude Code initially, with provider-neutral task/result contract.
- [ ] Programmatic agent task dispatch, cost ceilings, cancellation, resumption, structured output validation.
- [ ] Researcher/Investigator helpers: version-matched official docs/code and baseline builds.
- [ ] Coder recipe library: Fabric registries, datagen, tools, weapons, recipes, loot, GUI, side-safe networking.
- [ ] Debugger classifies compile/registry/mixin/side/resource errors from bounded live + crash logs.
- [ ] Footprint content-addressed evidence store, FTS knowledge search, stale note detection.
- [ ] Standard source patch review / approval / rollback and worktree concurrency.

**Exit:** deterministic broken-fixture repair benchmark; no green check without evidence.

## M4 — Designer and GeckoLib (PLANNED)

- [ ] Audit licenses/security of multiple Blockbench MCPs; prefer external providers over vendoring.
- [ ] Compare direct live editor, headless `.bbmodel` editing, image-to-blockbench and source geometry.
- [ ] Full designer: editable `.bbmodel`, texture source, UV, cuboids, bones, keyframes, GeckoLib export.
- [ ] Visual screenshots and review loop; enforce explicit user art approval where needed.
- [ ] Build and test animated entity / armor / animated item code with pinned GeckoLib examples.
- [ ] Provider benchmark: swords, decorative blocks, biped/quadruped/flyer, bosses; test multiple runs.

**Exit:** simple mob prompt → editable source → GeckoLib resources → actual in-game animation, with no manual asset editing.

## M5 — Worldgen + gameplay + compatibility (PLANNED)

- [ ] World Builder for biomes, placed/configured features, trees, caves, structures, dimensions, mobs.
- [ ] Deterministic seed corpus; dedicated-server and performance tests.
- [ ] Gameplay/persistence/GUI/network/audio systems and relevant skills.
- [ ] Existing-mod baseline/diff/patch workflow and safe migration.
- [ ] NeoForge support as separate verified adapter only after Fabric reliability.

## M6 — Distribution to nondevelopers (PLANNED)

- [ ] Cross-platform installer, managed per-app JDK/Gradle acquisition, checksum validation, offline cache.
- [ ] Project templates/version chooser/preview UI/rollback and backup wizard.
- [ ] Isolated build/test runtime, Minecraft test instance manager and visual feedback dashboard.
- [ ] Source/JAR release wizard with attribution/secret scans and clean-install checks.
- [ ] Optional cloud LLM connections with spend/egress visibility and explicit consent.

## Benchmark rules

Track `tests passed / repeated clean runs`, `real build pass`, `client launch`, `dedicated server launch`, `time/LLM cost per accepted feature`, `crashes`, `security-negative results`, `manual editing required`, `art rating`, `agent correction loops`, `world-save safety`. Each metric states **which version and environment** produced it. Never infer one category from another.
