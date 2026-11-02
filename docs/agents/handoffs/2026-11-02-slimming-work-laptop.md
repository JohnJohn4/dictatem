# Handoff — slimming & cold-start measurement on the managed work laptop (2026-11-02)

You are on the owner's **managed work laptop** (Windows 11 Enterprise, RTX 500
Ada 4 GB, **Microsoft Defender for Endpoint / `MsSense`**). It is the only
machine we have that reproduces the slow first launch. Your job is
**measurement first**: install the `perf/slimming` branch, collect the numbers
below, run the experiments, and write the results into this file. Do **not**
implement the candidate fixes at the bottom without the owner's go-ahead.

Read `CLAUDE.md` first. Work on branch `perf/slimming` (never `main`). Commit
results to this file on the branch; push only when the owner says so.

## Why this machine

On v0.7.0's first launch here: model load **57.4 s**, first transcription
**~64 s** for 4 s of audio. After an app restart: **2.7 s** load, **0.5 s**
transcription. There was also **~20 s** between config load and autostart in
the log. The owner's home PC (RTX 3050 4 GB, consumer Defender) does **not**
reproduce this: a cold first launch there is ~5 s to tray, 3.7 s model load,
1.3 s first transcription. So the cost is almost certainly MDE scanning each
newly written DLL on first load — and only this machine can measure it.

## What's on the branch (already done, verified on the home PC)

1. **`PySide6` → `PySide6-Essentials`** (`3a19a82`): −448 MB (2943 → 2495 MB
   GPU venv). The meta and Essentials wheels share `PySide6/__init__.py`, so an
   in-place upgrade from v0.7.0 would delete it and kill Qt ("DLL load failed
   while importing QtCore"). `install.ps1`/`install.sh` therefore add
   `--reinstall-package pyside6-essentials` **only** when the old meta's
   `pyside6-<ver>.dist-info` is present. Verified: real v0.7.0 release →
   branch in place → Qt OK; second upgrade skips the reinstall.
2. **Diagnostics** (`b55da04`), no behaviour change. New `daemon.log` lines:
   - `Startup timing: interpreter … | adapters … | imports … | lock … | config …
     | hw probe … | autostart … | qt app … | setup … | overlay+tray … | wiring …
     | total …` — the tray icon exists only after `overlay+tray`.
   - `Model load breakdown: engine import Xs, weights Ys`
   - `Transcribe call took Xs` (the first after a load includes cuBLAS/cuDNN
     lazy-loading).

## Hypotheses to confirm or kill

- **H1 — the hardware probe delays the tray.** On every launch, before the tray
  is created, `_run_daemon` reconciles hardware via `NvidiaHardwareProbe`, which
  does `import ctranslate2` + `get_cuda_device_count()` + NVML. That is the only
  work between config load and autostart, i.e. the ~20 s gap. Expect a large
  `hw probe` on a cold launch.
- **H2 — the 64 s first transcription is cuBLAS/cuDNN being scanned** on lazy
  load (`cublasLt64_12.dll` 638 MB, `cudnn_engines_precompiled64_9.dll` 504 MB…).
  Expect `Transcribe call took` ≫ 1 s on the first call only.
- **H3 — every model load phones Hugging Face.** `WhisperModel("small")` makes
  `GET https://huggingface.co/api/models/Systran/faster-whisper-small/revision/main`
  even when the weights are cached. Behind a corporate proxy this may cost time
  on every first dictation (and it's an outbound call on the local-first story).

## Install the branch

Use an immutable commit SHA in the tarball URL (uv caches by URL; a branch URL
can serve a stale copy). Mirror the real `irm | iex` path — **don't** run the
file with `-File` under Windows PowerShell 5.1: `install.ps1` is UTF-8 without a
BOM and its em-dashes mis-parse that way (pre-existing, `irm | iex` is fine).

```powershell
git fetch origin; $sha = git rev-parse origin/perf/slimming
$s = irm "https://raw.githubusercontent.com/JohnJohn4/dictatem/$sha/install.ps1"
$s = $s -replace 'refs/tags/v0\.7\.0\.tar\.gz', "$sha.tar.gz"
$s | iex
```

Size: `"{0:N0} MB" -f ((Get-ChildItem "$env:APPDATA\uv\tools\dictatem" -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)`
Log: `%APPDATA%\dictatem\logs\daemon.log`.

## Protocol (record every number in Results)

1. **Upgrade path (what users get).** With v0.7.0 still installed, run the
   install above. Record: install wall time, env size, that the installer
   printed nothing alarming, and the `Startup timing` line of the launch it
   triggers. Confirm the tray icon appears and the tray menu opens.
2. **Dictation check — with the owner at the keyboard.** Ask the owner to
   dictate one sentence into Notepad. Record `Model load breakdown`,
   `Model loaded in`, the first `Transcribe call took`, then a second dictation's
   `Transcribe call took`. **Never inject the hotkey/paste unattended** — a
   synthetic test on the home PC pasted into whatever window had focus.
3. **True cold launch.** `uv tool uninstall dictatem`, then
   `$env:UV_LINK_MODE = 'copy'` (forces brand-new files, not hard links to the
   already-scanned uv cache) and re-run the install. Record the same numbers as
   1–2. This is the "first install on a new laptop" case.
4. **Warm baseline.** Tray → Restart, then one dictation. Same numbers.

## Experiments (each answers a design question)

- **E1 (H1): what does the probe cost cold, and would NVML alone avoid it?** In
  a scratch dir (outside the repo), make two fresh copy-mode venvs with the
  runtime-gpu deps and time, each in a **new** venv:
  `import ctranslate2; ctranslate2.get_cuda_device_count()` vs
  `import pynvml; pynvml.nvmlInit(); pynvml.nvmlDeviceGetCount()`.
  If NVML is cheap and ctranslate2 is the 20 s, the fix is either "tray first,
  probe after" or a ctranslate2-free presence check (weigh: ctranslate2's count
  also proves the CUDA runtime works with the driver; NVML only proves a GPU).
- **E2 (H3): what does the HF call cost here?** Compare `Loading model...` →
  HTTP-request line timestamps. Then set a user env var `HF_HUB_OFFLINE=1`,
  restart the daemon from the tray, dictate (owner), and compare
  `Model loaded in`. Remove the env var afterwards.
- **E3: does MDE rescan by path or by content?** After step 3, uninstall and
  reinstall again with `UV_LINK_MODE=copy`. If the second cold launch is fast,
  MDE caches by hash → a one-time warm-up would also help after updates that
  don't change the DLLs; if slow, every new copy pays.

## Rules

- **Measure, don't fix.** Fix candidates below need the owner's sign-off.
- Do not touch Defender, exclusions, or any security setting — it's a managed
  corporate device. Only dictatem's own files, venvs and logs.
- Settled, don't reopen: **CPU is not becoming the default** (it would drop this
  laptop from `small`/cuda to `base`/cpu); don't delete DLLs from the NVIDIA
  wheels; keep `onnxruntime` (Silero VAD) and `av` (faster-whisper import);
  ADR-0025's load-on-arm + first-run fetch and "no preload at launch by default".
- No logged dictated text, ever (#188) — when quoting log lines, they only carry
  char counts; keep it that way.

## Candidate fixes (for the owner to choose from, after the numbers)

- **H1 →** create the tray before the hardware reconcile (or run the reconcile
  off the UI path), or detect GPU presence without importing ctranslate2.
  Constraint: the reconcile feeds `select_backend` → `build_transcriber`, and
  the CPU-fallback-for-this-session behaviour (ADR-0009) must stay.
- **H2 →** a one-time first-run background warm-up (load, transcribe 1 s of
  silence, unload) so the scan is paid during setup, not the first dictation.
  This **amends ADR-0025** (no model work at launch by default; installer stays
  thin), so it's a decision, not a tweak.
- **H3 →** load with `local_files_only=True` when the first-run fetch already
  cached the model, falling back to the network only if the cache misses.

## Results

_Fill in: machine, date, commit SHA, then one row per protocol step / experiment._

| Step | Install time | Env size | Startup timing (total; hw probe) | Model load (import / weights) | 1st transcribe | 2nd transcribe |
|---|---|---|---|---|---|---|
| 1 upgrade | | | | | | |
| 3 cold | | | | | | |
| 4 warm | | | | | | |

E1: · E2: · E3:
