# BlockMinion

*Formerly "Minecraft Mod Orchestra". Same tool, same `craftctl`; see [CHANGELOG.md](CHANGELOG.md).*

> New here? Start with **[docs/SETUP.md](docs/SETUP.md)** — a clean machine to a verified mod, step by step.

**A local-first orchestration foundation for turning Minecraft Java ideas into managed Fabric mod projects.**

[![CI](https://img.shields.io/badge/CI-Python%20unit%20tests-informational)](#testing) ![Version](https://img.shields.io/badge/version-0.1.0--prealpha-yellow) ![Loader](https://img.shields.io/badge/loader-Fabric-blue) ![License](https://img.shields.io/badge/license-source--available%20%7C%20no%20resale-blue)

> **Status: Pre-alpha, working foundation—not a finished AI mod factory.** The current executable app can collect requirements, track tasks and approvals, produce simple Fabric **item/block source**, generate deterministic 16×16 placeholder textures, validate the output, inspect the environment, and request an explicitly approved local Gradle build. It **cannot yet turn an arbitrary creative prompt into an automatically implemented, game-tested mod**. Minecraft itself was not available to run build/runtime tests in the development environment.

## Architecture commitments

- **Hybrid local-first:** Fabric workspaces, Gradle, Blockbench and future game tests stay local. Claude Code is an optional *developer integration*, not a required application dependency.
- **Fabric-first:** one narrowly scoped, pinned `fabric-1.21.1-candidate` profile mirroring the official FabricMC example mod (Mojang mappings, Loom 1.18, Gradle 9.7.1). Generator output has been **build-verified and tested in-game** (2026-10-20): see `examples/crystal_example/EVIDENCE.md`.
- **Approval autonomy:** reviewers approve the specification and any Gradle execution; source files are only generated in a new/empty folder; no silent executable installation, publishing or Minecraft save modification.
- **Evidence instead of wishful thinking:** `SOURCE_GENERATED_UNVERIFIED`, `BUILD_PASSED_GAME_UNTESTED`, and separate QA tasks are distinct outcomes.

## What works now

| Capability | Status |
|---|---|
| CLI (`craftctl`) and a local browser UI | **Implemented, exercised** |
| Read-only environment inspection | **Implemented, tested** |
| Deterministic idea interpretation (`items: ...; blocks: ...`) | **Implemented, tested** |
| Persistent SQLite projects, events, tasks and leases | **Implemented, tested** |
| User-spec approval + operation-scoped, one-use build approval | **Implemented, tested** |
| Fabric source generation, pixel-art placeholders, Java/resources | **Implemented, statically tested** |
| SHA-256 file manifest and static JSON/resource existence validation | **Implemented, tested** |
| One-use, explicitly authorized Gradle build invocation | **Implemented; not exercised against Minecraft here** |
| Restricted MCP interface (read-only tools plus approved source generation) | **Implemented, protocol smoke-tested** |
| 12 subagents + 12 skills (one per role in `capabilities.py`), deny rules and a PreToolUse guard | **Included and exercised by a real Claude Code session** |
| Blockbench/GeckoLib models via the vendored `tools/blockbench-mcp-safe` MCP (zero deps, Node only) authored by the designer worker on `MODEL` tasks | **Built; needs a real designer run + Blockbench check (R6 slice 2)** |
| Controller-driven dispatch (`craftctl dispatch`): one bounded Claude Code worker per task, schema-validated handoff, runs recorded | **Built and unit-tested with a fake provider; not yet proven against a real `claude -p` run** |
| GeckoLib mob modeling, Blockbench MCP, fully automatic worlds | **Planned / not integrated** |
| Real Minecraft GameTest, gameplay and multiplayer proof | **Not integrated** |
| Windows installer/managed JDK/Gradle provisioning | **Planned** |

## Quick start — Windows 11 / PowerShell

Install **Python 3.11+** (required to run the Orchestra itself, not to compile Minecraft). No Minecraft, JDK, Blockbench or Gradle are needed just to try the idea/plan/source flow.

```powershell
# Unzip this repo; open PowerShell in its directory
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
craftctl doctor
craftctl ui
```

The UI prints a **localhost-only URL containing an ephemeral authentication token**. Open it in your browser; create a mod, inspect its specification, approve it and generate source. The generated workspace is under `%USERPROFILE%\.minecraft-mod-orchestra\projects\<mod_id>` unless you set `CRAFTCTL_HOME`.

### Run through the CLI instead

```powershell
craftctl new --name "Crystal Frontier"  # free text works too: the interpreter agent proposes the spec (craftctl dispatch <id> --task <id>:SPEC)
craftctl new --name "Crystal Frontier" --id crystal_frontier --package com.example.crystalfrontier --idea "items: sky crystal, lunar gem; blocks: crystal stone"
craftctl add-recipe crystal_frontier --id frontier_block --kind shaped --result frontier_block --pattern CCC CCC CCC --key C=crystal   # USER-ONLY, before generate
craftctl add-drop crystal_frontier --block crystal_ore --item crystal --min 1 --max 2 --fortune --silk-touch
craftctl set-tab crystal_frontier --label "Crystal Frontier" --icon crystal   # or put 'tab: Crystal Frontier' in the idea
craftctl plan crystal_frontier
craftctl approve-spec crystal_frontier
craftctl generate crystal_frontier
craftctl validate crystal_frontier
craftctl status crystal_frontier
craftctl footprint crystal_frontier
```

**Intent syntax today:** `items: moon shard, crystal rod; blocks: carved slate, ore rock`. Unsupported advanced ideas (e.g. `boss`, `biome`, `dimension`, `GeckoLib animation`) generate blocking questions; they are **not** silently substituted with a basic item.

### Build the generated Fabric mod

Building requires **JDK 25** (Gradle 9.7.1 + Loom 1.18 runtime; sources target Java 21); Gradle itself is fetched by the shipped, hash-verified official wrapper, Gradle or a reviewed Gradle wrapper, a network connection for initial dependency resolution, and your explicit one-time approval. The generated source currently **does not include a Gradle wrapper JAR**; see `docs/SETUP.md` for why and how to bootstrap one from trusted sources.

```powershell
craftctl request-build crystal_frontier
craftctl approvals crystal_frontier
craftctl decide <approval-id> grant
craftctl build crystal_frontier --approval-id <approval-id>
craftctl logs crystal_frontier
craftctl add-task crystal_frontier --id SAPPHIRE --role coder --title "Add a sapphire item"   # USER-ONLY
craftctl dispatch crystal_frontier --task crystal_frontier:SAPPHIRE   # USER-ONLY: runs ONE Claude Code worker
craftctl orchestrate crystal_frontier --max-runs 3   # USER-ONLY: keep dispatching until you are needed; failed builds open REPAIR tasks for the debugger automatically
craftctl request-smoke crystal_frontier && craftctl decide <id> grant && craftctl server-smoke crystal_frontier --approval-id <id>   # dedicated server boot, records SERVER_BOOT_PASS
craftctl break crystal_frontier --fault wrong-mapping   # USER-ONLY test fixture for the repair loop
craftctl runs crystal_frontier
craftctl requeue crystal_frontier:SAPPHIRE   # USER-ONLY: FAILED/WAITING_USER -> READY
craftctl evidence crystal_frontier CLIENT_BOOT_PASS --note "Loading N mods: - crystal_frontier"   # USER-ONLY
craftctl release crystal_frontier:SCAFFOLD      # USER-ONLY: break a stuck lease
craftctl delete crystal_frontier --yes --workspace   # USER-ONLY
```

A Gradle build runs project code **without OS-level sandboxing in this pre-alpha**. Review Gradle files and JDK before approving; the wrapper is the official Gradle one, hash-verified (`src/mod_orchestra/resources/gradle-wrapper/PROVENANCE.md`). Build success is not gameplay success; test in an isolated Minecraft instance before shipping.

## Integrate with Claude Code (advanced, optional)

This repository contains `.mcp.json` (MCP server), `.claude/agents/` (12 subagents), `.claude/skills/` (12 skills, preloaded per role), `.claude/settings.json` (deny rules for USER-ONLY `craftctl` commands) and `.claude/hooks/guard.py` (PreToolUse backstop), plus `CLAUDE.md`. After installing `craftctl` into an environment available to Claude Code, open the repository using Claude Code and verify the `minecraft-orchestra` MCP server appears. The MCP exposes only typed diagnostic/project/plan/generate/footprint/validation tools—**not user approval-granting tools, arbitrary shell execution, or Blockbench by default**.

The agent roles and skills are prompts/playbooks, not an implemented provider-independent execution sandbox or autonomous planner yet. When agents work on a mod, review `docs/SECURITY.md` first.

## Repository map

```text
src/mod_orchestra/       Python stdlib controller, CLI, MCP, Fabric generator, state, UI
src/mod_orchestra/static Local browser UI (no Node/npm build required)
.claude/agents/          Claude Code subagents (12)
.claude/skills/          Domain procedures (12), preloaded per subagent
.claude/settings.json    Permission deny/allow rules + PreToolUse hook
.claude/hooks/guard.py   Blocks USER-ONLY craftctl ops and git push from agents
knowledge/               Pin-aware source notes and recipes
profiles/                Version profile and policy metadata
tests/                   Unittest suite, CLI workflow and security negative cases
examples/                Small generated showcase project source
.github/workflows/       Python CI
CLAUDE.md                Agent operating policy
docs/                    Architecture, decisions, setup, security and roadmap
```

## Testing

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Tests check intake, generated JSON/PNG/file integrity, safe workspace paths, task leases, approvals, MCP tool restrictions and CLI end-to-end creation. CI does **not** run Gradle or Minecraft; that remains an explicit milestone.

## License: free to use, free to fork, never for sale

BlockMinion is **source-available**: the code is public, and you may use it, change it and share it for free. It is **not**
OSI "Open Source", because of one restriction: nobody may sell the software itself. Full terms in [LICENSE](LICENSE);
attribution and third-party notices in [NOTICE.md](NOTICE.md); names and logo rules in [TRADEMARKS.md](TRADEMARKS.md).

**You may**
- download, install and use it for anything: personal, educational, research, professional, commercial;
- create Minecraft mods with it and **sell them**, with no royalty or fee to this project (they are yours);
- read and modify the code, make forks and derivative versions;
- redistribute the original or your fork, **free of charge**;
- charge for your own work around it: installation, configuration, customization, consulting, training, support;
- accept donations for a free fork;
- contribute (see [CONTRIBUTING.md](CONTRIBUTING.md)).

**You may not**
- sell the software, or a renamed, rebranded or lightly modified copy of it, or charge for access to it or its features;
- present a fork as the official project or claim to be its original author;
- remove the copyright and license notices;
- use the project's name or logo to impersonate its maintainers.

**Before this license, the project was MIT.** Everything published up to tag `v0.13.4-prealpha` stays under MIT for anyone
who received it ([LICENSE-MIT.txt](LICENSE-MIT.txt)); those permissions are not revoked. The new license applies from the
commit that introduced it onward.

### Licensing FAQ

- **I modified BlockMinion, added features, and give my version away for free.** Allowed. Keep `LICENSE`, `LICENSE-MIT.txt`
  and `NOTICE.md`, add your copyright line to your parts, give your fork its own name and say it is based on BlockMinion.
- **Someone renames BlockMinion and sells it for $20.** Prohibited for the code covered by the new license, unless the
  copyright holder authorizes it separately. Code they obtained under the earlier MIT releases keeps MIT permissions, which
  do allow selling that older code; the license cannot reach back.
- **I built an RPG mod with BlockMinion and sell it for $15.** Allowed, with nothing owed to this project. Your mod is
  Independent Content. Minecraft's EULA, the licenses of the libraries your mod uses (Fabric, GeckoLib, Player Animation
  Library, each MIT or Apache) and any third-party content are separate obligations of yours.
- **I charge a customer $50 to install, configure, customize or fix BlockMinion for them.** Allowed: that is a service,
  as long as the customer is paying for your work and could get the software itself for free.
- **I distribute a free fork and accept donations.** Allowed, provided no payment is required to get or use it.
- **Someone publishes a free fork but advertises themselves as the original creator.** Not allowed: `LICENSE` section 3
  forbids misrepresenting authorship, and `TRADEMARKS.md` requires a distinct name and a truthful "based on BlockMinion".
- **Is this legal advice?** No. The license is a custom text; its enforceability has not been tested, and it has not been
  reviewed by a licensing body. The project recommends professional review before relying on it in a dispute.

## Project status, development and contributions

The master architectural plan from the research review is in `docs/MASTER_PLAN_v2.md`; the forward execution plan is `docs/DEVELOPMENT_PATH.md` (`docs/ROADMAP.md` is kept as history). **What "done" means is fixed in `docs/V1_DEFINITION.md`**; anything outside it lives in `docs/V2_BACKLOG.md`. The origin audit includes [Universal Modder](https://github.com/rehan-remade/universal-modder), Fabric's [official example mod](https://github.com/FabricMC/fabric-example-mod), [GeckoLib](https://github.com/bernie-g/geckolib) and Blockbench MCP candidates. **These projects are not bundled or executed**; provider adoption requires license and safety review.

All ordinary Python dependencies are standard-library modules. `pip install -e .` uses `setuptools` packaging; users need a working Python packaging environment. Local state/credentials are not included in the Git repo or ZIP.

## Honest limitations

1. **One verified path only:** static items/blocks on Fabric 1.21.1 build and run (`examples/crystal_example/EVIDENCE.md`). Anything beyond that (recipes, entities, worldgen) is still unverified. The Gradle wrapper JAR cannot be bundled without a verified source.
2. **No automatic third-party software installers yet:** first-run checks and actionable instructions exist, but managed installation is a later milestone.
3. **No arbitrary natural language auto-coding yet:** advanced ideas are still tasks for Claude Code workers or human developers. No OpenAI/Anthropic API account is required to use deterministic mode.
4. **Local web UI is a developer prototype:** token-authenticated localhost, not a hardened multiuser desktop product. Disable port forwarding and do not expose it to the LAN/internet.
5. **No security sandbox:** agent prompts and MCP permission lists are *not* isolation. Launch untrusted code only in a real sandbox/VM after explicit approval.

## Official references

- [Fabric documentation](https://docs.fabricmc.net/) and [Fabric developer setup](https://fabricmc.net/develop/)
- [Fabric Example Mod](https://github.com/FabricMC/fabric-example-mod)
- [Fabric Maven](https://maven.fabricmc.net/)
- [GeckoLib](https://github.com/bernie-g/geckolib)
- [Blockbench](https://www.blockbench.net/wiki/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

*Minecraft is a trademark of Mojang Studios/Microsoft. This project is an independent tool and is not affiliated with or endorsed by them.*

### Coordinator and knowledge commands

```powershell
craftctl capabilities
craftctl next crystal_frontier
craftctl handoff crystal_frontier crystal_frontier:BUILD
craftctl kb-search "fabric loom profile"
craftctl footprint crystal_frontier --write
```

These provide bounded developer-facing task packets and reference lookup. They **do not automatically spawn model workers** or bypass approvals. In a future agent-adapter milestone, `handoff` will feed a supervised Claude Code worker with scoped task permissions.

### Bounded build diagnostics

`craftctl logs <mod-id>` shows a limited build-log tail, and `craftctl diagnose <mod-id>` classifies familiar Gradle, Java compilation, Mixin, registry, resource and GeckoLib error patterns. These are **heuristics**, not a full debugger or automatic repair; continuous in-game log collection is still planned.

## Push this project to GitHub

After extracting the ZIP and reviewing the source:

```powershell
git init
git add .
git commit -m "Initial Mod Orchestra pre-alpha"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Create the empty GitHub repository first and replace the placeholder remote. Do **not** commit your local `CRAFTCTL_HOME` projects, credentials or Minecraft saves.
