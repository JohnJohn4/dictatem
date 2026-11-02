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

Machine: owner's managed work laptop — Windows 11 Enterprise 10.0.26100, NVIDIA
RTX 500 Ada Laptop 4 GB (driver 596.71), MDE. Date 2026-11-02. Branch commit
`43330ca`. uv 0.11.16.

| Step | Install time | Env size | Startup timing (total; hw probe) | Model load (import / weights) | 1st transcribe | 2nd transcribe |
|---|---|---|---|---|---|---|
| 1 upgrade | 29.9 s | 2,928 → 2,489 MB | 11.86 s; 3.64 s | 38.2 s (23.36 s / 14.88 s) | 36.93 s (6.3 s audio) | 1.07 s (6.0 s audio) |
| 3 cold (`UV_LINK_MODE=copy`) | 29.9 s (35 pkgs, 17.1 s link) | 2,483 MB | **37.14 s; 15.10 s** | **60.1 s (46.52 s / 13.54 s)** | **73.74 s** (2.7 s audio) | 0.78 s (9.0 s audio) |
| 4 warm | | | | | | |

**Step 1 (upgrade from v0.7.0).** Installer output was clean: it stopped the
running daemon (2 PIDs), removed `pyside6`, `pyside6-addons`, `pyside6-pdf`,
`pyside6-webengine`, reinstalled `pyside6-essentials` (the migration path
fired) and rebuilt `dictatem`. Only 2 packages were written; the
ctranslate2/NVIDIA DLLs were left untouched. Full startup line:
`interpreter 2.99s | adapters 0.74s | imports 3.28s | lock 0.84s | config 0.01s
| hw probe 3.64s | autostart 0.00s | qt app 0.10s | setup 0.09s | overlay+tray
0.10s | wiring 0.05s | total 11.86s`. The tray appeared and the menu opened.

**Step 2 (owner dictation, ~3.8 h after launch).** Three attempts:
1. Owner-reported *failed*: the pill took a long time to appear. Load-on-arm
   started at 20:52:58.6 and finished at 20:53:36.9 (`Model loaded in 38.2s`,
   `engine import 23.36s, weights 14.88s`). Only **0.338 s** of audio was
   captured; VAD removed all of it and the result was empty
   (`Transcribe call took 0.72s`, which means no cuBLAS work ran).
2. The pill was late again and the whole attempt took "a min or two":
   6.3 s of audio, **`Transcribe call took 36.93s`**. This is the first call
   that did real decoding, so it is the cuBLAS/cuDNN lazy load (H2).
3. About 3 s end to end: 6.0 s of audio, `Transcribe call took 1.07s`. The
   owner says the pill still felt slow to appear after the trigger key, even
   on this warm attempt.

HF timing inside the load: the engine import ended about 20:53:22.0, the HF
`GET …/revision/main 200` was logged at 20:53:32.6, and the load finished at
20:53:36.9. So about **10.6 s** passed between the import and the HTTP
response, then about 4.3 s for the actual weights. E2 must separate the
request from hub/SSL import cost.

**Finding A — the cold cost is not limited to newly written files.** This
upgrade did not rewrite any ctranslate2/NVIDIA DLL, and the same files loaded
in 2.7 s at 11:31 that morning (v0.7.0, a tray restart). Roughly 9 h later,
in a fresh process, they cost 23 s (import) + 37 s (cuBLAS). Something
invalidated the warm state in between (sleep/idle evicting the OS file cache,
an MDE cache or signature refresh, …). That weakens the H2 fix "one-time
first-run warm-up": it would not cover this case. E3 and a deliberate
"wait / sleep, then re-dictate" check should separate MDE from the file cache.

**H4 (new) — the background load starves the UI and capture threads.** The
load runs on a worker thread (`lifecycle.preload()`), but CPython holds the
GIL while it imports extension modules and their DLL dependencies. While MDE
scans a 100s-of-MB DLL, the Qt main thread, the hotkey handling and the audio
callback cannot run. That fits a pill that doesn't appear, and only 0.338 s
of audio from the first attempt. Not yet proven; a test would log
hotkey-press → pill-shown latency and captured-vs-held duration during a cold
load.

**Step 3 (true cold).** Full startup line: `interpreter 7.86s | adapters 2.02s |
imports 9.27s | lock 1.15s | config 0.01s | hw probe 15.10s | autostart 0.00s |
qt app 0.71s | setup 0.21s | overlay+tray 0.45s | wiring 0.35s | total 37.14s`.
H1 confirmed: with fresh files the probe is the largest single phase before the
tray, but interpreter + adapters + imports add another ~19 s. The first
dictation took about **2 min 14 s** end to end (load 60.1 s + transcribe
73.7 s). The owner reports a very slow pill on arm and a pill that "took a
while to go away" (that was the 73.7 s transcribe behind it). Same shape as
v0.7.0 earlier today (57.4 s load) and on 2026-10-28 (`Model loaded in
120.4s`), so this is not a regression from this branch. The branch changes no
runtime behaviour.

**H4 evidence:** three `Audio callback status: input overflow` warnings
(21:14:20, :33, :43) fell inside the 46.5 s engine import. The PortAudio
callback could not be serviced while the background import ran, which is
consistent with the import holding the GIL. 2026-10-28 shows the same
warnings during its 120 s cold load. Because of this, the first cold
dictation can lose audio, not just arrive late.

E1: · E2: · E3:
