# Handoff: smoke-test PRs #296 + #297 on the owner's normal home PC (2026-11-03)

You are on the owner's **home PC** (Windows, RTX 3050 4 GB, consumer Microsoft
Defender, no endpoint scanner). The work changed startup, model loading, audio
capture and the tray. It was measured and tuned on a **managed work laptop with
Microsoft Defender for Endpoint**. Your job is to confirm that **nothing got
worse on a normal machine**, and that the work-laptop-only paths stay off here.
**Measure and report; don't fix.** If something regresses, diagnose it and
write it up. The work-laptop session merges the PRs after your report.

Read `CLAUDE.md` first (no Claude trailers in commits/PRs; Conventional
Commits). Work on branch **`perf/finding-c`**, which contains both PRs.

## What changed (read these, don't re-derive)

- PR **#296** `perf/slimming` → `main`: https://github.com/JohnJohn4/dictatem/pull/296
- PR **#297** `perf/finding-c` → `perf/slimming`: https://github.com/JohnJohn4/dictatem/pull/297
- Full measurement log, hypotheses and dead ends:
  `docs/agents/handoffs/2026-11-02-slimming-work-laptop.md`. Its "Why this
  machine" section has this PC's **v0.7.0 baseline**: cold first launch ~5 s to
  tray, 3.7 s model load, 1.3 s first transcription.
- Decisions: `docs/adr/0029-engine-prewarm-in-a-child-process.md` (prewarm at
  install and launch, resident engine, PySide6 import-hook patch).

## Expected on a normal PC (what "no regression" means)

| Check | Expect here |
|---|---|
| Installer "Preparing the speech engine…" | `Speech engine ready (N s)`, **a few seconds** |
| `~/.dictatem/.slow_engine_load` | **absent** (only written when a prewarm takes ≥ 10 s) |
| `Engine kept resident…` log line | **absent** (`resident_engine = "auto"` + no marker) |
| Idle daemon RSS (no model loaded) | ~100 MB (the work laptop with resident engine: 325 MB) |
| `Startup timing` | `hw probe` ≲ 1–2 s; total no worse than ~5 s to tray |
| Probe log | `CUDA device detected (via nvml)` |
| `Engine prewarm finished in Xs` (launch) | a few seconds at most |
| First dictation after launch | load ≈ 3–4 s, 1st transcribe ≈ 1 s (no worse than baseline) |
| `Hotkey KEY_DOWN … handled in Xms` | well under 1 s (built-in mic open time varies by device) |
| Tray | no **Preload model**, no **Start/Stop recording**; **Unload model** present; **Microphone ▸** present |

## Protocol (record every number)

**Never inject the hotkey or paste unattended.** The owner dictates; you read
`%APPDATA%\dictatem\logs\daemon.log`.

1. **Upgrade path (what users get).** With v0.7.0 installed, install the
   branch through the real installer. The branch's `install.ps1` still pins
   the v0.7.0 tarball, so substitute the immutable SHA. Use `irm | iex`; don't
   run the file with `-File` under PowerShell 5.1:
   ```powershell
   git fetch origin; $sha = git rev-parse origin/perf/finding-c
   $s = irm "https://raw.githubusercontent.com/JohnJohn4/dictatem/$sha/install.ps1"
   $s = $s -replace 'refs/tags/v0\.7\.0\.tar\.gz', "$sha.tar.gz"
   $t0 = Get-Date; $s | iex; "install {0:N0}s" -f ((Get-Date)-$t0).TotalSeconds
   ```
   Record: install time, `Speech engine ready (N s)`, env size
   (`"{0:N0} MB" -f ((gci "$env:APPDATA\uv\tools\dictatem" -Recurse -File | measure Length -Sum).Sum/1MB)`;
   expect ~2,490 MB vs v0.7.0's ~2,930 MB). Check the PySide6 → Essentials
   migration left Qt working (the tray appears). Then the launch log:
   `Startup timing`, probe line, `Engine prewarm finished`, marker absent,
   no resident line, RSS.
2. **Dictation (owner).** Two sentences into Notepad. Record `Model load
   breakdown` (now includes `resolve`/`construct`), `Model loaded in`, both
   `Transcribe call took`, and the `Hotkey …` lines. Ask how the pill felt.
3. **Tray.** The owner right-clicks: confirm the item list above. Open
   **Microphone**: "System default" ticked plus the real inputs (full names, no
   "Microsoft Sound Mapper"). If a USB mic or headset is available: plug it
   in, dictate (is it used?), pick it in the menu, unplug it (menu hides it and
   ticks System default; the log shows `…is not connected; using the system
   default`), replug it (ticked again). Ask the owner whether the taskbar mic
   indicator appears **only while recording**.
4. **Unload model.** Tray → Unload model; `nvidia-smi` shows the VRAM freed.
   The next dictation reloads it.
5. **Offline.** Relaunch dictatem with outbound HTTP blocked, for that
   process only: `$env:HTTP_PROXY=$env:HTTPS_PROXY=$env:ALL_PROXY='http://127.0.0.1:9'; $env:NO_PROXY='localhost,127.0.0.1'; Start-Process dictatem`
   after stopping it. The owner dictates. It must work with **no**
   `HTTP Request` line in the log. Relaunch normally afterwards.
6. **Optional: true cold install.** `uv tool uninstall dictatem`,
   `$env:UV_LINK_MODE='copy'`, re-run step 1. Expect it to stay quick and no
   marker to be written here.
7. **Optional: test suite.** `uv sync --extra runtime; uv run pytest -q`
   (expect `2089 passed, 32 skipped`); `uv run ruff check .`.

Write results into a new "Home PC smoke test" section at the end of
`docs/agents/handoffs/2026-11-02-slimming-work-laptop.md` (a table like the
one above, before/after), commit on `perf/finding-c`, and **push only when the
owner says so**. If everything passes, say so plainly. The work-laptop session
then merges.

## Gotchas learned on the work laptop

- Installing from a local checkout (`uv tool install "dictatem[...] @ file:///…"`)
  **reuses a cached build** of the same version. Add `--reinstall-package
  dictatem --refresh-package dictatem`. The SHA-tarball URL above avoids this.
- A daemon started with `Start-Process` from an agent shell **dies when the
  agent session ends**. To make it outlive the session, launch via
  `Invoke-CimMethod Win32_Process Create` (that inherits the user env, not
  your shell env, so use `Start-Process` for the proxy test).
- `py-spy` (via `uvx py-spy`) must target the **child** interpreter
  (`uv\python\cpython-…\pythonw.exe`), not the tool venv's
  `Scripts\pythonw.exe` redirector. Don't time anything with `--native`: it
  distorts timings 10–15×.
- In Bash, `cat >> file` without a heredoc waits on stdin and hangs; Python
  heredocs with `\n` inside f-strings can get mangled. Prefer the Write tool.
- `gh` was not installed on the work laptop. PRs were opened through the API
  with the existing git credential.

## After this: merging and shipping (work-laptop session)

1. Merge **#296** first, then **#297** (GitHub retargets #297 to `main` when
   `perf/slimming` is merged and deleted; check it did).
2. **Merging alone does not reach users.** The tray's **Check for updates…**
   compares the installed version with the **latest GitHub release tag** and
   re-runs *that tag's* `install.ps1` (`src/dictatem/upgrade/core.py`). Cut a
   release: bump `version` in `pyproject.toml`, the pinned tarball tag in
   `install.ps1` (`$source = …/refs/tags/vX.Y.Z.tar.gz`), and the README
   one-liner; tag and publish a GitHub release. Existing v0.7.0 installs then
   upgrade via the tray, including the PySide6 migration and the install-time
   prewarm.

## Suggested skills

- `mattpocock-skills:diagnosing-bugs`: if any check regresses on this PC.
- `mattpocock-skills:code-review`: optional review of `main..perf/finding-c`
  before merging.
- `mattpocock-skills:pr`: if PR #296/#297 bodies need the home-PC evidence
  added.
