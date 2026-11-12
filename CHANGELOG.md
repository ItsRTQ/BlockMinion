# Changelog

## v0.14.0-prealpha — 2026-11-12

The first release as **BlockMinion**, under the new license. Everything below landed on `dev` since `v0.13.4-prealpha`.

### Models and art
- Mobs: **Resize** (scale + hitbox, one attribute), **Modify this model** (edits checked against a snapshot; shape lock), **Use your own
  model** and **Install my Blockbench edits**; every version keeps the whole model.
- **Give it its own art**: the coder lists what it borrows from vanilla, the designer paints it, the coder wires it (`art_needed`).
- **Make it 3D** for items, tools, weapons, food, blocks and projectiles. Items are held by a computed pose (**Hold**: kind, front, size,
  with in-hand previews before any build; per-style fine tuning), the inventory keeps the 2D icon; blocks render through a block entity;
  projectiles turn like arrows. Z-fighting is nudged apart on install. Open in Blockbench for all of them.
### Animation
- **Animate** on items, projectiles, mobs and blocks: what it does (designer) and when it plays (coder), shape and texture locked.
- The **animation contract**: `Item3DBase`, `Item3DActions.event`, declared `animation_events`; GeckoLib and the 3D support ship with
  every project; actions on a declared GeoItem need no wiring. The player's body through Player Animation Library (bundled jar-in-jar).
- **A limitation becomes work**: a moment the code lacks sends the coder first; an agent that hits a limitation reports `needs` and is
  brought back after; **Ask** turns a free-text request into a plan the controller applies.
### Map
- One change request across several cards (**Select cards** mode, `craftctl change --cards`).
### Licensing and name
- The project is now **BlockMinion** (CLI still `craftctl`; repository `ItsRTQ/BlockMinion`).

- **Name:** the project is now **BlockMinion** (formerly "Minecraft Mod Orchestra"). The CLI keeps its name, `craftctl`,
  and existing installations, projects and commands are unchanged. The repository may be renamed by its owner; GitHub
  redirects the old URL.
- **License:** from this release onward the software is distributed under the **BlockMinion Source-Available License 1.0**
  (`LICENSE`): free to use for anything, free to modify, fork and redistribute without charge, free to use commercially to
  make and sell Minecraft mods; the software itself (or a renamed or lightly changed copy of it) may not be sold, and the
  official name may not be used to impersonate the project. It is source-available, **not** OSI Open Source.
- **MIT permissions remain:** everything published before this change, including every tag up to `v0.13.4-prealpha`, was
  released under the MIT License, kept verbatim in `legal/MIT.txt`. Those permissions are not and cannot be revoked:
  anyone who received that code under MIT keeps all MIT rights over it. The new license governs the software as distributed
  from this change onward.
- **New files:** `LICENSE` (new terms), `legal/MIT.txt` (the previous license, unchanged), `NOTICE.md` (authorship,
  earlier MIT releases, third-party material and the licenses of what generated projects download), `TRADEMARKS.md`
  (branding rules for forks and services), a licensing section and FAQ in `README.md`, a contribution-license rule in
  `CONTRIBUTING.md`.
- **Metadata:** `pyproject.toml` and the vendored server's `package.json` now point at `LICENSE` instead of declaring MIT.
- No functional change: the software behaves exactly as before.

Earlier history: see the Git tags (`v0.1.0-prealpha` … `v0.13.4-prealpha`) and `docs/`.
