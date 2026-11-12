# BlockMinion — Build & Development Path

**Document type:** Execution roadmap / implementation contract  
**Baseline:** `Minecraft_Mod_Orchestra_v0.1.0_GitHub_Ready.zip`  
**Planning date:** 2026-10-19  
**Source of design:** `Minecraft_Modding_Orchestra_Master_Plan_v2.md`, original Deep Research, and the v0.1.0 repository's `README.md`, `docs/ARCHITECTURE.md`, and `docs/ROADMAP.md`  
**Status:** Proposed engineering plan; milestones beyond v0.1.0 are not claimed implemented

> **Mission:** Turn a person's Minecraft Java mod idea into an approved specification, a dependency-aware work plan, implemented Java/resources/assets, verified gameplay, and releasable mod JAR + source. Preserve the user's original intent and existing work. Research unknown functionality instead of inventing APIs. Reuse mature external tools rather than rebuilding them.

## 1. Product decisions — fixed until a documented ADR changes them

| Decision | Policy |
|---|---|
| Deployment | **Hybrid local-first.** Source workspaces, Java/Fabric builds, Blockbench, test instances, logs, and user files remain on the user's machine by default. Optional remote AI/research requires visible data-sharing controls. |
| Initial mod loader | **Fabric only.** Establish at least one fully build- and game-verified version profile before adding others. |
| Autonomy | **Approval-based.** Workers may perform preauthorized bounded tasks, but material changes, untrusted installers/plugins, exceptional costs, world modification, external publishing, and high-risk execution need human approval. |
| First orchestration integration | **Claude Code adapter**, with model/provider-independent task and result interfaces. |
| Source of truth | Controller-managed SQLite + Git/evidence artifacts; Markdown is a bounded, readable projection. |
| External tooling | Reuse official Fabric scaffold/tooling, GeckoLib, Blockbench, compatible MCP providers, Gradle wrapper, and existing testing infrastructure. |
| Evidence standard | A generated file is not a working mod. A successful build is not a gameplay test. An agent's assertion is not test evidence. |
| Scope | Start with reliable single-user local application. Multiuser/cloud hosted workers, NeoForge, and broad version support are follow-on work. |

### Architectural rule

```text
User / Desktop UI / CLI
         |
         v
  Trusted local controller
  - permissions + approvals
  - project/task state
  - workspaces + snapshots
  - version/profile resolver
  - execution / evidence broker
         |
         v
  Coordinator (reasoning worker)
  - interpreter / planner / scrum-master
  - researcher / investigator / coder
  - designer / world-builder / debugger / QA
         |
         v
  Allowlisted provider adapters
  - Claude Code / optional other LLMs
  - Fabric/Gradle & Minecraft tests
  - Blockbench MCP + GeckoLib
  - source/docs/knowledge retrieval
         |
         v
  Independent verification + Footprint + Git
         |
         v
  Human-reviewed export (source + JAR)
```

**Trust boundary:** Only the controller decides whether a task may touch files, execute a process, contact a service, or change lifecycle state. Agent prompts, `CLAUDE.md`, and hooks are useful coordination tools but are **not OS-level security controls**.

## 2. Exact starting point: what v0.1.0 actually contains

The following is based on the shipped pilot's README and repository contents; it is not a claim of in-game validation.

| Capability | Baseline status | Notes |
|---|---|---|
| `craftctl` CLI + localhost browser UI | Implemented prototype | Locally tested application workflow |
| Project/spec/task/event state in SQLite | Implemented prototype | Tasks, one-owner leases, approvals, bounded Footprint |
| Deterministic `items:`/`blocks:` parser | Implemented | **Not** a general natural-language Interpreter |
| Simple Fabric Java/resource generator | Implemented, statically tested | Generates placeholders and resources, not arbitrary mod mechanics |
| Static output validation & file-hash manifest | Implemented | Not a compiler/runtime verifier |
| Build approval + bounded Gradle runner | Prototype | No OS-enforced sandbox; target stack not yet Minecraft-build proven |
| `doctor`, `diagnose`, limited log handling | Prototype | No continuous Minecraft live-log collector or autonomous debugger |
| MCP facade and capability registry | Prototype | No live AI dispatch |
| 11 Claude Code agent definitions / 12 skill playbooks | Present as files | No automatic workers from UI |
| Fabric 1.21.1 candidate profile | Candidate only | Maven coordinates listed, combined build not verified |
| GeckoLib and Blockbench | Researched | Not integrated into actual generation workflow |
| Worldgen, GUI, advanced mechanics | Planned | Not implemented |
| First-run tool auto-installation | Planned | Diagnostics only |
| Gameplay/GameTests/multiplayer verification | Planned | Not performed |

**Critical correction from the earlier discussion:** The presence of `.claude/agents/*.md` is **not** an operational agent orchestra. Connecting and supervising those workers must be among our earliest implementation goals, not postponed until the desktop app is polished.

### Baseline repository locations

| Area | Existing location |
|---|---|
| Core Python package | `src/mod_orchestra/` |
| CLI | `src/mod_orchestra/cli.py` |
| Persistent state | `src/mod_orchestra/state.py` |
| Basic workflow | `src/mod_orchestra/workflow.py` |
| MCP | `src/mod_orchestra/mcp.py` |
| Fabric output | `src/mod_orchestra/fabric.py` |
| Capability registry | `src/mod_orchestra/capabilities.py` |
| Diagnostics / build | `src/mod_orchestra/diagnostics.py`, `build.py`, `doctor.py` |
| Web UI | `src/mod_orchestra/ui.py`, `static/` |
| Agent definitions | `.claude/agents/` |
| Skills | `skills/*/SKILL.md` |
| Knowledge | `knowledge/` |
| Candidate profile | `profiles/fabric-1.21.1-candidate.json` |
| Existing tests | `tests/` |

## 3. Development strategy

### Three tracks, one integrated release gate

**Track A — Trust and reliability.** Dependency profiles, sandbox/process broker, approvals, durable scheduler, Git/snapshots, versioned evidence, live logs, crash recovery.

**Track B — The actual agent orchestra.** Claude Code worker adapter, Coordinator dispatch, Interpreter/Planner/Scrum-Master structured results, Coder, Researcher/Investigator, Debugger, Designer and World Builder.

**Track C — Minecraft capability.** Verified Fabric compilation and client/server launch, datagen, items/blocks, GUI/networking, GeckoLib, worldgen, automated gameplay and release validation.

Track A starts first and defines permissions. Tracks B and C may advance in parallel in their own isolated test workspaces; **a milestone cannot be declared production-ready until its Track A gates pass**.

### Rules for every pull request

1. Small, reviewable change with one owner and explicit acceptance criteria.
2. Reproduce/fail-first test where practical; record the before-state.
3. Only edit owned workspace paths; preserve user files and existing worlds.
4. Any change to an external dependency carries version, source, license and provenance.
5. CLI, API, MCP and UI must call the **same controller operations**; no parallel implementation of approval/state rules.
6. A worker returns structured results: changed files, patch/commit, tests, logs, confidence, risks and unresolved questions.
7. Independent verification determines DONE; failing or unavailable game validation must remain labeled as such.
8. Every significant change updates tests, documentation, milestone state and a bounded Footprint summary.

## 4. Milestones, in execution order

### R0 — Freeze the v0.1.0 baseline (already shipped; verify once locally)

**Goal:** Keep a reproducible reference before adding autonomous agents.

- Tag `v0.1.0-prealpha` after confirming local checkout and tests.
- Capture Python version, OS, current test suite outcome and zipped hash.
- Run unit tests and local CLI create/approve/generate scenario.
- Record known limitations in a `KNOWN_LIMITATIONS.md` or GitHub issues.
- Treat the existing `docs/ROADMAP.md` as history; use this document for the forward plan.

**Exit evidence:** clean checkout installs, CLI smoke completes, Python tests pass, baseline Git tag exists. If a check fails, file an issue rather than changing historical claims.

---

### R1 — Trusted foundation and first real Fabric build

**Priority:** P0 / release blocker. **Depends on:** R0.

**Deliverables**

- Verify a complete, *compatible* Minecraft + JDK + Gradle + Loom + mappings + Loader + Fabric API profile. GeckoLib is pinned separately for the animation milestone.
- Bootstrap a reviewed Gradle wrapper with verified distribution URL/checksum; record hashes and licenses.
- Build the generated sample from an untouched source checkout on Windows; remove API/compiler discrepancies based on actual compiler output.
- Launch an isolated client and dedicated server where supported; collect logs and JAR metadata.
- Add real `BUILD_PASS`, `CLIENT_BOOT_PASS`, `SERVER_BOOT_PASS` evidence levels distinct from static validation.
- Introduce migrations and migration tests for the SQLite schema before expanding orchestration.
- Implement atomic generation into a staging directory, preflight target-path checks, snapshots and failure cleanup.
- Add policy-enforced process invocation for **allowlisted commands**, working directories, environment, timeouts, output caps, network visibility and cancellation.
- Prototype OS-level isolation for untrusted builds/agents. **Do not advertise isolation** until isolation tests prove it on the supported OS. Until then, keep execution opt-in and clearly unsafe for untrusted projects.

**Initial tickets**

| ID | Task | Test / definition of done |
|---|---|---|
| `ENV-001` | Probe Java, Git, Gradle/Wrapper, Minecraft, Blockbench | Structured diagnostic report and actionable missing-tool states |
| `FAB-001` | Validate one Fabric target profile | Exact dependency/profile lock + working real compilation |
| `FAB-002` | Create and run known-good sample project | Client and dedicated server launch evidence |
| `SEC-001` | Workspace path broker + atomic staging | Traversal/symlink/partial-write test fixtures |
| `SEC-002` | Scoped process broker and approval check | No unapproved process launch; replay protection; bounded output |
| `SEC-003` | Isolated execution proof-of-concept | Canary tests establish what the sandbox actually blocks |
| `STA-001` | Schema migrations and recovery checks | Upgrade/restart test preserves projects and events |
| `QA-001` | Fabric build smoke job | Build failure blocks green status |

**Exit gate:** The pilot generates a Minecraft mod that compiles and runs in the target client and server **on at least one tested machine**, with evidence retained. Unsafe builds are never silently triggered by a worker.

---

### R2 — Working Coordinator and first live AI agents

**Priority:** P0 / core identity of product. **Depends on:** R1's controller policy/approval foundations; Fabric build verification can continue in parallel.

This is the first release that deserves the name **agent orchestrator**.

**Deliverables**

- Define `AgentProvider` interface: `start(task_envelope)`, `poll`, `cancel`, `stream_events`, `result`, `capabilities`.
- Implement a **real Claude Code adapter** that invokes one bounded worker and observes its lifecycle; do not assume a Claude Code CLI/API flag without verifying the installed release.
- Dispatch by capability and dependency state; no free-form agent ability to launch arbitrary worker trees.
- Coordinator chooses a role from `capabilities.py`, checks required evidence/permissions, constructs bounded handoff and dispatches.
- Implement maximum simultaneous workers, resource reservations, time/cost budgets, backoff, leases, heartbeat, cancellation and duplicate-delivery handling.
- Require schema-validated worker output; reject malformed, context-free or unsupported completion claims.
- Integrate command/tool/event reporting into the Footprint, redact secrets, preserve compact summary.
- Add a **user-facing live activity feed**: who is working, on what, changes proposed, logs, questions and requested approvals.
- Introduce clear statuses: `QUEUED`, `RUNNING`, `WAITING_APPROVAL`, `WAITING_USER`, `VERIFYING`, `BLOCKED`, `FAILED`, `DONE`, `CANCELLED`.
- Concurrency: exclusive task leases and isolated Git worktrees or staged patches; one integration/merge owner.

**First true orchestration test**

```text
User: "Add a blue crystal item to a Fabric mod."
  -> Interpreter creates typed requirements
  -> Planner produces minimal implementation plan
  -> Scrum Master creates dependent tasks
  -> Coordinator dispatches Coder
  -> Coder proposes or applies bounded changes
  -> Controller runs allowed verification
  -> QA marks verified only with build/game evidence
  -> Footprint records artifact and remaining uncertainty
```

**Acceptance:** At least two distinct reasoning roles are actually invoked by the controller from the UI/CLI, with inspectable independent outputs and a real completed task. Restarting the controller must not duplicate writes or lose an active task. User can pause/cancel.

**Not sufficient:** Only adding more `.md` agent prompts, only producing handoff text, or letting an unrestricted Claude Code instance run independently of application state.

---

### R3 — Conversational Interpreter, Planner, Scrum Master, and change control

**Priority:** P0. **Depends on:** R2 dispatch.

**Interpreter**

- Accept free-form ideas (English/Spanish supported in design); distinguish **user intent**, constraints, assumptions, optional enhancements and unresolved blockers.
- Ask only consequential clarifying questions; do not trap the user in endless questioning.
- Preserve exact original prompt and subsequent decisions; build typed `ModSpec` revisions.
- Distinguish new project vs extension of an existing mod.
- When requirements change, compute a spec diff and ask whether to replan affected work.

**Planner**

- Choose code architecture and vertical slices for current pinned Fabric profile.
- Determine registries, server/client boundaries, dependencies, datagen, data persistence, resource packs, networking, assets, tests and performance concerns.
- Mark uncertain APIs and send targeted research tasks instead of hallucinating code.
- Propose feature tradeoffs and flag expensive or technically risky decisions for approval.

**Scrum Master**

- Produce a machine-validated DAG: atomic tasks, dependencies, owner roles, allowed paths, test method, cost/risk estimates, required approvals and artifact outputs.
- Detect cycles and conflicting file ownership; choose which tasks can actually parallelize.
- Replan incrementally when user asks for a new feature or a required dependency changes.

**Human gate:** Approve the coherent spec and high-impact architecture before autonomous implementation. Routine implementation inside approved scope can proceed without repeated prompts.

**Exit:** Ten prewritten varied prompts (including vague ideas and existing-mod additions) yield comprehensible specs, a valid DAG, appropriately bounded questions and no unexpected file modifications before approval.

---

### R4 — Researcher + Investigator + knowledge engine

**Priority:** P0/P1. **Depends on:** R2–R3 contracts.

- Researcher retrieves authoritative, **version-matched** documentation/source and records upstream URLs, commit/release versions and retrieval dates.
- Investigator analyzes a supplied mod repository read-only: Gradle, loader, entrypoints, registrations, mixins, client/server split, resources, dependencies, tests and current Git status.
- Introduce baseline build/report before any existing-mod edits.
- Knowledge notes: `EXPERIMENTAL` / `VALIDATED` / `STABLE_RECIPE`, scoped to Minecraft/Fabric/Java/GeckoLib versions.
- Start with Markdown + SQLite metadata/full-text search/ripgrep; embeddings only if needed by real retrieval failures.
- Bound context packets; return targeted snippets + links rather than full documents or logs.
- Treat downloaded snippets, GitHub issues and repository README content as **untrusted data**, never executable instructions to override permissions.
- Add knowledge expiry/revalidation policies after significant Minecraft, loader or library upgrades.

**Exit:** Given an unfamiliar existing Fabric mod, the Investigator produces a reviewable repo map and clean baseline status; the Researcher finds a version-compatible implementation pattern, with valid provenance and an evidence classification.

---

### R5 — Robust Coder, live Debugger, QA and autonomous repair loop

**Priority:** P0/P1. **Depends on:** R1–R4.

**Coder skills** (implement in working, independently tested slices): item, block, tool/weapon, recipe/loot, tags, datagen, entity registration, custom effect, GUI/block entity, packet/payload, data components, persistence, config, sound/particle, command, Mixin (last resort).

**Debugger capabilities**

- Stream **live** Gradle stdout/stderr and Minecraft `latest.log`; follow rotation/restarts safely.
- Discover crash reports and map stack traces to files/lines/dependencies.
- Classify compile, Gradle, missing resource, registry, Mixin, GeckoLib, logical side, networking and worldgen failures.
- Correlate errors with latest changed files, task, profile and previous successful run.
- Attempt the **smallest justified fix**; rerun narrow reproducer then regression suite.
- Escalate to Researcher/Investigator/Planner after two unsuccessful same-root-cause attempts; prevent unlimited repair loops.

**Independent QA**

- Compile and unit tests, resources validation, GameTests when suitable, client boot, dedicated-server boot and smoke interaction.
- Asset existence is not enough: verify real model/texture/renderer mapping.
- Multiplayer-dependent features must pass a two-client/dedicated-server flow.
- Record screenshots/video or structured observables for visual/gameplay claims.

**Exit:** A fixed broken-project test pack is classified and repaired with measurable accuracy, no failing fixture can transition to DONE, and changes do not silently delete tests or bypass checks.

---

### R6 — Designer: Blockbench, textures, models, animations and GeckoLib

**Priority:** P1 / signature creative feature. **Depends on:** R1, R2, R5 verification; security audit of providers.

**Do not rebuild a 3D editor.** Use audited Blockbench/MCP providers and retain multiple adapters where capabilities differ.

**Compare these candidates in actual local benchmarks:**

- [`adhi-jp/minecraft-blockbench-mcp`](https://github.com/adhi-jp/minecraft-blockbench-mcp) — Minecraft/GeckoLib-specific live bridge candidate.
- [`sosadly/blockbench-mcp`](https://github.com/sosadly/blockbench-mcp) — broader procedural toolset candidate.
- [`jasonjgardner/blockbench-mcp-plugin`](https://github.com/jasonjgardner/blockbench-mcp-plugin) — headless `.bbmodel` editing candidate; assess its GPL license before integration/distribution.
- [`img2blockbench`](https://github.com/search?q=img2blockbench&type=repositories) — reference-image path candidate; verify exact maintained upstream and current licensing before adoption.

**Asset routes**

| Artifact | Default workflow |
|---|---|
| Simple item icons | Source texture image/16×16 pixel pipeline + standard Minecraft item model |
| Standard static blocks | Block model JSON / Blockbench Java block-item format as needed |
| Complex entity | Editable `.bbmodel` → UV/texture → pivoted bones → animations → GeckoLib `.geo.json` / `.animation.json` |
| Advanced item/block entity animation | GeckoLib only when actual animation needs justify it |
| Reference art | Optional image-to-model reconstruction followed by human/vision validation |

**Provider evaluation:** fixed prompts covering simple/complex swords, decorative/machine blocks, quadruped, flyer, humanoid boss and animated item; run repeated attempts. Track correctness, texture coverage, bone pivots, animation names, exported resource paths, tool calls, errors and actual in-game appearance. **No unverified “best MCP” claim.**

**Output contract:** editable `.bbmodel`, lossless source textures, previews, export files, source/license provenance, screenshots, structural checks and Java resource-path references.

**Exit:** One original animated mob is generated from a prompt, source remains editable, GeckoLib code compiles, a real client renders correct animation, and a user can request visual revisions without manually editing Blockbench.

---

### R7 — World Builder + deeper Minecraft gameplay

**Priority:** P1. **Depends on:** R5–R6 as applicable.

- Biome additions, configured/placed features, ore/vegetation/tree generation, structure placement and spawn rules.
- Advanced caves, terrain, dimensions and world presets as version-scoped, separately tested recipes.
- Separate **what generates**, **how/frequency**, and **where**, using the proper version-specific worldgen bootstrap/data/codec APIs.
- Persist a diverse seed corpus, observed placement counts, biome/structure positions and dedicated-server exceptions.
- Add mechanics modules: combat/AI, inventory interactions, GUI, networking, persistent data, cross-mod compatibility and performance.
- Include world-save backup/restore and worldgen migration warnings **before** modifying a real user's world.
- Measure world startup, chunkgen timing, memory and server tick impact; set feature-specific performance budgets.

**Exit:** A custom biome or structure with generated features and its associated mob works across multiple reproducible seeds on a dedicated server, with no critical regressions.

---

### R8 — Safely extend an existing mod

**Priority:** P1. **Depends on:** R4–R7 basics.

- Import existing Fabric repository **without** moving/deleting untracked user files.
- Investigator records baseline build, versions, branch, licenses, dependencies, mixins and resource map.
- Request change as a new spec revision, not a fresh project replacement.
- Create a separate worktree/patch; limit touched paths and preserve original project by default.
- Detect dependency conflicts, incompatible versions, mapping differences and duplicate registries.
- Run preexisting tests plus new regression fixtures; compare against recorded baseline errors.
- Present patch summary before integration; capture rollback/recovery points.

**Exit:** Extend a representative real mod with an item and a behavior change, with **zero unrelated file edits**, passing existing checks or clearly labeling original baseline failures.

---

### R9 — First-run Setup Wizard and desktop alpha

**Priority:** P1 for public usability; start UX prototype earlier. **Depends on:** tested version profile and policy broker.

**Wizard sequence**

1. Detect OS, architecture, free disk, Python/runtime (until packaged), JDK, Git, wrapper/Gradle, Blockbench, launcher/game installation and compatible assets.
2. Offer a **verified** Minecraft/Fabric profile instead of silently choosing the newest Minecraft release.
3. Explain optional requirements per project (no Blockbench for simple items; no GeckoLib unless animation requires it).
4. Present exact tool downloads, vendors, version, checksums/signatures, licenses and required storage/network to user **before** installation.
5. Install into user/app-managed tool directories where possible; never silently modify system-wide `PATH` or install browser/MCP plugins.
6. Configure optional cloud/local AI provider and its data-sharing policy; test credentials without recording tokens in project logs.
7. Perform real smoke tests: build a sample mod; optionally launch a separate test instance; show pass/fail and recovery actions.
8. Cache verified toolchains; support uninstall, repair, version switch, and offline detection.

**UI areas:** Projects, Idea/Chat, Specification & Questions, Plan/Tasks, Agent Activity, Assets/Previews, Logs/Debugger, Test Evidence, Approvals, Dependencies, Export.

**Important game ownership distinction:** Building Java source does not necessarily require a preinstalled Minecraft launcher. Launching/playing tests needs legitimate game/runtime assets and appropriate account/licensing handling; **the app must not distribute proprietary Minecraft files**.

**Exit:** A clean Windows machine can start with no Minecraft modding development environment, pass guided setup and build a basic Fabric mod without manual terminal commands. Installation denials and interrupted downloads recover cleanly.

---

### R10 — Product beta: reliability, distribution and release

**Priority:** P1 after real development loops stabilize.

- Produce source and tested mod JAR with runtime dependency declarations, licenses and reproducible manifest/hashes.
- Clean-instance install smoke check, dedicated-server checks where appropriate, new-world vs existing-world safety warning.
- Add crash recovery, workspace snapshots, migration strategy, backups and restore wizard.
- Provider cost visibility, quotas, consent for cloud upload, secrets redaction and prompt-injection guards.
- GitHub release pipeline, updater strategy, user telemetry opt-in **off by default**.
- Test on clean machines and against failure cases: disk-full, offline, missing Java, mismatched dependencies, malicious MCP, interrupted execution and unsaved Blockbench project.
- Publish transparent capability coverage and success rates; no “supports any mod” claims beyond measured tests.

**Exit:** Repeatable novice user flow from idea → spec approval → code/assets → verified working mod → JAR/source export, with auditable permissions and recoverable errors.

---

### R11 — Expansion only after stable Fabric beta

**Priority:** P2 / future.

- NeoForge adapter with **separate** official template/toolchain and QA matrix.
- Additional Minecraft versions with version-specific code recipes, mapping migration tools and upgrade reports.
- Optional common-source multi-loader project mode, using existing template patterns rather than inventing shared Gradle infrastructure.
- More image/model/LLM providers; local model runtime; remote worker option with strict opt-in data boundaries.
- Modpack compatibility scans, profiling, team collaboration, distributed queues, richer evaluation dashboards and advanced dimensions.

**Exit:** Every new backend passes the full benchmark suite **independently**, not by inheriting Fabric-only green statuses.

## 5. Priorities: the next issues to open in GitHub

These are ordered by **unblocking capability**, not by which feature looks most impressive in a demo.

| Order | Issue | Dependencies | Output |
|---:|---|---|---|
| 1 | Capture/verify v0.1.0 test baseline and tag | none | Known starting point |
| 2 | Validate one real Fabric profile (JDK/Gradle/Loom/Loader/API) | 1 | Build-proven lock profile |
| 3 | Build approved sample and boot isolated client/server | 2 | First real mod evidence |
| 4 | Implement core task/result/approval JSON schemas | 1 | Validation contracts |
| 5 | Harden process broker, staging and path controls | 4 | Minimal enforceable trust boundary |
| 6 | Create `AgentProvider` and Claude Code worker adapter | 4–5 | First real invoked worker |
| 7 | Coordinator dispatch + durable runs/heartbeat/cancel | 6 | Agent lifecycle in controller |
| 8 | Show agent progress, task evidence and approval prompts in UI | 7 | Visible orchestration |
| 9 | Interpreter free-form intake and versioned spec | 7 | Natural-language requirement flow |
| 10 | Planner → Scrum Master validated task DAG | 9 | Executable feature plan |
| 11 | Coder patch integration with scoped files and independent verification | 3, 7, 10 | End-to-end AI-implemented item |
| 12 | Live Gradle/Minecraft logs + Debugger triage | 11 | Repair loop |
| 13 | Researcher/Investigator version-aware retrieval | 7, 10 | Unknown API and existing-code expertise |
| 14 | Build/launch validation fixtures and automated quality dashboard | 11–13 | Trustworthy DONE evidence |
| 15 | Audit/benchmark Blockbench MCP providers | 5, 14 | Grounded Designer choice |
| 16 | Integrate GeckoLib animated mob vertical slice | 15 | Signature 3D pipeline |
| 17 | Worldgen slice with seed corpus and server validation | 14 | World Builder proof |
| 18 | Existing-mod safe extension path | 13–14 | Modify existing projects |
| 19 | Guided first-run installs and desktop packaging | 2–5 | Nondeveloper setup |
| 20 | Release beta with security and repeatability suite | all essential | User-ready beta |

**Parallel work:** Issues 2–3 (Fabric verification) can proceed alongside issues 4–8 (safe worker orchestration) in separate test workspaces. Provider security auditing can begin early, but installation/integration must wait for approval and isolation controls.

## 6. Agents and when they become *operational*

| Agent or service | Earliest meaningful release | Why it becomes real then |
|---|---|---|
| Coordinator | R2 | Actually launches, monitors and cancels workers |
| Interpreter | R3 | Structured, conversational requirements and follow-up decisions |
| Planner | R3 | Uses actual versioned project context to propose architecture |
| Scrum Master | R3 | Generates enforceable DAG/task dependencies via controller |
| Researcher | R4 | Retrieval with versions, provenance and a bounded answer contract |
| Investigator | R4 | Real repository inspection and baseline analysis |
| Coder | R2 first slice; deeper in R5 | Scoped edits backed by build/tests |
| Debugger | R5 | Live logs, root-cause loop, repair evidence |
| QA | R1 basic; R5 broad | Independently verifies real Minecraft behavior |
| Designer | R6 | Actual Blockbench/GeckoLib integration |
| World Builder | R7 | Tested biome/structure/feature worldgen |
| Release | R10 | Reproducible JAR/source audit and export |
| Footprint | Already basic; R2–R5 strengthened | Service, **not** a hallucination-prone history agent |
| Environment Manager | R1 basic; R9 install automation | Deterministic service, not another LLM worker |
| Security/Policy | R1 baseline onward | Controller/OS enforcement, not prompt-only reviewer |

**No need to keep all workers active.** Most tasks use Coordinator plus 1–3 specialists. Parallel workers are admitted only when file ownership, game-instance resources, and dependencies allow safe overlap.

## 7. Interfaces that must stabilize before scaling agent count

### `ModSpec` (validated and revisioned)

```yaml
schema_version: 1
project_id: crystal_frontier
revision: 2
intent: create_mod
platform:
  loader: fabric
  minecraft: pinned_verified_profile_id
features:
  - id: crystal_item
    type: item
    description: A blue crystal collectible
nonfunctional:
  dedicated_server: true
  multiplayer: basic
assumptions: []
blocking_questions: []
approved_revision: 2
```

### `TaskEnvelope` (no implied permission)

```yaml
schema_version: 1
task_id: ITEM-004
role: coder
spec_revision: 2
objective: Register the crystal item and resources
workspace_id: worktree-item-004
allowed_paths:
  - src/main/java/com/example/crystalfrontier/item/**
  - src/main/resources/assets/crystal_frontier/**
allowed_operations:
  - read_project
  - propose_patch
acceptance:
  - Item registered without client-side class on dedicated server
  - Resource IDs resolve
  - Real Gradle build passes
evidence_required:
  - build_log
  - generated_file_manifest
risk_tier: low
```

### `AgentResult` (verified later by controller/QA)

```yaml
schema_version: 1
task_id: ITEM-004
status: submitted_for_verification
changed_files:
  - src/main/java/com/example/crystalfrontier/item/CrystalItem.java
proposed_git_commit: null
evidence_refs:
  - build-run-028
risks: []
unverified:
  - Not yet confirmed visible in the Minecraft creative inventory
```

Do not confuse `AgentResult.status` with the controller's task state. A worker can **submit** a result; only independent verification can mark it DONE.

### Approval contract

Every approval must be bound to **exact action, target project, paths, hash of relevant inputs, dependency/profile versions, expiration and single-use nonce**. UI approval **cannot** be granted through a model-callable MCP tool. Changing the action invalidates the approval.

### Core APIs / CLI behavior

- `projects.create / inspect / import`
- `spec.question / revise / approve`
- `plan.create / diff / approve`
- `tasks.ready / claim / heartbeat / submit / verify / cancel`
- `agent.launch / events / stop / status`
- `build.request / authorize / run / result`
- `game.launch_test / stop_test / evidence`
- `logs.follow / classify / crash_latest`
- `assets.generate / validate / preview`
- `kb.search / read / propose_note / promote_after_evidence`
- `release.audit / package`

Actual CLI/API names may differ from this **target contract**; avoid declaring endpoints operational until corresponding implementations and tests exist.

## 8. Acceptance and benchmark program

### Validation ladder

1. **Generated** — files exist, manifest hashes match.
2. **Static validated** — models/JSON/resources/references parse and resolve.
3. **Build verified** — Gradle compiler/build steps succeed on locked profile.
4. **Client boot verified** — mod loads and no relevant startup errors.
5. **Server boot verified** — dedicated server starts without wrong-side class failures.
6. **Feature test verified** — behavior passes GameTest/manual captured observation.
7. **Visual verified** — visuals/animations/screenshots match acceptance criteria.
8. **Release verified** — fresh install and JAR/source audit pass.

Never collapse these into a single `success: true`.

### Minimum fixed regression fixtures

- Basic item; basic block; crafting+loot; tool durability and use.
- Missing texture; invalid model/JSON; duplicate registry ID; compile error.
- Incorrect dependency; Mixin application failure; logical-side classloading issue.
- Basic entity; GeckoLib missing bone/animation; entity motion with animation.
- Client/server packet synchronization; GUI/block entity persistence.
- Biome/feature/structure generation on fixed seeds.
- Existing mod extension with an intentionally dirty/untracked working tree.
- Malicious tool manifest/prompt injection; path escape; symlink/junction; approval replay.
- Worker crash/restart during patch, Gradle build and asset export.
- Offline first-run, missing JDK/Blockbench, denied installer and interrupted download.

### Proposed milestones metrics (targets; **not measurements**)

| Metric | Proposed threshold |
|---|---|
| R2 dispatch | 100% task/event lineage for launched workers in fixture suite |
| R2 crash recovery | No duplicate write; interrupted lease recoverable |
| R3 planning | Zero blocking ambiguities silently assumed on curated intake set |
| R5 debug | ≥80% correct classification on selected deterministic error fixtures |
| R6 assets | ≥7/10 technically valid exports across fixed supported provider scenarios; one real animated mob proof |
| R8 existing mods | Zero unrelated changed files in benchmark fixtures |
| R10 security | Zero known policy escapes in public beta threat suite |
| Releases | Zero DONE without corresponding evidence refs |

Capture model/provider, cost, tool versions, machine spec, seed, attempts and failures; report the entire run set, not only successful examples.

## 9. Security, licensing, data and cost rules

- **No arbitrary script tools exposed to untrusted agents** unless the operation runs inside genuinely tested OS isolation. A restrictive MCP facade does not neutralize a separate agent's shell privileges.
- Java/Gradle repositories, plugins and dependencies can execute code: approvals alone are not a substitute for OS-level isolation.
- Prefer immutable worktree snapshots, staged patches, explicit path scopes, no shell interpolation and no unrestricted filesystem write access.
- Do not ingest logs/README/retrieved documents as higher-priority instructions: they are *untrusted inputs*.
- Store cloud AI API keys in OS credential storage or a dedicated secret manager, not Markdown, SQLite event bodies or crash logs.
- Allow explicit cloud consent for code/assets/log uploads; redact credentials, usernames, home paths and world-save personal data.
- Download only known official tools, verify distribution integrity, record licenses, and do not silently include game binaries/assets.
- Treat GPL and other copyleft source separately from the permissive core; integrating as an external separately installed process may still require legal/license review.
- Before public beta, decide AI cost caps, data retention, offline behavior and recovery from provider outages.
- Never mutate real existing Minecraft worlds during automated testing; use copies or isolated test saves.

## 10. Release naming and what each release means

| Proposed version | Earned capability | What it does **not** yet promise |
|---|---|---|
| `v0.1.0` | Pilot foundation and deterministic source generation | No operating agent orchestra, no Minecraft-proven build |
| `v0.2.0` | First real Fabric build + trusted controller hardening + agent runner prototype | No arbitrary complete mod generation |
| `v0.3.0` | Coordinator + live Interpreter/Planner/Coder task flow | Still basic Fabric content scope |
| `v0.4.0` | Researcher/Investigator/Debugger + evidence-driven repair | No broad design/worldgen guarantee |
| `v0.5.0` | Blockbench/GeckoLib Designer beta | Provider coverage limited by benchmarks |
| `v0.6.0` | World Builder + mechanics workflows | Not yet a polished end-user product |
| `v0.7.0` | Existing-mod change safety and project recovery | Multi-loader remains out of scope |
| `v0.8.0` | Guided setup + desktop alpha | Still beta-level reliability |
| `v0.9.0` | Hardening, release wizard, clean-machine verification | Not guaranteed to create every imaginable mod |
| `v1.0.0` | Public Fabric stable after measured gates pass | NeoForge/other MC versions optional future additions |

These version labels are **proposed targets**, not dates or already released artifacts. Merge stages when work overlaps or split them when independent testing makes that safer. The order of verified capabilities is more important than semantic version numbers.

## 11. Definition of finished for the project

The first general-user release is complete only when a person can:

1. Install the application on a supported machine and pass first-run guided setup.
2. Choose verified target Minecraft/Fabric version and see the dependency implications.
3. Explain an idea in everyday language and answer only relevant clarifying questions.
4. Review/approve an understandable spec and project plan.
5. Observe real agents perform delegated tasks and see their status, evidence and failures.
6. Review/modify visual assets and see Blockbench/GeckoLib previews when relevant.
7. Watch automatic build, debugging and controlled retry progress.
8. Have the features independently validated inside Minecraft (and dedicated server where relevant).
9. Pause/resume safely; recover from crash or restart without losing unsaved user work.
10. Export a verified JAR and full editable source, with limitations honestly stated.

It must also successfully **reject** unsupported, unsafe or out-of-scope operations and explain next steps. A working application should not pretend a failed task is done.

## 12. Immediate kickoff order (short version)

**First engineering sprint:** audit baseline → verify pinned Fabric build/runtime → strengthen controller paths/approvals/process safety → implement Claude Code worker lifecycle → show real worker activity in UI.

**Second sprint:** live Interpreter and Planner produce a revisioned `ModSpec` → Scrum Master generates DAG → Coder creates a small Fabric feature → verified build and client test → Footprint captures the full evidence chain.

**Third sprint:** live logs and Debugger diagnosis → Researcher/Investigator evidence-based API lookup → fix/retest loops and safe Git patch integration.

**After these succeed:** add Blockbench+GeckoLib, worldgen, existing mods, first-run installers and public desktop hardening in that dependency order.

**Recommended next concrete proof:** From the existing v0.1.0 repository, run a real Claude Code Coder worker under controller supervision to add one custom item to a known-good Fabric project. Show the user an agent task card, capture the patch, run the actual Fabric build, confirm the item in an isolated client instance, and close the task only with evidence. This would prove the orchestra's *core loop* before its creative scope expands.

---

## Appendix A — Selected source references (from the research corpus)

- Fabric docs: <https://docs.fabricmc.net/>
- Fabric developer setup and versions: <https://fabricmc.net/develop/>
- Fabric example mod: <https://github.com/FabricMC/fabric-example-mod>
- Fabric Maven: <https://maven.fabricmc.net/>
- GeckoLib: <https://github.com/bernie-g/geckolib>
- GeckoLib examples: <https://github.com/bernie-g/geckolib-examples>
- Blockbench: <https://www.blockbench.net/wiki/>
- MCP specification: <https://modelcontextprotocol.io/>
- Claude Code docs: <https://code.claude.com/docs/en/overview>
- Universal Modder: <https://github.com/rehan-remade/universal-modder>
- Candidate Blockbench MCP: <https://github.com/adhi-jp/minecraft-blockbench-mcp>
- Candidate Blockbench MCP: <https://github.com/sosadly/blockbench-mcp>
- Candidate Blockbench MCP: <https://github.com/jasonjgardner/blockbench-mcp-plugin>

*Links identify primary reference sources, not proof that all current APIs, releases, licenses, or integration claims were freshly reverified when this development-path file was generated. Pin commits/versions and validate locally before adoption.*

## Appendix B — Relationship to other documents

- `docs/MASTER_PLAN_v2.md` — full architecture and research-derived design; this file focuses on **build order**.
- `docs/ROADMAP.md` in v0.1.0 — original snapshot; retain it as historical baseline.
- `Minecraft_Java_Modding_Orchestra_Complete_Research_Knowledge.md` — consolidated research archive, **not** something to load wholesale into an agent context window.
- `CLAUDE.md`, `.claude/agents/`, `skills/`, `knowledge/` — role prompts, execution procedures, and retrievable domain references, none of which substitute for tested policy enforcement.

**Change discipline:** The Coordinator/Scrum Master may propose roadmap updates, but material architectural or product-scope changes require user approval and a new Architecture Decision Record.
