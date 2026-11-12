# NOTICE

**BlockMinion** (formerly distributed as "Minecraft Mod Orchestra" in the repository `ItsRTQ/Minecraft-Modding-Minion`, now `ItsRTQ/BlockMinion`).

Copyright (c) 2026 ItsRTQ (HCoding). Licensed under the BlockMinion Source-Available License (see `LICENSE`).
This file must be kept with every copy and Derivative Version.

## Authorship

- The project was created and is maintained by **ItsRTQ**, who also commits as **HCoding**. Both names in the Git
  history are the same person and the same copyright holder.
- A large part of the code base was written by AI coding assistants (commits authored as "Claude") under the direction,
  review and testing of ItsRTQ. The copyright status of AI-assisted output varies by jurisdiction; the project treats
  that material as part of the Software it distributes and claims no more than the law allows for it.
- Contributions from others are licensed under section 6 of `LICENSE` and are credited in the Git history. No
  contributor other than ItsRTQ has submitted code as of the adoption of this License.

## Earlier MIT releases

Everything published before the commit that introduced the current `LICENSE`, including the tagged releases
`v0.1.0-prealpha` through `v0.13.4-prealpha`, was released under the MIT License, whose text is kept verbatim in
`legal/MIT.txt`. Those permissions are not revoked (see `LICENSE` section 11).

## Third-party material shipped in this repository

| Material | Where | License | Notes |
|---|---|---|---|
| Gradle wrapper (`gradle-wrapper.jar`, `gradlew`, `gradlew.bat`) | `src/mod_orchestra/resources/gradle-wrapper/` and every generated project | Apache License 2.0 | The only third-party binary shipped. Provenance and checksums in `resources/gradle-wrapper/PROVENANCE.md`; the Apache notice and text travel inside the jar (`META-INF/LICENSE`). |
| Build file templates derived from `FabricMC/fabric-example-mod` | the generator in `src/mod_orchestra/fabric.py` | CC0 1.0 | No attribution required; noted for completeness. |
| `blockbench-mcp-safe` (headless Blockbench/GeckoLib server) | `tools/blockbench-mcp-safe/` and its identical copy under `src/mod_orchestra/resources/` | BlockMinion Source-Available License (previously MIT) | Independently authored for this project. It does **not** contain source from `jasonjgardner/blockbench-mcp-plugin` (GPL-3.0), which is only used as a behavioural oracle in CI and is never bundled or executed. |
| Player rig (`resources/blockbench/player_rig/`) | built by `scripts/build_rig.mjs` | BlockMinion Source-Available License | Bone names and pivots follow the publicly documented layout of Player Animation Library; facts, not copied code. |

## Software that generated projects download (not shipped here)

Projects created with BlockMinion download their own dependencies through Gradle. They are not part of BlockMinion and keep their
own licenses, which bind the mod's author:

- Fabric Loader and Fabric API (FabricMC): Apache License 2.0.
- GeckoLib (`bernie-g/geckolib`): MIT License.
- Player Animation Library (`PlayerAnimationLibrary`): MIT License. It is bundled *inside the generated mod's jar* (jar-in-jar)
  when a project uses player animations, so its license notice is carried by that mod.
- Minecraft itself is the property of Mojang Studios / Microsoft and is governed by the Minecraft EULA. BlockMinion never
  ships Minecraft, its assets or its code.

Generated mods are **Independent Content** (see `LICENSE` section 1): they belong to their author, whose `fabric.mod.json`
defaults to `"license": "ARR"` until the author chooses otherwise.

## Trademarks

"Minecraft" is a trademark of Mojang Synergies AB / Microsoft. "Fabric" and "Forge"/"NeoForge" belong to their respective
projects. BlockMinion is not affiliated with, endorsed by or sponsored by any of them. See `TRADEMARKS.md` for the
project's own marks.
