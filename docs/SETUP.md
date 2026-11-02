# Setup — from a clean machine to a verified mod

This is the document v1 criterion 8 is tested against: a person who is not the author follows **only** this
page on a clean Windows 11 machine (or a fresh user account) and reaches a built, verified mod. Every step
says what to type and what you should see. If something here is wrong, that is a bug: note the step and tell us.

Linux and macOS work the same way (the CI runs the Linux path on every push); commands differ only where marked.

## 0. What you need and why

| Tool | Needed for | Version |
|---|---|---|
| **Python** | the controller itself (`craftctl`) | 3.11 or 3.12 |
| **Git** | getting the code and updates | any recent |
| **JDK 25** | building mods (Gradle 9.7.1 runs on it; mods compile for Java 21) | 25 |
| **Claude Code** | every agent run (interpreter, coder, designer, debugger). Uses **your** Claude login; no API key | current |
| **Node.js** | the designer worker's Blockbench MCP (vendored, zero dependencies, runs on Node) | 22 LTS |
| Blockbench | optional: open/edit the `.bbmodel` files the designer makes (install the *GeckoLib Animation Utils* plugin inside Blockbench) | current |
| Minecraft | **not** needed to generate or build. `run-client` launches an isolated dev client through Gradle; a Minecraft account is only needed if you want to log in there | — |

Nothing is downloaded by `craftctl` itself except what Gradle fetches for a project (Minecraft, Fabric, GeckoLib, from their official Maven repositories, hash-checked by Gradle) and the Gradle distribution (pinned SHA-256 in `gradle-wrapper.properties`).

## 1. Install the tools (Windows 11)

1. **Python 3.12** from https://www.python.org/downloads/windows/ (the installer, not the Microsoft Store). Tick *Add python.exe to PATH*.
   Then disable the Store aliases, or they will shadow every virtualenv: Settings → Apps → Advanced app settings → *App execution aliases* → turn off `python.exe` and `python3.exe`.
2. **Git** from https://git-scm.com/download/win (defaults are fine; it installs Git Bash, which this guide uses for commands).
3. **JDK 25** from https://adoptium.net (Temurin 25, MSI). Let the installer set `JAVA_HOME`. Check in a new terminal: `java -version` → `openjdk version "25…"`.
4. **Node.js 22 LTS** from https://nodejs.org (MSI). Check: `node --version` → `v22…`. (Compare the installer's SHA-256 with the site's `SHASUMS256.txt` if you want to verify it.)
5. **Claude Code** (native Windows): in PowerShell `irm https://claude.ai/install.ps1 | iex`, then open a new terminal and run `claude` once to log in. Check: `claude --version`.
   If `claude` is not on your PATH, `craftctl` can be pointed at it: `set CRAFTCTL_CLAUDE_BIN=C:\Users\<you>\.local\bin\claude.exe`.
6. Optional: **Blockbench** from https://www.blockbench.net, then File → Plugins → install *GeckoLib Animation Utils*.

Linux/macOS: the same tools from your package manager (`python3.12`, `git`, Temurin 25, `node` 22) and Claude Code via `curl -fsSL https://claude.ai/install.sh | bash`.

## 2. Install craftctl

In **Git Bash** (Windows) or a terminal (Linux/macOS):

```bash
git clone https://github.com/ItsRTQ/Minecraft-Modding-Minion.git
cd Minecraft-Modding-Minion
python -m venv .venv
source .venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
python -m pip install -e .
python -m mod_orchestra.cli doctor
```

`doctor` prints JSON. What you want to see:

- `"java": {"compatible": true, …}` — JDK 25 found.
- `"wrapper": {"ok": true}` — the shipped Gradle wrapper matches its recorded hashes.
- `"node": {"executable": "…node…"}` and `"claude_code": {"executable": "…claude…"}` — both found.
- `"schema": {"version": N, "current": N}` — the local database is created and up to date.

If `which python` points at `…/WindowsApps/python.exe` even with `(.venv)` in the prompt, the Store aliases are still on (step 1.1). Until you fix that, use `python -m mod_orchestra.cli …` everywhere this guide says `craftctl` — they are the same program.

**Where things live:** everything the controller creates goes under `~/.minecraft-mod-orchestra/` (`state.sqlite`, `projects/<mod_id>/`, `logs/`). The repo stays clean. To start over, delete that folder.

## 3. First mod, from the UI (recommended)

```bash
craftctl ui
```

It prints a `http://127.0.0.1:8765/#<token>` link; open it in your browser (the token is the only way in; the server listens on localhost only).

1. **New mod** → name, mod id (lowercase), Java package (`com.yourname.yourmod`) and the idea in plain words, e.g.
   *"a sky crystal ore that drops crystals, a crystal block made of 9 crystals, a full crystal tool and armor set, a crystal berry that gives night vision, and a small bird-like passive mob; creative tab 'Sky'"*.
2. In **Now**, open *Autopilot permissions* and press **Allow everything up to the client**. Then **Autopilot** with a budget (say $5). It runs the interpreter, approves the spec if there are no questions, generates, runs the designer for the mob, builds, repairs if needed, and boots a dedicated server. It stops when it needs you.
   - If the interpreter asks questions, answer them in **Now** and press Autopilot again.
   - Each agent run uses your Claude Code session; typical costs are shown next to every run.
3. When Now says **ready for your eyes**: **Launch game client**. Minecraft opens with only your mod. Look at the creative tab, craft something, spawn the mob with its egg, equip the armor.
4. Back in the UI → **Verification** → record what you saw: `CLIENT_BOOT_PASS` (the game loaded the mod) and `CONTENT_VERIFIED` (the behaviour you checked). The project becomes **GAME_VERIFIED**.

Where to find things afterwards: the mod's JAR is `~/.minecraft-mod-orchestra/projects/<mod_id>/build/libs/<mod_id>-1.0.0.jar`; the editable Blockbench models are in `…/projects/<mod_id>/models/`.

## 4. The same, from the terminal

```bash
craftctl new --name "Sky Crystals" --id sky_crystals --package com.yourname.skycrystals --idea "items: sky crystal; blocks: crystal ore; mobs: sky critter; tab: Sky"
craftctl autopilot sky_crystals --allow all
craftctl orchestrate sky_crystals --max-cost-usd 5
craftctl run-client sky_crystals
craftctl evidence sky_crystals CLIENT_BOOT_PASS --note "Loading N mods: - sky_crystals 1.0.0"
craftctl evidence sky_crystals CONTENT_VERIFIED --note "what you saw"
craftctl status sky_crystals
```

The `items: …; blocks: …; mobs: …; tab: …` grammar skips the interpreter; free text goes through it. Before generation you can shape the spec with `craftctl add-recipe / add-drop / add-material / add-food / add-mob / set-tab`; after generation the same things are added through the UI (a coder registers them).

## 5. Keeping up to date

```bash
cd Minecraft-Modding-Minion && git checkout prod && git pull
python -m pip install -e .
```

`prod` holds tagged releases (`vX.Y.Z-prealpha`); `dev` is integration. The local database migrates itself on the next command (a backup `state.sqlite.bak-v<N>` is written first). Existing projects keep working; the UI tells you if a project needs a rebuild after an update.

## 6. Things that went wrong for us (so they don't for you)

- **`(.venv)` in the prompt but commands use the Store Python** → step 1.1 (aliases). Symptom: `ModuleNotFoundError: mod_orchestra`.
- **`Embedded Gradle wrapper gradlew hash … != recorded`** → a checkout converted `gradlew` to CRLF. Run `git add --renormalize . && git checkout -- .` once.
- **First build takes minutes** → Gradle downloads Minecraft, Fabric and GeckoLib once per machine; later builds take seconds.
- **`claude` not found when dispatching** → step 1.5, or set `CRAFTCTL_CLAUDE_BIN`.
- **Designer run fails with "node not found"** → step 1.4; `doctor` shows it under `node`.
- **Port 8765 busy** → `craftctl ui --port 8766`.
- **Something looks stuck in the UI** → every long action shows in **Now** with a spinner; the **Activity** tab shows each worker's live log. If a build or smoke failed, Now offers the repair; if an approval expired, Now re-offers the request.
- **Deleting a test project** → header → *Delete project* (type DELETE). It removes the folder too if you leave the box ticked.

## 7. Agent runtime

v1 runs agents through **Claude Code** only (`claude -p`, headless; your Claude login or `ANTHROPIC_API_KEY`), on Windows, Linux or macOS — the controller must be able to start `claude` as a local process, so Claude Code inside WSL does not work with a Windows controller. Everything else (controller, MCP servers, generator, builds, UI) is runtime-agnostic; other agent CLIs can be added behind the `AgentProvider` interface (`src/mod_orchestra/provider.py`) — planned for v2.

## 8. Security model in one paragraph

Agents (Claude Code workers) only ever edit files inside the project's workspace and can call a small set of read/validate tools; they cannot approve a spec, grant a build, run the game, or record evidence — those are yours, from the UI or CLI, or pre-authorised per project in *Autopilot permissions*. Builds run through a process broker with a minimal environment and timeouts; the dedicated-server smoke runs in the project's isolated `run/` folder. Nothing phones home; the UI is localhost-only with a per-process token. Details: `docs/SECURITY.md`, `docs/ARCHITECTURE.md`.
