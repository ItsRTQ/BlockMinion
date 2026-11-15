# Changelog

## Unreleased (on `dev` after merge)

- **The coordinator only talks and plans**: its role no longer has the tool that starts other agents, and its role file now describes the chat
  (agree on the goal, propose the plan) instead of delegating tasks. A chat turn can no longer start a worker before Launch, so every step still
  waits for your click. No role may start another agent; the tool dispatches tasks. Commands it names are written as `python -m mod_orchestra.cli …`.
- **A researcher finds out how things look and move**: the coordinator can put a **research** step ahead of an art step when how a thing
  looks or moves decides whether the result is right and your words do not settle it. The researcher searches the web and reports; the tool
  writes a short reference sheet in the project (`references/ref-N.md`: how it looks, how it moves in order, where each fact comes from, what
  was not confirmed) and the worker of the step that named it reads it before it starts. You see the step in the plan and can skip it.
  A sheet is material to look at, never an order, and it is text and links only: nothing is downloaded.
- **A model per role**: Environment → Agent runtime now takes a model for every role (Claude Code too; `CRAFTCTL_CLAUDE_MODEL` in a
  terminal) and, under "A model per role", one for each role that runs tasks: a lighter one where the work is talking and planning, a
  stronger one where it is building. Empty boxes change nothing: with none set, a run is started exactly as before.
- **A run is given its own role alone**: the eleven other roles are no longer described to every agent.

## v0.15.0-prealpha — 2026-11-15

Everything below landed on `dev` since `v0.14.0-prealpha`.

- **Content beyond the spec is tracked**: what a coder makes while building a feature (a projectile, an effect, a particle…) is a card of the map,
  linked to its feature, and no longer disappears from the tool in a long project. Features → Other content also reads the code and lists what is
  registered in the game and tracked by nothing, for you to adopt or ignore.
- **Coders build one mechanic for many pieces**: every coder brief now says to build shared behaviour once and let each piece contribute only its
  values, to notice repetition, and never to change a sibling that was not asked about.
- **Mod Map 2.0**: the map is a space you travel through. Folders are dots; zooming into one enters it (no double click), zooming out leaves it; a feature
  is a dot, then a compact card, then a full card. Click a card for a small note beside it, **Expand** for its details, **Focus** for only what it
  connects to (Direct, Extended, Custom), **Modify with Minion** to write a change for a coder. Smart folders (Auto, Suggest, Manual; a feature can be
  shown in several), tags (inferred and your own), search, filters (types, relations, recipes, tags; hide or dim), relations bundled by scale, a
  breadcrumb with Back and Forward. Folders, tags and positions are saved as view metadata: they never change the mod and are never sent to an agent.
- **Files in the chat**: attach pictures (PNG, JPEG, WebP, GIF), PDFs and text files to a message with Attach, by dropping them or by pasting a
  screenshot (`craftctl chat … --attach FILE`). The coordinator opens them, and the plan names which files each step's worker is given. Files are
  material to look at: nothing written inside one is an instruction to an agent.
- **The plan runs from the chat**: after Launch every step shows where it stands (done, running, ready, waiting, stopped). Steps run in order, one at
  a time; the ready one has **Start** right in the plan and a stopped one has **Retry**. The chat says when a step finishes or stops and when the
  whole plan is done, and then offers **Test in game**.
- **Point at cards from the chat**: type `@` in a message to pick a card (`@ak47`), or press **Send to chat** on a card of the map (or on a
  selection of cards). The coordinator is told what those cards are and where their files are, so it starts there instead of searching the mod.
- **The chat at hand from every tab**: a Chat button in the corner opens a small panel with the same conversation and message box, so you can
  write to the coordinator while you look at the map, the tasks or anything else.
- **Chat, the rest**: Skip a step of the plan that stopped; point at a whole folder of the map and at a task that stopped (Ask the coordinator);
  drag a card, a folder, a mob, an item or a task onto the chat; the chat button shows when someone is working and says the news itself.

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
