# BlockMinion — Claude Code orchestration instructions

## What this repository is

An **early working foundation**, not an autonomous arbitrary-mod generator. Python deterministic source generation supports simple Fabric 1.21.1 items/blocks. Advanced mobs/worldgen/animations require agents, researched APIs, implementation, and Minecraft runtime tests; they MUST NOT be presented as generated just because they were planned.

## Architecture decisions (binding)

1. Hybrid/local-first: user projects, Gradle, Blockbench and game testing run locally.
2. Fabric first: do not silently change MC/loader versions; the `fabric-1.21.1-candidate` profile (Mojang mappings, Loom 1.18.4) is build- and game-verified for static items/blocks only (`examples/crystal_example/EVIDENCE.md`).
3. Approval autonomy: requester must explicitly authorize consequential operations.
4. Trusted controller: `.claude/agents`, tools, prompts and Hooks are NOT a security boundary. Do not bypass `craftctl` approval state.
5. Preserve evidence: build pass != game pass != visual pass.

## Primary workflow

1. **Interpreter** scopes intent, classifies work, asks at most three consequential questions in a batch. Preserve ambiguous creative meaning.
2. **Investigator** reads existing project and tries a clean baseline; no speculative refactoring.
3. **Researcher** looks up version-matched official Fabric/GeckoLib/Blockbench references; records links, exact versions, uncertainty.
4. **Planner** chooses working vertical slices, dependencies and explicit acceptance criteria.
5. **Scrum Master** outputs independent task contracts and a dependency DAG.
6. **Coordinator** delegates only relevant workers; avoid spawning everyone for every task.
7. **Coder/Designer/World Builder** implement scoped changes. No arbitrary external scripts or downloaded MCPs without user consent.
8. **Debugger/QA** capture concrete logs, validate behavior, attach reproducible evidence.
9. **Footprint** is SQLite, not a story an agent can rewrite. Use `craftctl status`, `craftctl footprint` and events.

## Agent registry

Subagents: `.claude/agents/<role>.md` (12, one per role in `capabilities.py`), each preloading its skill from `.claude/skills/<role>/SKILL.md`. `.claude/settings.json` denies USER-ONLY `craftctl` commands and `git push`; `.claude/hooks/guard.py` is the PreToolUse backstop. The MCP server is registered in `.mcp.json`.

- `coordinator` routes tasks, enforces gates and handoff expectations.
- `interpreter` defines the spec, preserving user intent.
- `planner` makes architecture and vertical slices.
- `researcher` collects source-grounded versioned knowledge.
- `investigator` analyzes local code, dependencies and baseline.
- `coder` implements Fabric Java/data/assets.
- `designer` handles Blockbench/GeckoLib/pixel textures and screenshots.
- `world-builder` implements seed-testable world generation.
- `debugger` uses build logs, crash reports and live logs.
- `qa` validates gameplay/client-server/visual evidence.
- `release` audits JARs and source manifests.

## Tool execution policy

- `craftctl doctor` and `craftctl status` are safe read operations.
- `craftctl new`, `plan`, `approve-spec`, `generate` are explicit local workflow operations; **approval must be the user's action, not an agent impersonating the user**.
- `craftctl build` requires a one-use approval. A Gradle build is NOT sandboxed in this version; user must review the project and toolchain first.
- Do not execute arbitrary external repositories, MCP install scripts, remote setup scripts, Git hooks or Gradle plugins without approval and isolation.
- Never use normal Minecraft saves for tests. No publishing, forced overwrites or version migrations without approval.
- Keep per-task context small. Save evidence pointers and succinct decision notes, not full logs.

## Handoff format

Return a concise summary with `task`, `scope`, `changed_files`, `evidence`, `risks`, `unknowns`, `needs_approval`, `next_agent`. Never claim game-tested when no Minecraft runtime was launched.

## Scope control

`docs/V1_DEFINITION.md` is the contract. Every feature branch names the v1 criterion it advances (`[v1:#N]` in the commit message); work that advances none goes to `docs/V2_BACKLOG.md`. Bugs are always fixed; unplanned features are not built before v1.

## References

Read `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/ROADMAP.md`, `docs/SETUP.md`, `knowledge/fabric/profile-1.21.1.md`, and the versioned master plan as needed.
