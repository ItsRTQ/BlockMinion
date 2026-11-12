# Contributing

Contributions should advance an evidence-based, local-first Minecraft Java modding workflow. Keep changes small and scoped to the current milestone in `docs/ROADMAP.md`.

1. Open a discussion/issue for new providers, dependency changes, security-sensitive actions or version migrations. Include exact Minecraft, Fabric, Java and GeckoLib versions where relevant.
2. Add tests for new deterministic controller or parsing features. Run `python -m unittest discover -s tests -v` before opening a pull request.
3. Never mark a generated source tree as game-tested without an actual Minecraft instance and reproducible evidence. Include build logs, client/dedicated server checks and screenshots when appropriate.
4. Do not bundle proprietary Minecraft game assets or external MCP/plugin source without license audit. Keep third-party providers optional by default.
5. Do not add unapproved auto-installation, unrestricted file writes, shell execution from MCP, cloud uploads or publishing actions. See `docs/SECURITY.md`.
6. Keep the root CLAUDE instructions and agent skill responsibilities consistent with implemented tools. Agent prompts are not a security mechanism.

Please include a summary, affected files, checks run, failure cases and any user-visible security/compatibility changes in your pull request.

## License of contributions

By submitting a contribution you agree that it is licensed under the project's `LICENSE` (section 6): it stays yours, it is
licensed to the project and to every recipient under those terms, and the copyright holder may license it under other terms
as part of the software. If you cannot agree to that for a particular contribution, say so when you submit it, and it will
not be merged under those terms. Do not submit code you do not have the right to license this way, and do not bundle
third-party code without its license and a line in `NOTICE.md`.
