# Pilot testing log

Findings from exploratory testing of the orchestrator (Python layer only; no Gradle/Minecraft
available in the test environment). Severity: **High** = generated output cannot compile or a
safety gate fails; **Med** = wrong/unclear behavior a user will hit; **Low** = polish.

Status legend: OPEN · FIXED(branch) · WONTFIX

## Round 1 — 2026-10-19 · CLI + UI API · base `dev` @ 5b2fae8

### Bugs

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| B1 | High | generator | Item/block id `mod_id` → `public static final Item MOD_ID` collides with the `MOD_ID` string constant. Duplicate field, javac fails. Uniqueness check only compares raw identifiers, not derived Java names. | FIXED (`claude-feature/round1-fixes`) |
| B2 | High | generator | Item `ruby_item` + block `ruby` → `RUBY_ITEM` emitted twice (item + BlockItem). Duplicate field; block also lands in the wrong creative tab. Same root cause as B1. | FIXED (`claude-feature/round1-fixes`) |
| B3 | Med | generator | Datapack folder `loot_tables/` is ignored by 1.21+ (singular `loot_table/`); blocks dropped nothing. Test asserted the wrong path. | FIXED (`claude-feature/mojmap-1.21.1-generator`) |

### UX / correctness

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| U1 | Med | build | One-use build approval is **consumed even when no Gradle is found** (`BUILD_BLOCKED`). User must request + grant again for a tooling problem. Pre-check wrapper/Gradle before `consume_approval`. | FIXED (`claude-feature/round1-fixes`) |
| U2 | Med | build | `request-build` succeeds on a tampered workspace; failure only surfaces at `build` after the approval is spent. Run `validate_generated` inside `request_build` and refuse early. | FIXED (`claude-feature/round1-fixes`) |
| U3 | Low | validation | Single-char identifiers rejected (regex `{1,39}` → min 2) but the message says "starting with a letter". Fix message (or allow 1 char). | FIXED (`claude-feature/round1-fixes`) |
| U4 | Low | validation | Invalid-identifier error echoes the full offending string (tested 300 chars). Truncate to ~40. | FIXED (`claude-feature/round1-fixes`) |
| U5 | Low | diagnose | `diagnose` with no build log returns `lines_reviewed: 1, classifications: []` instead of saying there is no log. | FIXED (`claude-feature/round1-fixes`) |
| U6 | Low | planner | `:BUILD` task is assigned role `debugger`. Arguably `coder`/`release`; debugger should own the failure path. Design question. | FIXED (`claude-feature/r2-dispatch`: BUILD → coder; debugger owns BUILD_FAILED) |
| U7 | Med | UI clarity | UI exposes plan/approve/generate/request-build/grant/deny/build but **no validate, logs or diagnose views**. After a failed build the user cannot see why from the UI. | FIXED (`claude-feature/r2-dispatch`: Verification panel — validate/build log/diagnose; Evidence panel; Agent runs feed with handoff, needs_user and worker log; dispatch + requeue from the UI). Browser rendering not yet checked by RTQ. |
| U8 | Low | UI/CLI clarity | Blocking-question message says "Update the idea in a new project" — there is no edit path, so the user must pick a new mod id. Either allow re-interpreting the idea on an unapproved project or explain the constraint. | OPEN |

### Verified OK

- Input validation: invalid mod id, shell chars in package, empty idea, duplicate identifiers, unicode/punctuation, numeric-leading ids, nonexistent project.
- Unsupported keywords (`boss`, `biome`) produce blocking questions; `approve-spec` refuses while they remain.
- `generate` is one-shot; second call refused. Never overwrites an existing workspace.
- Approvals: bogus id refused; granted approval is one-use (second `build` refused).
- Manifest tamper detection (`validate` → `CHANGED: build.gradle`).
- UI: 403 without token, with wrong token, with non-localhost `Host`; POST requires matching `Origin`; bound to 127.0.0.1 only; path traversal and unknown endpoints rejected; malformed JSON returns 400.
- UI and CLI share the same core: identical results for create → plan → approve → generate → request-build.

## Round 2 — 2026-10-19 · MCP server (stdio) · base `dev` @ fcf723c

Driven with a hand-written JSON-RPC client over `craftctl mcp`: handshake, `tools/list`,
every tool, forbidden names, malformed frames, schema violations, path traversal.

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| M1 | Low | protocol | `initialize` always answered `2025-03-26` regardless of the client's requested version. Now echoes a supported requested version, else the newest supported. | FIXED (`claude-feature/pilot-testing-r2`) |
| M2 | Low | tools | `orchestra_validate_source` before generation leaked a raw `FileNotFoundError` with the absolute workspace path. Now a clean `StateError`. | FIXED (`claude-feature/pilot-testing-r2`) |
| M3 | Low | tools | Argument types were not checked against `inputSchema` (`project: 123` was looked up as `"123"`). Now enforced for string properties. | FIXED (`claude-feature/pilot-testing-r2`) |
| M4 | **High** | repo | README, CLAUDE.md and ROADMAP claim `.mcp.json` and `.claude/agents/*.md` (11 roles) ship in the repo. **Neither was ever committed.** `.mcp.json` added in round 2; 12 agents, settings deny rules and a PreToolUse guard added in `claude-feature/r2-agents`; fixed and exercised in round 3. | FIXED |
| M5 | Low | tools | `orchestra_knowledge_search` returned absolute install paths. Now `repo:<relative>` / `home:<relative>`. | FIXED (`claude-feature/pilot-testing-r2`) |
| M6 | Low | design | `resources/list` and `prompts/list` return Method not found. Fine for now; skills/knowledge could be exposed as Resources later. | OPEN (design) |
| M7 | Low | design | Server is a hand-rolled JSON-RPC loop. Works, but any spec drift is on us. Evaluate the official Python SDK once a real Claude Code session confirms the current server connects. | OPEN (design) |
| M8 | Med | agent clarity | `initialize` carried no `instructions`; a cold agent had no way to learn that approve/build are USER-ONLY and would hunt for missing tools. Added `instructions` naming the exact `craftctl` commands to ask the user for. | FIXED (`claude-feature/pilot-testing-r2`) |

### Verified OK

- Only the 12 `orchestra_*` tools are listed; approve/decide/build/new_project are rejected by name.
- `orchestra_generate_source` refuses before user approval; `orchestra_project_plan` is one-shot.
- Malformed frames (non-JSON, JSON array, missing method, missing params, non-dict args, extra/missing args) all produce JSON-RPC errors; the loop never crashes and stderr stays empty.
- Project ids are looked up, never used as paths: `../../etc` → `Project not found`.
- Notifications get no reply (correct per spec).

## Host verification — 2026-10-20 · RTQ · Windows / JDK 25 · `dev` @ aa8538d

`examples/crystal_example` built, client and dedicated server booted, content verified in-game (R1 FAB-001/FAB-002). Full record: `examples/crystal_example/EVIDENCE.md`. Evidence levels and `craftctl evidence` added in `claude-feature/r1-evidence-levels`.

## Host run 2 — 2026-10-20 · RTQ · Windows / Git Bash / venv · controller-driven `craftctl build`

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| H1 | High | repo | No `.gitattributes`; Windows checkouts turned `gradlew` into CRLF, hash check refused to ship it (`0367e8c7…` vs recorded `a5a5c199…`). Added `.gitattributes` (gradlew LF, `*.bat` CRLF, jar/png binary). | FIXED (`claude-feature/hotfix-wrapper-eol`) |
| H2 | High | generator | A failing `generate` left a half-written workspace **and** kept the SCAFFOLD task lease, so the retry hit "Scaffold task unavailable" / "No overwrite permitted". Now all-or-nothing: partial dir removed, lease released, project stays PLAN_READY. | FIXED (`claude-feature/hotfix-wrapper-eol`) |
| H3 | Med | UX | Workspaces generated by an older generator (no wrapper) fail `build` with "No Gradle wrapper" instead of "generated by an older version; regenerate". The lock file carries the generator version, so this is detectable. | FIXED (`claude-feature/r1-ux-leases-delete`) |
| H4 | Med | CLI | No `craftctl delete <id>`; removing a workspace by hand leaves an orphan project row in SQLite. | FIXED (`claude-feature/r1-ux-leases-delete`) |
| H5 | Low | docs | SETUP assumed `pip install -e .` puts `craftctl` on PATH; on Windows the Store Python aliases can shadow a venv. Documented. | FIXED (docs) |

## Host run 3 — 2026-10-20 · RTQ · Windows / JDK 25 · `claude-feature/hotfix-wrapper-eol`

Controller-driven path verified end to end with the shipped wrapper and no manual steps:
`new → plan → approve-spec → generate → request-build → decide grant → build` on project `wrap_test3`.
`build` exit 0; `BUILD_PASS` recorded by the controller with JAR sha256 `fb58b290f5c0d7f29f95dc1454b38a1c4149eb262e2016fb50bd53f18d95ec9c`;
approval `CONSUMED`; `:BUILD` task `DONE`, `:GAME` `READY`; status `BUILD_PASSED_GAME_UNTESTED`.
H1 (`.gitattributes`) and H2 (lease release, `TASK_RELEASED` event observed) confirmed on Windows. **R1 FAB-001 complete.**

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| H6 | Med | UX | A task held by an expired-but-not-yet-timed-out lease reports only "task unavailable"; nothing shows who holds it or when it expires, and there is no `craftctl release`. | FIXED (`claude-feature/r1-ux-leases-delete`) |

## Round 3 — 2026-10-20 · Claude Code session (R2 adapter smoke) · base `dev` @ 37f06aa · Windows / JDK 25

First real Claude Code session (desktop app, PowerShell primary tool) opened on the repo after the
adapter merge. Baseline: local `dev` was 18 commits behind `origin/dev` (fast-forwarded first);
`python -m unittest` 79 tests, 1 error (A5), 3 skipped; `python -m mod_orchestra.cli doctor` OK
(`craftctl` itself not on PATH, see A1). Fixes on `claude-feature/r2-smoke`.

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| A1 | **High** | MCP | `.mcp.json` ran `craftctl mcp`; `craftctl.exe` lives in the Store-Python `Scripts/` dir that is not on PATH, so Claude Code reported `minecraft-orchestra (CONNECTION_CLOSED)` at startup. Launched by hand as `python -m mod_orchestra.cli mcp` the server is fine: handshake echoes `2025-06-18`, 563-char `instructions`, 12 tools, `orchestra_doctor`/`orchestra_capabilities` answer. `.mcp.json` now uses the module form; test added. Reconnect needs a session restart (not yet observed). | FIXED (`claude-feature/r2-smoke`) |
| A2 | **High** | agents | All 12 agents listed `mcp__minecraft-orchestra__project_status` etc. Claude Code names MCP tools `mcp__<server>__<tool>` and the server's tools are `orchestra_*`, so the real name is `mcp__minecraft-orchestra__orchestra_project_status`; no role would have received any MCP tool. `test_claude_code_config` accepted both spellings, which is how it slipped through. Renamed in all agents; test now accepts only real names. | FIXED (`claude-feature/r2-smoke`) |
| A3 | **High** | hook | `settings.json` ran `python .claude/hooks/guard.py` relative to the shell cwd. After one `cd examples/crystal_example` the script was not found and Claude Code fails closed: **every** Bash/PowerShell/Write/Edit call was blocked ("can't open file ... examples\crystal_example\.claude\hooks\guard.py") until the session directory was reset. Anchored to `"$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py"`; settings hot-reloaded and the same call from the subdirectory now passes. Test asserts the anchor. | FIXED (`claude-feature/r2-smoke`) |
| A4 | **High** | agents | Only 9 of 12 subagents loaded (`Agent(subagent_type: investigator/release/world-builder)` → "not found"). Their unquoted YAML `description:` contains `": "` (e.g. "reports its baseline: structure, ..."), a YAML mapping error; Claude Code skips the file silently. Descriptions quoted; frontmatter test rejects unquoted scalars with `": "`. Agent files are **not** hot-reloaded: loading of the three must be confirmed in a fresh session. | FIXED, load unconfirmed |
| A5 | Low | tests | `test_safe_inside_blocks_symlinks` errors on Windows without Developer Mode/admin (`WinError 1314` creating the symlink). CI passes because runners are elevated. Now `skipTest` when the host cannot create symlinks. | FIXED (`claude-feature/r2-smoke`) |
| A6 | Med | settings | `permissions.deny` rules are spelled `Bash(craftctl decide*)`. In the desktop app on Windows the primary shell tool is `PowerShell`, which those rules do not cover; the hook is the only control there. Hook matcher does include `PowerShell`. Decide whether to mirror the rules as `PowerShell(...)` once that syntax is confirmed honoured. | FIXED (`claude-feature/r2-smoke`, PowerShell(...) deny/allow rules mirrored from Bash) |
| A7 | Low | hook | Guard regex is bypassable by indirection (`C=craftctl; $C decide ...`, `python -c "from mod_orchestra.cli import main; main([...])"`). Expected: CLAUDE.md rule 4 says hooks are not a security boundary; the controller's approval state is. Logged so nobody mistakes the hook for one. | OPEN (design) |
| A8 | Low | hook | False positive: the guard scans the whole command string, so a `git commit` whose heredoc message mentions "git push" is blocked. Worked around with `git commit -F <file>` (which also shows how thin the regex is, see A7). Consider matching only at command-start positions (`^`, `&&`, `;`, `|`). | OPEN |
| A9 | Low | session | Adapter files that land mid-session (here via the fast-forward) are not picked up: subagents appeared only after the session directory was reloaded; hooks did hot-reload. Not a repo bug; worth a line in SETUP ("restart the session after pulling adapter changes"). | OPEN (doc) |

### R2 proof — `sapphire` item added by the `coder` subagent

Task `R2-PROOF-001`: the real `coder` subagent (skill preloaded, under the hook) added a `sapphire`
item to `examples/crystal_example`: `SAPPHIRE` registered with Mojang mappings in `ModMain.java` and
added to `INGREDIENTS`; `models/item/sapphire.json`; lang entry; 16×16 RGBA placeholder texture made
with the Python stdlib. Scope held: exactly four files under `src/main/`, nothing else touched, no
USER-ONLY command run. `./gradlew build --no-daemon --console=plain` → exit 0, `BUILD SUCCESSFUL in 13s`
(incremental; `compileJava`, `jar`, `remapJar` executed). The orchestrating session re-verified the diff,
the PNG header (16×16, RGBA), and the JAR: `build/libs/crystal_example-1.0.0.jar` SHA-256
`e8460b2e550e89563c79141fba6f22d6a1bf768bd39b207ef11495644f8d93c4` contains the new model, texture, lang
and `ModMain.class`. The handoff reported only observed evidence and named the right next actions.

**Level reached: BUILD_PASS observed in-session; then CLIENT_BOOT_PASS (client log: `crystal_example 1.0.0`
loaded, 0 errors, no missing texture/model) and CONTENT_VERIFIED by RTQ (all three gems in the Ingredients
tab, sapphire named and textured).** Recorded in `examples/crystal_example/EVIDENCE.md`, not in the Footprint
(`crystal_example` is not a controller project; `craftctl projects` lists only `wrap_test3`). **R2 proof
complete.** A first attempt with a generic worker, launched before the `coder` type had loaded, stalled on
A3 and was stopped; it left no file changes but did open a terminal tab ("write build wrapper").

### Verified OK

- Guard (`.claude/hooks/guard.py`) exercised with hook payloads: blocks all eight USER-ONLY commands in both spellings (`craftctl …`, `python -m mod_orchestra.cli …`), for `Bash` and `PowerShell` payloads, including when prefixed by `cd … &&`; blocks `git push`, `git reset --hard`, `git clean -fd`; allows `craftctl doctor/status`, `./gradlew build`, `git status`; researcher `Write` only under `knowledge/`. Live check: a Bash call containing `craftctl decide x grant` was refused by the running hook with the USER-ONLY message (after A3 was fixed).
- MCP server over stdio via the module entry point (see A1). The `coder`, `coordinator`, `debugger`, `designer`, `interpreter`, `planner`, `qa`, `researcher`, `scrum-master` subagents load and `coder` runs with its skill preloaded.
- Session environment: `git fetch` over SSH fails (`Permission denied (publickey)`) inside the tool shell, so feature branches from a session must be pushed by the user.

## Host run 4 — 2026-10-21 · RTQ · Windows / Claude Code native · controller-driven dispatch (`claude-feature/r2-dispatch`)

First `craftctl dispatch` against a real `claude -p`. Project `wrap_test3`, ad-hoc task `SAPPHIRE` (coder).

- Run 1 `F3ooCkRVv_dq`: worker ran 155 s, exit 0, $0.94, produced a valid handoff; **controller rejected it** (D1).
- Runs 2–4 (`N3Lv9o_C4GRT` 76 s $0.76 WAITING_USER; `bOAtZ3sP-qm9` 64 s $0.49 rejected by D5; `kgk-WNuFojfD` 72 s $0.44 DONE with real BUILD_PASS). Total agent cost for the sapphire task ≈ $2.63 across 4 runs, 3 of them lost to controller bugs D1/D5/D6.
- Closing: `accept-changes N3Lv9o_C4GRT` → `validate PASS (revisions 1)` → `request-build` → `decide` → `build` exit 0 in 8.4 s through the new process broker (first SEC-002 run on Windows) → **BUILD_PASS #2, JAR sha256 `7debfd3d…69e7f2`**. v1 criterion 3 observed end to end. Criterion 5 closed in-game: `CLIENT_BOOT_PASS` (56 mods, `wrap_test3 1.0.0`) and `CONTENT_VERIFIED` (Sapphire in Ingredients next to Ruby) recorded by the owner.
- Run 2 `N3Lv9o_C4GRT` detail: 76 s, 16 turns, $0.76. Worker wrote `ModMain.java`, `en_us.json`, `models/item/sapphire.json`, `textures/item/sapphire.png`, validated JSON/PNG, called `orchestra_validate_source` over MCP (`--mcp-config` works headless), could not build (D2), and reported honestly: `status WAITING_USER`, `evidence STATIC`, `needs_user` = request-build / decide / build. **Criterion 3 (controller dispatches agents; gates hold) observed end to end.**

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| D1 | High | provider/broker | Log header was written to Python's buffer while the child wrote to the fd, so the header (carrying the whole prompt) landed after the JSON envelope; the parser spanned to the prompt's example handoff block and failed. Prompt now via stdin, header flushed + truncated, envelope found with `raw_decode`. | FIXED |
| D2 | Med | provider | Worker's `./gradlew.bat build` was denied: allow list had `./gradlew` and `gradlew.bat` but not `./gradlew.bat`. Added (both shells). | FIXED |
| D3 | High | manifest | After an agent edit, `validate` reported CHANGED and `request-build` refused, so agent work could not be built through the controller (blocks v1 criterion 5). Added manifest revisions attributed to runs; unreported edits still fail. | FIXED |
| D5 | Med | handoff schema | Run `bOAtZ3sP-qm9` (64 s, $0.49): coder reported `DONE` + `needs_user` (the trusted-build commands); controller rejected it as contradictory. Rule was wrong: a finished coder always has user steps. DONE+needs_user allowed; semantics stated in the prompt. | FIXED |
| D6 | Med | manifest | Run `kgk-WNuFojfD` (72 s, 11 turns, $0.44): `DONE` with real `BUILD_PASS` (gradle exit 0 + jar inspection) but `changed_files: []` because an earlier run wrote the files; acceptance only looked at the current run, so validate stayed FAIL. Now a task's edits are the union of all its runs' reports; `craftctl accept-changes <run>` (USER-ONLY) for manual acceptance. | FIXED |
| D7 | High | build/evidence | `request-build` only accepted `SOURCE_GENERATED_UNVERIFIED`, so a project that had already been built could never be rebuilt after an agent revision ("Only a generated starter may be built"). Now any generated status is buildable; an accepted revision resets the project to `SOURCE_GENERATED_UNVERIFIED` (`VERIFICATION_RESET`) and evidence levels count only when observed on the current manifest. | FIXED |
| D8 | Med | build | H3 check rejected `wrap_test3` ("older generator v1") although it ships the wrapper: it was generated after the wrapper landed but before `generator_version` existed. The check now keys on the real incompatibility (wrapper files absent), not the version number. | FIXED |
| D4 | Low | packet | Task board in the handoff packet showed `BUILD [debugger]` for projects planned before U6; cosmetic, old data. | WONTFIX |

## Host run 5 — 2026-10-21 · RTQ · Windows · repair loop (`claude-feature/r5-repair-loop`)

Fault `wrong-mapping` injected on `wrap_test3` → trusted build failed in 6.8 s → `REPAIR:1` opened → `orchestrate`: **debugger fixed it unaided (82.9 s, $0.62, `DONE`)**. Then `missing-import` (REPAIR:2, 74 s, $0.61, DONE, one run, loop stopped for the trusted build) and `bad-loot-json`: trusted build passed, `server-smoke` booted the dedicated server in 26.8 s, read `Couldn't parse element minecraft:loot_table/wrap_test3:blocks/ruby_ore - Unknown registry key`, opened REPAIR:3; debugger fixed it (60 s, $0.41). Fault 3 confirmed: trusted build passed and a second `server-smoke` booted clean (`wrap_test3 1.0.0` among 44 mods, `Done (1.484s)!`, `stop` sent, clean shutdown, no mod errors) → `SERVER_BOOT_PASS` recorded by the controller. **v1 criterion 4: 3 of 3 faults repaired autonomously; total debugger cost $1.64.** `broker.run_watch` verified on Windows.

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| E2 | High | manifest | The qa worker reported `run/eula.txt` and `run/server.properties` as changed; they were accepted into the manifest. The server rewrites both on every boot, so the next `request-build` refused with CHANGED. Runtime dirs (`run/`, `build/`, `.gradle/`, `.mod-orchestra/`) are now never accepted and ignored in validation even if an old revision recorded them. | FIXED |
| E1 | High | orchestrate | After the repair `orchestrate` went on to the `GAME` (qa) task: 353 s and **$2.11** for a worker that ran `runServer` itself and whose `SERVER_BOOT_PASS` claim the controller cannot accept by design. Now: a repair `DONE` stops the loop (next step is the user's trusted build), and `GAME`/qa tasks are not dispatchable until a `BUILD_PASS` exists for the current source. | FIXED |

## Host run 6 — 2026-10-22 · RTQ · Windows · static content (`claude-feature/v1-static-content`)

Project `crystal_test` (2 items, 2 blocks, tab, 3 recipes, ore drop): trusted build passed; `server-smoke` booted clean with `crystal_test 1.0.0` loaded and the datapack counting **1293 recipes / 1402 advancements** (vanilla 1290 / 1399 + the mod's 3 + 3), `SERVER_BOOT_PASS` by the controller; client verified by the owner (tab with 4 entries, recipe-book unlock, 9→1 and 1→9 crafting, furnace, ore drops with Fortune, Silk Touch returns the ore — each one tried) → first project at **`GAME_VERIFIED`** with all four levels on one manifest. **v1 criterion 2 observed.**

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| F1 | Low | smoke | `server.properties` written by the smoke set `level-type=minecraft:flat` without `generator-settings`; vanilla logs `[main/ERROR] No key layers in MapLike[{}]` and falls back. Not a mod error (smoke still passed) but noise in a log that should be clean. Removed. | FIXED |
| F2 | Low | UX | `runClient` had to be run from the right workspace by hand; running it elsewhere shows another project's mod. Added `craftctl run-client <project>` (USER-ONLY) which launches the isolated client from anywhere and prints the exact `evidence` commands. | FIXED |

## Host run 7 — 2026-10-22 · RTQ · Windows · interpreter suite (`claude-feature/r3-interpreter`)

`craftctl interpret-suite`: 10 prompts (EN/ES, vague, grammar, unsupported, typos) through the real interpreter. **10/10 valid proposals, 0 controller rejections, every prompt ≤ 3 questions**, $2.55 total, 25–62 s each. Stricter per-prompt bar: 7/10. Results: `tests/v1/results/20261022-155823.json`. **v1 criterion 1 observed.**

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| G1 | Low | interpreter | Asked whether to add recipes to a prompt that mentioned none (07). Instruction tightened: never ask about optional additions; omit and note under assumptions. | FIXED (instruction) |
| G2 | Low | fixtures | 04 asked a legitimate question (vanilla already smelts emerald ore); 09's "extend the existing crystal mod" had no existing mod (that is criterion 5). Expectations/fixture adjusted. | FIXED |
| G3 | Low | interpreter | "make it cool" (03) produced deepslate variants and blasting recipes — reasonable for that prompt, but the no-scope-widening rule is now explicit. | NOTED |

## Round 4 — 2026-10-24 · Claude Code session (R6 scaffold) · `claude-feature/r6-geckolib-scaffold` @ 78975ef · Windows / JDK 25

Goal: first GeckoLib mob in-game (v1 criterion 6 at scaffold level). `craftctl new` is USER-ONLY, so the
session generated the handoff's exact spec (`items: sky crystal; mobs: sky critter; hostile mobs: shadow
stalker; tab: Critters`, package `com.rtq.crittertest`) straight through `fabric.generate(interpret(...))` into a
scratch workspace (`%LOCALAPPDATA%/Temp/mo-r6/projects/critter_scratch`, 32 files, static validation PASS) and
exercised it there. **Nothing below is recorded in the Footprint**; `critter_test` as a controller project still
has to be created, built and smoked by RTQ (commands at the end of this section).

Observed, in order: `python -m unittest discover -s tests` 159 tests, 1 failure (H1), 19 skipped → after H1 and the two new tests, 161
OK (20 skipped). `./gradlew.bat build --no-daemon --console=plain` → `BUILD SUCCESSFUL in 53s` on the first attempt; GeckoLib
4.7.3 resolved from Cloudsmith (POM HTTP 200; the same metadata lists 1.21.1 builds up to 4.9.3, pin kept);
`compileJava`, `jar`, `remapJar` executed; `build/libs/critter_test-1.0.0.jar` SHA-256
`6ef1c80bccd945c42baa1222b81b56b0c50f0010edc483d21c0af4bd21a7cba7`, 37 entries under `critter_test`/`crittertest`.
`runServer` via `broker.run_watch`: `critter_test 1.0.0` and `geckolib 4.7.3` in the mod list, `Done (4.745s)!`
after 24.8 s wall, `stop` sent, exit 0; no `critter_test` error, no exception. `runClient` (100 s capture, killed): same
mod list, resource reload with `critter_test` completed, all atlases created, title screen reached; no GeckoLib
error, no `Unable to load model`, no missing texture. **Level reached for the scratch workspace: BUILD_PASS,
SERVER_BOOT_PASS and CLIENT_BOOT_PASS observed in-session. CONTENT_VERIFIED (eggs in both tabs, critter wanders
and animates, stalker attacks) is not observed: nobody has entered a world yet.**

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| H1 | Low | tests | `test_packaged_resources_match_dot_claude` compared bytes; with `core.autocrlf=true` the working copy of `.claude/agents/designer.md` was LF while its packaged twin was CRLF (both LF in the index), so a clean checkout failed. Compares text now. | FIXED |
| H2 | **High** | geckolib.py | Entity loot tables used `minecraft:looting_enchant`, removed in 1.21 (renamed `enchanted_count_increase`, `enchantment` required). Any mob with drops would have failed datapack parsing on boot, exactly the `bad-loot-json` shape of host run 5, and opened a repair. Function renamed; test asserts the 1.21 name. The handoff spec has no drops, so the scratch run could not have caught it. | FIXED |
| H3 | **High** | fabric.py | No `models/item/<id>_spawn_egg.json` was generated: both eggs would have rendered as the missing-texture cube in the Critters and Spawn Eggs tabs. Now `{"parent": "minecraft:item/template_spawn_egg"}` per mob (tinted by the `SpawnEggItem` colours); test added. | FIXED |
| H4 | Med | spec | Every mob got the same default `egg_colors` (0x8A6DD1/0xE6D8FF): two indistinguishable eggs in one tab. `default_egg_colors(identifier, behavior)` derives a deterministic pair (dark base + saturated spot for hostile, bright + pale for passive); grammar, `add-mob` and `read_spec` without the field use it; explicit values are kept. | FIXED |
| H5 | Low | geckolib.py | Placeholder geo: the four leg cubes' UV (`[24+8i, 0]`) overlapped the body's UV island (x 0–39, y 0–17). Moved to row 18 beside the head. Cosmetic until the designer slice replaces the placeholders. | FIXED |
| H6 | Low | smoke | Vanilla logs `[main/ERROR] No data fixer registered for <entity>` once per modded `EntityType` without a DataFixer schema entry (seen for both mobs on server and client). Harmless and universal for Fabric mob mods, but `_mod_errors` would have flagged it whenever the mod id is a substring of the entity id (e.g. mod `critter`, entity `critter`) and opened a false repair. `smoke.BENIGN` skips that exact line; test covers it. | FIXED |
| H7 | Low | env | The session scratchpad path is too long for `fabric.generate` staging on Windows (`FileNotFoundError` on a 260+ char path, the MAX_PATH family of host run 8). Not a product bug: the controller's `~/.minecraft-mod-orchestra/projects/<id>` is short. Noted so nobody generates under `%TEMP%\claude\...`. | NOTED |
| H8 | Low | hook | Guard false positives widened: a `grep` whose pattern names a USER-ONLY subcommand, and a Python heredoc writing a memory note that mentions one, were both blocked (A8 family). Worked around with the Edit tool. | OPEN (A8) |

### Controller project `critter_test` — same day, after the push

RTQ created `critter_test` with the controller (`new` → `plan` → `approve-spec` → `generate`: 32 files, static
validation PASS, assets in the `DefaultedEntityGeoModel` layout, two `*_spawn_egg.json`, distinct egg tints
`0x0D2827/0x9B6867` stalker, `0x99A47D/0xDFE3D3` critter). Session-side in the real workspace: `./gradlew.bat build`
→ `BUILD SUCCESSFUL in 46s`; `runServer` via `run_watch` → `critter_test 1.0.0` + `geckolib 4.7.3` loaded,
`Done (4.991s)!` in 25.7 s, clean stop, only the two benign data-fixer lines; `craftctl validate` PASS (31 files).
Then the trusted path: **`craftctl build` → `BUILD_PASS` by the controller, JAR SHA-256
`5b453fc211f63473716c3b1d834b9b9c6e49e731a8cde3432ddc13396a2cd579` (identical to the session's build); `server-smoke`
→ `SERVER_BOOT_PASS` by the controller (H6 filter held: no false repair)**; `run-client` 371 s, exit 0, mod loaded.
In a creative world RTQ confirmed all five checks: Critters tab shows the sky crystal and both eggs with distinct
tints; both eggs in Spawn Eggs; the sky critter spawns as the grey quadruped, wanders, legs swing while walking,
head nods when idle; the shadow stalker approaches and hits; nothing invisible, no missing-texture cube, nothing
odd in the log. **v1 criterion 6 observed at scaffold level (placeholder model): spawns, moves, animates, hostile
attacks, spawn eggs work. Still missing for the criterion as written: a Blockbench model + texture (designer
slice), loot on death (the spec has no drops; `add-mob --drops` exists but was not exercised in-game), and the
`EVIDENCE.md` with screenshots/clip.** RTQ recorded `CONTENT_VERIFIED` (actor `user`, 20:31: "Critters tab: sky crystal + both eggs
with distinct colors; shadow stalker approached and hit for 1.5 hearts; sky critter roamed; both use the same
placeholder model, only the egg colors differ"). `CLIENT_BOOT_PASS` was not recorded, so the project stays at
`BUILD_PASSED_GAME_UNTESTED`: `derive_status` needs all of `BUILD_PASS`, `CLIENT_BOOT_PASS`, `SERVER_BOOT_PASS`
and `CONTENT_VERIFIED` on the same manifest to reach `GAME_VERIFIED`. One more evidence command closes it.

Not done in this round, by design: the Blockbench/designer slice (placeholders stay), natural spawning, sounds.
`GENERATOR_VERSION` not bumped: existing workspaces still build; only new generations get H2–H5.

**For RTQ (USER-ONLY, in this order):** `craftctl new --name "Critter Test" --id critter_test --package
com.rtq.crittertest --idea "items: sky crystal; mobs: sky critter; hostile mobs: shadow stalker; tab: Critters"` →
`craftctl plan critter_test` → `craftctl approve-spec critter_test` → `craftctl generate critter_test` (expect 32
files, `geo/`, `animations/`, `textures/entity/`, two `*_spawn_egg.json`) → `craftctl request-build critter_test`,
`craftctl decide <id> grant`, `craftctl build critter_test --approval-id <id>` → `craftctl request-smoke critter_test`,
`craftctl decide <id> grant`, `craftctl server-smoke critter_test --approval-id <id>` (expect `SERVER_BOOT_PASS` by
the controller, two benign data-fixer lines) → `craftctl run-client critter_test`, then in a creative world: both
eggs in **Critters** and **Spawn Eggs** (distinct tints), spawn the sky critter (grey quadruped placeholder: wanders,
legs swing while walking, head nods when idle) and the shadow stalker (approaches and hits for 3). Record with the
evidence subcommand: `CLIENT_BOOT_PASS --note "..."` and `CONTENT_VERIFIED --note "..."` with what was seen, plus
a screenshot or clip path for `EVIDENCE.md`. If a model is invisible or GeckoLib logs an error, send
`run/logs/latest.log`.

## Host run 9 — 2026-10-25 · RTQ · Windows / Node 22 · designer worker (`claude-feature/r6-designer-worker`)

First autonomous model: `craftctl dispatch critter_test --task critter_test:MODEL:sky_critter` → designer run `LvotaXwDc3Ow` (218 s, 28 turns, $1.82) using the vendored `blockbench-mcp-safe` over MCP: bird rig (9 bones / 11 cubes, 64×32), flat-colour texture generated by a script, `animation.sky_critter.idle` + `.walk`, `bbmodel_geckolib_validate` + `bbmodel_quality_gates` passed, renders inspected by the worker, exports written; the controller validated the deliverables and installed geo/animation/PNG over the placeholders (`MODEL_INSTALLED`). Trusted build → server smoke → `run-client`: **the bird renders in-game with its texture** (light-blue body, striped wings, orange beak/legs, white crest), idle and walk motion observed (`CONTENT_VERIFIED` ×2 by the owner). **v1 criterion 6 observed** except loot on death (slice 3).

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| I1 | Low | cli | `add-task` uppercased the whole suffix (`MODEL:SKY_CRITTER`), which would not match the mob id. Only the task kind is uppercased now. | FIXED |
| I2 | Low | manifest | Designer previews (`models/*_rest.png`, `_walk.png`) and its texture script were accepted into the manifest as reported changes. Harmless; consider excluding `models/*_rest.png`-style previews. | NOTED |
| I3 | Low | model | Designer flagged the bird (~0.4 blocks tall) vs the placeholder hitbox (0.8×0.9). Size/hitbox should derive from the model bounds in slice 3. | OPEN |

## Round 5 — 2026-10-26 · sandbox · UI/UX overhaul (`claude-feature/ui-ux-overhaul`), driven through the API with the fake provider

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| J1 | High | generate | A pre-generation interpreter run writes its log to `<workspace>/.mod-orchestra/runs/`, so `generate` saw a non-empty directory and refused. The UI flow (interpret first, generate later) always hit this; the CLI tests never did. `generate` now keeps a controller-owned `.mod-orchestra` and merges it into the staged workspace. | FIXED |
| J2 | High | plan | The plan was frozen at the first `dispatch`/`plan`; a later interpreter proposal (mobs, content) never got its tasks (`Task not found: …:MODEL:…`). `approve-spec` re-plans while no source exists; `set_tasks(replace=True)` keeps a DONE SPEC task. | FIXED |
| J3 | Low | fake provider | `CRAFTCTL_FAKE_REPLY_FILE` was read once; now read per run (dev/testing only). | FIXED |

Owner session on the UI (host run 10, 2026-10-26): drops edited through the picker → rebuild → client launched from the UI; feedback, Add-a-mob form, Autopilot; three UX findings fixed during the session (stale needs_user shown as pending; Autopilot buried in Verification; evidence from older sources mixed in). **v1 criterion 7 observed.** `models/sky_critter.bbmodel` opened in Blockbench via the new button: rig, animations and texture load — the last unverified claim of the blockbench-mcp-safe audit is now verified. I3 (hitbox from model bounds) closed as not needed: the owner judged the in-game hitbox adequate.

## Host run 11 — 2026-10-27 · RTQ · Windows · sandbox review of `claude-feature/v1-tool-sets`

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| K1 | High | delete | `FOREIGN KEY constraint failed`: `runs` and `task_instructions` rows were not deleted. | FIXED |
| K2 | Med | ui | `Task not found: ovis_moon%3ASPEC` — path segments were not URL-decoded. | FIXED |
| K3 | Med | interpreter | Handoff without `spec` was rejected and the loop stopped. Now auto-retried once with the reason; Autopilot continues. | FIXED |
| K4 | High | orchestrate | Autopilot dispatched a coder to `SCAFFOLD` ($0.58, deadlock against the generator's own lease) and earlier a coder to `BUILD` / a qa to `GAME`. All four are planner tasks owned by the controller/user, never agents: roles changed, `DISPATCHABLE_ROLES` excludes them. | FIXED |
| K5 | High | autopilot | "Run alone until the mod is ready": added per-project Autopilot permissions (approve spec, generate, build, server smoke) set only by the user; Autopilot crosses those gates and stops for questions, exhausted repairs, budget, and the client. | FIXED |
| K6 | Low | ui | Policy checkboxes appeared to reset while a job ran: busy guidance omitted the policy. | FIXED |
| K7 | Med | plan | Replanning on approval dropped user-added tasks. Replan now touches only planner-owned tasks. | FIXED |
| K8 | Low | ui | Worker log could not be closed; no live output while running. Toggle + stream-json live summary. | FIXED |

## Host run 12 — 2026-10-28 · RTQ · Windows · art pipeline on `ovis_moon` (`claude-feature/v1-tool-sets`)

- Sprites task: 11/11 icons painted and installed (browser cache hid them at first → cache-busted URLs).
- Retint (first version) overwrote designer icons and painted the worn armor as a solid box → retint now touches layers only; layers painted as shaded cube nets with an open visor; `Restore designer icons`; WinError 267 on `:` in preview dir names fixed.
- ARMOR designer task with the player template + mandatory worn render: run `DONE` ($1.69, 3 min 22). **Owner: "way better"**; feedback: outlines too dark/bold → brief changed to soft gradient edges, no black outlines, shared edge colour between adjacent faces.
- Expired build approval left the Now panel stuck → expired approvals are never offered; UI marks them EXPIRED.
- Items grouped by material set (set-level actions once; a helmet-only set has the same actions).

## Not yet tested

- MCP server **as connected by Claude Code** (only the hand-driven stdio run in Round 3; needs a restart after A1).
- Loading of the `investigator`, `release` and `world-builder` subagents after A4 (fresh session).
- `diagnose` against real failing Gradle logs.
- UI rendered in a browser (only the API was exercised).
