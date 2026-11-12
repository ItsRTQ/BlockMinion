# Gradle wrapper provenance

These are the only third-party binaries shipped by BlockMinion. They are copied
verbatim into every generated workspace so `craftctl build` can run without a system Gradle.

| File | SHA-256 | Source |
|---|---|---|
| `gradle/wrapper/gradle-wrapper.jar` | `7a9ce74cff467ca1bf60a4fcd9f05185acceda4d0f382434d393e17864262c5d` | Gradle 9.7.1 official wrapper. Matches the `wrapper:` checksum published at https://github.com/gradle/gradle-distributions/releases/tag/v9.7.1. Taken from FabricMC/fabric-example-mod branch `1.21.1` @ `684b581` (byte-identical). |
| `gradlew` | `a5a5c199ba02189ae8c46a334223371a20599d9c298ef65e7540ede4a3f72d59` | Same template commit. |
| `gradlew.bat` | `d539676c48b596afda64c963ec8f7ee56c7b3fe7e3b81d1dbe2d1a1e3dd9e9f8` | Same template commit. |

License: Apache-2.0 (`SPDX-License-Identifier: Apache-2.0` in the scripts and in the jar's `META-INF/MANIFEST.MF`; full text in the jar's `META-INF/LICENSE`).

The generated `gradle/wrapper/gradle-wrapper.properties` pins
`distributionUrl=gradle-9.7.1-bin.zip` and
`distributionSha256Sum=acd53f1edaf02f1a8ff99879f8a34b302661a057d9b063ae9e35b552f804d20a`
(the `bin:` checksum from the same release page), so the wrapper refuses a tampered or
corrupted distribution download.

`craftctl doctor` recomputes the jar hash and reports `wrapper.ok=false` if the embedded
binary ever drifts from this record. To bump Gradle: update `config.PROFILE["gradle"]`,
`GRADLE_DIST_SHA256`, replace the three files from the matching official release, and
update this table.
