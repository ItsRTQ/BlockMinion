# Verification evidence — crystal_example

## Current content (regenerated 2026-10-27, v1 tool/armor sets + food)

Items `sky_crystal`, `lunar_gem`; blocks `crystal_stone`, `crystal_ore`; creative tab "Crystal Example".
Recipes: `crystal_stone` (shaped, 9 sky_crystal), `sky_crystal_from_stone` (shapeless, 1 stone → 9 crystal),
`lunar_gem` (shapeless, sky_crystal + minecraft:ender_pearl), `sky_crystal_smelting` (crystal_ore → sky_crystal, 0.7 xp).
Drop: `crystal_ore` → 1–2 `sky_crystal`, Fortune, Silk Touch returns the ore.
Mob: `crystal_critter` (passive, GeckoLib, placeholder 6-bone quadruped, idle + walk, spawn egg, drops sky_crystal). GeckoLib 4.7.3.
Material `crystal` (diamond-like numbers, from sky_crystal): sword, pickaxe, axe, shovel, hoe, helmet, chestplate, leggings, boots with standard recipes and placeholder armor layers. Food `crystal_berry` (nutrition 4, saturation 0.6, night vision 20 s).

| Level | Evidence |
|---|---|
| BUILD_PASS | CI: `fabric-build` job compiles this directory on a clean JDK 25 runner on every push. |
| CLIENT_BOOT_PASS | pending (owner) |
| SERVER_BOOT_PASS | pending (`craftctl server-smoke` on a controller project with the same spec) |
| CONTENT_VERIFIED | pending: tab visible with 5 entries (incl. spawn egg); critter spawns from the egg, wanders, legs animate while walking, dies and drops sky crystal; recipes appear in the recipe book after picking up a sky crystal; crafting works; mining crystal_ore drops sky crystal(s); Silk Touch drops the ore. |

## History (earlier revisions of this example)

Recorded by the project owner (RTQ) on **2026-10-20**, Windows, JDK 25. Source built was `dev @ aa8538d`
(generator output identical to this directory except `loom_version`, then `1.18-SNAPSHOT`, which resolved to 1.18.4 and is now pinned).

| Level | Evidence |
|---|---|
| BUILD_PASS | `gradlew.bat build` → `BUILD SUCCESSFUL in 1m 4s`, `Fabric Loom: 1.18.4`. JAR `build/libs/crystal_example-1.0.0.jar` SHA-256 `6de89b8cebde3bac596c504489d07fad9c6c858eaffa97e99414f24cf4b857f1` (SHA-1 `8469487abcb98fa061fff77df19027a8238cb9dc`). Manifest: Loom 1.18.4, Gradle 9.7.1, Loader 0.19.5, namespace intermediary. JAR contents inspected: `ModMain.class` remapped (`class_1792`, `class_4970`), `data/crystal_example/loot_table/blocks/crystal_stone.json` present. |
| CLIENT_BOOT_PASS | `run/logs/latest.log`: `[FabricLoader] Loading 56 mods: - crystal_example 1.0.0`; `Reloading ResourceManager: vanilla, fabric, crystal_example, …`. Only warnings are vanilla (`goat_horn` sounds, `rendertype_entity_translucent_emissive` sampler). |
| SERVER_BOOT_PASS | `gradlew.bat runServer`: stopped on `eula.txt`, accepted, re-run. Server log: `Env=SERVER`, `Loading Minecraft 1.21.1 with Fabric Loader 0.19.5`, `Loading 44 mods: - crystal_example 1.0.0`, `Starting minecraft server version 1.21.1`, `Done (4.354s)! For help, type "help"`. No warnings or errors. |
| CONTENT_VERIFIED | Sky Crystal and Lunar Gem in the **Ingredients** creative tab; Crystal Stone in **Building Blocks**; block placeable; in survival the block breaks, drops itself and can be re-placed (validates the 1.21 `loot_table/` folder fix). |

Known harmless build warning: `duplicate input class net/fabricmc/fabric/mixin/tag/package-info` (Fabric API `convention-tags-v2` vs `tag-api-v1` packaging).

Not yet verified: multiplayer join, dedicated-server content behaviour, any mechanic beyond static item/block registration.

## Sapphire item — R2 proof (added by the Claude Code `coder` subagent)

Source: `claude-feature/r2-smoke @ 2207685`. Recorded by RTQ on **2026-10-20**, Windows, JDK 25, after the
orchestrating session verified the build artifact.

| Level | Evidence |
|---|---|
| BUILD_PASS | `./gradlew build --no-daemon --console=plain` → exit 0, `BUILD SUCCESSFUL in 13s`, `Fabric Loom: 1.18.4`. JAR `build/libs/crystal_example-1.0.0.jar` SHA-256 `e8460b2e550e89563c79141fba6f22d6a1bf768bd39b207ef11495644f8d93c4`; contains `models/item/sapphire.json`, `textures/item/sapphire.png` (16×16 RGBA), updated `lang/en_us.json`, `ModMain.class`. Observed by the session, re-checked independently of the subagent's report. |
| CLIENT_BOOT_PASS | `gradlew runClient` by RTQ. `run/logs/latest.log`: `Loading Minecraft 1.21.1 with Fabric Loader 0.19.5`, `Loading 56 mods: - crystal_example 1.0.0`; 0 errors; the only warnings are the known vanilla ones (`goat_horn` sounds, `rendertype_entity_translucent_emissive` sampler). No missing-texture/model entries for `sapphire`. |
| CONTENT_VERIFIED | RTQ, creative test world: Sky Crystal, Lunar Gem **and** Sapphire all present in the **Ingredients** tab; sapphire renders as the flat blue placeholder and its hover name reads "sapphire" (lang entry resolved). |

Not yet verified for sapphire: dedicated-server boot with this build, multiplayer. The texture is a deliberate
placeholder, not final art.
