# Changelog

## Unreleased — licensing transition and new name

- **Name:** the project is now **BlockMinion** (formerly "Minecraft Mod Orchestra"). The CLI keeps its name, `craftctl`,
  and existing installations, projects and commands are unchanged. The repository may be renamed by its owner; GitHub
  redirects the old URL.
- **License:** from this change onward the software is distributed under the **BlockMinion Source-Available License 1.0**
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
