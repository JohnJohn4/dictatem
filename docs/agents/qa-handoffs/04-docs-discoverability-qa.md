# QA Handoff — Session 3: Docs & discoverability (#122, #123)

**Device required:** Windows 11 (the auto-open + tray wiring is win32/Qt).
**Build under test:** PR **#153**, branch `feat/discoverability-onboarding-122-123`
· run from a dev clone: `uv run python -m dictatem`.
**Why this is manual:** the first-run Usage Guide auto-open and the tray "Open
config file…" item are Qt/tray behaviour — not machine-verifiable. The pure
marker-gate logic (`onboarding.py`) is already unit-tested (`test_onboarding.py`);
this checklist covers only the wiring.

> Only **#122** and **#123** need QA. #67 (PR #151, README) and #127 (PR #152,
> default `polish` prompt) are docs/bootstrap and merge without QA.

## Prerequisites
- A checkout of the PR branch: `git fetch && git checkout feat/discoverability-onboarding-122-123`, then `uv sync --extra runtime` (or `runtime-gpu`).
- **Stop any already-running Dictatem first** (tray → **Quit**, or `dictatem --uninstall` is overkill — just Quit). The single-instance guard (#92) makes a second instance exit immediately, and an autostarted **installed** daemon (`pythonw.exe`) is invisible to a `python.exe` check — so a dev build launched alongside it will either silently exit (lock held) or you'll get double behaviour. Confirm only the dev build is running.
- No Ollama needed (the `polish` trigger is #127, which needs no QA).

## Checklist (tick on a real Windows box)

### #122 — Usage Guide auto-opens once on first run
- [ ] **Reset to "unseen":** delete `C:\Users\<you>\.dictatem\.usage_guide_seen` if it exists (it won't before this build). Do **not** delete the rest of `~/.dictatem` (keeps your config). → this simulates first run.
- [ ] Launch the dev build (`uv run python -m dictatem`). → **Expect:** within ~2 s the **Usage Guide window auto-opens once**, on its own, scrolled to the top, non-modal (you can click elsewhere). · **Issue:** #122
- [ ] Confirm the marker was written: `C:\Users\<you>\.dictatem\.usage_guide_seen` now **exists**. The daemon log (`%APPDATA%\Dictatem\logs\daemon.log`) shows `First run — auto-opened the Usage Guide`. · **Issue:** #122
- [ ] **Quit** (tray → Quit) and **relaunch** the dev build. → **Expect:** the guide does **NOT** auto-open again; no second "auto-opened" log line. (The tray "How to use Dictatem…" item still opens it on demand.) · **Issue:** #122

### #123 — Config discoverability
- [ ] Right-click the tray icon → **"Open config file…"**. → **Expect:** `~/.dictatem/config.toml` opens in your default editor/app. · **Issue:** #123
- [ ] Tray → **"How to use Dictatem…"** → scroll to the **"Changing your hotkey"** section. → **Expect:** it shows your **live** combo (default **Win+Alt**), names `config.toml` and `[hotkey].modifiers`, lists the vocabulary `win`/`meta`, `alt`, `ctrl`, `shift`, `mouse4`, `mouse5`, `middle`, says use-standalone-or-combined, and that a **restart** applies changes. · **Issue:** #123
- [ ] *(Optional, proves "live")* set `[hotkey].modifiers = ["ctrl", "shift"]` in config, restart Dictatem, reopen the guide → the section now reads **Ctrl+Shift**. Revert when done. · **Issue:** #123

## What to capture
- A screenshot of the auto-opened Usage Guide (first launch) and of the "Changing your hotkey" section.
- The `daemon.log` line `First run — auto-opened the Usage Guide`, and confirmation that the **second** launch produced no such line.
- That `~/.dictatem/.usage_guide_seen` exists after the first run.

## On result
- **PASS** → comment the evidence on **#122** and **#123**, close them, and merge PR **#153**.
- **FAIL** → comment the captured evidence; keep #122/#123 open; note the hypothesis (e.g. guide didn't open, or opened on every launch → marker not written / gate wrong).
