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
| 4 restart (tray) | — | — | 19.77 s; 4.80 s | 19.3 s (3.35 s / 15.98 s) | 2.52 s (13.6 s audio) | |

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

**Step 4 (Tray → Restart, ~17 min after step 3).** Startup: `interpreter
4.93s | adapters 1.82s | imports 5.95s | lock 1.28s | config 0.03s | hw probe
4.80s | … | wiring 0.49s | total 19.77s` (the tray appeared ~20 s after the
click; `lock` includes waiting for the old instance). The engine import is
warm now (3.35 s) and so is cuBLAS (2.52 s for 13.6 s of audio). **The weights
phase stayed slow at 15.98 s.** The import ended about 21:35:00.1 and the HF
`revision/main` response was logged at 21:35:12.1, i.e. ~12 s; the actual
weight load after it took ~3.9 s. Step 1 showed the same ~10.6 s gap, and at
11:31 this morning the gap was ~1 s. **H3 looks like the dominant warm-path
cost on this network tonight**, on every load. E2 will confirm it.

**Missed hotkey press:** after the restart the owner had to press the hotkey
twice. The first press left no trace: there is no `Loading model...` line,
and load-on-arm would have logged one on any RECORD_START. So it never
reached record-start. The cause is unknown because hotkey events are not
logged. Candidates: the press landed before the hook was installed (the tray
appears ~20 s after Restart), or it was dropped somewhere in the hook/state
machine. A diagnostic hotkey-event log line (no key content beyond the
configured hotkey) would settle it.

**E2 (H3) — H3 killed as the main cost.** The daemon was relaunched from a
shell with `HF_HUB_OFFLINE=1` set for that process only (a tray restart would
not pick up a new user env var, because the child inherits the old process's
environment). Startup total was 18.87 s. One owner dictation of 11.1 s audio:
no HTTP line was logged (offline took effect), but `Model loaded in 18.0s
(engine import 3.18s, weights 14.86s)` was essentially the same as step 4's
19.3 s / 15.98 s. Transcribe 1.90 s. The pill was still slow to appear. So
the ~12 s before the HF line in steps 1 and 4 is **not** the network request.
(Going offline is still worth doing for the local-first story, but it won't
buy speed here.)

**Standalone load split (same venv, same machine, warm, daemon idle,
`C:\Temp\dictatem-perf\load_split.py`):**

| | online | `HF_HUB_OFFLINE=1` |
|---|---|---|
| import faster_whisper + ctranslate2 | 0.92 s | 1.07 s |
| `download_model("small")` | 0.86 s | 0.55 s |
| `ctranslate2.models.Whisper(cuda, float16)` | 1.59 s | 0.82 s |
| `WhisperModel(local path)` again | 0.75 s | 0.80 s |

**Finding B / H5 — the load is ~5–10× slower inside the daemon than
standalone, with warm files.** In step 4, `download_model` (mostly Python:
hub + httpx) took ~12 s in the daemon vs 0.86 s standalone. The leading
suspect is GIL contention with the live recording: load-on-arm runs the load
while the user is still talking, so the audio callback, level meter and Qt
overlay are all active. This morning's v0.7.0 load of 2.7 s came with a short
2.9 s utterance; tonight's 15–19 s loads came with 11–14 s utterances. H4 is
the other side of the same contention (the load starves the UI and audio).
Proposed A/B (owner): after a restart, a ~1 s dictation vs (after another
restart) a ~12 s dictation, comparing `Model loaded in`.

**A/B run 1 — H5 killed.** A ~1 s dictation ("testing", 1.35 s of audio) right
after a fresh launch still took `Model loaded in 19.3s (engine import 3.72s,
weights 15.59s)`, with the same ~12 s before the HF line. Run 2 was skipped
because recording length isn't the driver.

**Standalone under the daemon's conditions doesn't reproduce it either.**
`C:\Temp\dictatem-perf\load_bisect.py` under `pythonw.exe` with the load in a
background thread: import 0.84–0.88 s, download 0.71–0.85 s, ct2 build
1.15–1.29 s (one first run had a 7.88 s import outlier).

**Profiling the live daemon:** `uvx py-spy dump/record` works once it is
pointed at the *child* interpreter. The tool venv's `Scripts\pythonw.exe` is a
redirector that spawns `uv\python\cpython-3.12…\pythonw.exe`. The recorded
load (22:38:35, owner dictation) happened to be fast: `Model loaded in 3.2s
(0.46s / 2.72s)`, HF response after 1.5 s.

**Finding C — warm loads are slow after ~15 min of no GPU/model activity,
fast within a few minutes of the last load:**

| Load | Gap since previous GPU/model use | `Model loaded in` |
|---|---|---|
| 11:31 (v0.7.0) | ~6 min | 2.7 s |
| 21:34 (step 4) | ~17 min | 19.3 s |
| 21:51 (E2, offline) | ~16 min | 18.0 s |
| 22:34 (A/B run 1) | ~43 min | 19.3 s |
| standalone scripts 21:52, 22:35 | 1–2 min | ~3 s |
| 22:38 (profiled) | ~2 min (after standalone runs) | 3.2 s |

So the cost is not "inside the daemon". Something goes cold on idle:
dGPU/Optimus power state, the network/proxy path, or an MDE cache TTL. Next:
leave the machine idle ≥20 min with the daemon stopped (a resident model keeps
the GPU awake), then run a finer-grained standalone split under py-spy.

**Idle test (Finding C follow-up), daemon stopped 22:40, run at 23:01 after
21 min idle.** `C:\Temp\dictatem-perf\idle_split.py`. (The py-spy-wrapped run
died: `py-spy record -- Scripts\python.exe` attaches to the venv redirector,
not the child interpreter.) The first full run after the idle was **fast**:
DNS 0.03 s, register DLL dirs 0.18 s, import ct2 0.15 s, import
faster_whisper 0.31 s, `download_model` 0.64 s, `get_cuda_device_count`
1.71 s, ct2 construct 0.68 s, **total 3.69 s**. So a plain idle gap doesn't
make a standalone load slow, and **Finding C's cause is still open**. It may
need the daemon to have been resident across the gap. Next step: arm py-spy
on the live daemon's *child* PID and catch a slow (≥15 min gap) load.

**E1 (H1) — NVML is ~8× cheaper cold.** Fresh `UV_LINK_MODE=copy` venvs
(`C:\Temp\dictatem-perf\e1`), each with only its own package:

| | 1st run (fresh files) | 2nd run |
|---|---|---|
| `import ctranslate2` + `get_cuda_device_count()` | **7.61 s** (5.93 + 1.68) | 0.88 s |
| `import pynvml` + `nvmlInit()` + `nvmlDeviceGetCount()` | **0.89 s** (0.19 + 0.70) | 0.22 s |

The daemon's cold `hw probe` (15.1 s in step 3) is larger than ct2 alone,
because it competes with the rest of the cold import tree. Either fix
direction (tray first, or NVML-only presence check) removes most of it from
the tray path.

**E3 — every fresh copy pays again, partly.** A second uninstall +
`UV_LINK_MODE=copy` reinstall (29.3 s): `Startup timing: interpreter 4.42s |
adapters 0.86s | imports 4.47s | lock 0.13s | hw probe 8.17s | … | total
19.04s` (step 3: 37.14 s / 15.10 s). A standalone cold load + transcribe of
4 s of noise with VAD off (`cold_transcribe.py`, which overlapped the
daemon's own startup for its first ~19 s): **engine import 17.81 s, weights
7.00 s, 1st transcribe 35.95 s**, 2nd 0.15 s. The immediate repeat was 0.58 s
/ 2.11 s / 0.95 s. So identical content in new files is **not** free: it is
roughly half of the first cold cost, and the cuBLAS/cuDNN first-transcribe
stall (~36 s) is reproducible outside the daemon. Every update that rewrites
the NVIDIA wheels will pay it again.

## Conclusions (for the owner's fix decision)

1. **H1 confirmed.** On a cold launch the probe is 8–15 s of the 19–37 s
   before the tray. ct2 detection costs 7.6 s cold vs 0.9 s with NVML.
2. **H2 confirmed and the biggest cost.** The first real transcribe after
   new files costs 36–74 s. It reproduces standalone, and E3 shows it recurs
   on every fresh copy. Finding A shows it can also recur without new files.
3. **H3 killed as a speed issue** (offline made no difference). It is still
   an outbound call per load.
4. **H4 strongly supported.** During the background load the audio callback
   overflows (3× in step 3, also on 2026-10-28), the pill appears late, and
   one attempt captured 0.34 s and came back empty. This is a user-visible
   bug: lost audio, not just latency.
5. **H5 killed** (recording length isn't the driver). **Finding C (slow warm
   loads after ~15 min) is still unexplained** and only reproduces inside the
   resident daemon so far.
6. **Missed first hotkey press** after a restart: no log trace. Probably
   pressed before the tray was back (~20 s); hotkey events are not logged.

## Fixes implemented (owner go-ahead 2026-11-02) and verification

Commits on `perf/slimming`: `7f49dee` (NVML-first probe, cache-first model
resolution), `8bd4647` (engine prewarm child, ADR-0029, and the hotkey
input-event log), `e5909af` (prewarm gate fix: it compared device names
instead of `BackendKind`, so it never fired in the daemon). Candidate fix 3
(model warm-up at first run) was **replaced by the prewarm**. The prewarm gets
the same scan benefit without putting a model in VRAM, so ADR-0025 holds.

Verification on the work laptop, 2026-11-03, installed from the local checkout:

- **Probe:** `CUDA device detected (via nvml)`. On fresh copy-mode files, `hw
  probe 1.85s` and `total 17.72s` (step 3: 15.10 s / 37.14 s). Warm: 1.7 s.
- **Prewarm in the daemon:** `Engine prewarm started` 1 s after `daemon
  started`, then `Engine prewarm finished in 212.6s (exit 0)` in the background.
  The tray and hotkey were usable throughout.
- **After the prewarm, a first load + transcribe in a new process**
  (`cold_transcribe.py`): engine import **0.55 s** (was 17.8–46.5 s), 1st
  transcribe **0.78 s** (was 36–74 s).
- **Cache-first resolution:** loading via `FasterWhisperBackend.load_model()`
  logged no HF request. `load_model 3.83s` (import 0.48 s, weights 3.35 s).
- **Not yet verified with the owner at the keyboard:** an in-daemon dictation
  after a cold launch, and the new `Hotkey …` log lines in the field.

Gotchas found along the way:

- `uv tool install "dictatem[...] @ file:///…"` reuses a cached build of the
  same version. Use `--reinstall-package dictatem --refresh-package dictatem`
  or you test stale code.
- Daemons launched with `Start-Process` from an agent shell die when the
  agent session ends. Launch detached via `Invoke-CimMethod Win32_Process
  Create` when it must outlive the session.
- py-spy must target the child interpreter (`uv\python\cpython-…\pythonw.exe`),
  not the tool venv's `Scripts\pythonw.exe` redirector.

Open: Finding C (warm loads of ~19 s after a long gap in a resident daemon,
not reproducible standalone) and H4's stall during a mid-session rescan. The
prewarm only covers launch.

## Owner tests on the fixed build (2026-11-03, local install of `feb6f24`)

**Install-time prewarm.** Real `install.ps1` from the checkout, fresh
`UV_LINK_MODE=copy` files: `Speech engine ready (130 s)`, install total 151 s,
then launch. Startup total 14.99 s (`hw probe 0.97s`; `imports 7.83s` is now
the largest phase, which is the Qt/PySide6 DLLs, not prewarmed). The launch
prewarm then took 1.9 s.

**Test A: first dictation after the fresh install (~6 min after the
prewarm).** `Model loaded in 17.1s (engine import 6.45s, weights 10.63s)`,
then `Transcribe call took 14.63s`. That is about 27 s from stop to paste
(step 3: about 2 min 14 s). The second dictation took 0.61 s. This is better
than before the fixes but not the ~1 s seen standalone right after the
prewarm. It fits Finding C: the warm state fades within minutes here.

**Test B: offline.** The daemon was relaunched with `HTTP(S)_PROXY` /
`ALL_PROXY` pointing at a dead port (`NO_PROXY=localhost,127.0.0.1`); both
urllib and httpx2 were verified blocked. The launch prewarm took 13.7 s. The
owner dictated ~27 s later: **it worked**, with no HF request, `Model loaded
in 2.9s (0.48s / 2.45s)` and `Transcribe call took 0.95s`. After the
first-run fetch, dictation needs no network (the update check only runs from
the tray menu; Ollama is localhost).

**Pill delay = record-start blocks the GUI thread for 1-2 s.** The new hotkey
log shows `KEY_DOWN … handled in 1938ms` (first press after install), 1000 ms
(second), 1141 ms (Test B). The pill is drawn only after the mic stream
opens. py-spy over the Test B press (~0.98 s inside `_do_record_start`):
**~0.60 s** in `sounddevice.InputStream.__init__` (PortAudio/WASAPI stream
open), **~0.32 s** importing `sounddevice` (lazily, on the first press of each
session), ~0.06 s `show_pill`. Candidate fixes for the owner:

1. Import `sounddevice` at launch (after the tray): safe, saves ~0.3 s on
   every first press, more when cold.
2. Speed up the stream open. Options: pre-open and keep the stream stopped
   (check whether Windows shows the mic-in-use indicator for an opened but
   unstarted stream), or open it off the GUI thread. Do **not** show the pill
   before the mic is live, or the start of speech is lost.

Still open: Finding C (warm state fades within minutes; Test A paid ~32 s of
load + transcribe 6 min after the prewarm).

## Microphone + tray follow-up (owner-requested, 2026-11-03)

Commits `aa2d2bc` (PortAudio DLL preload, superseded), `ce64651` (device
re-scan, tray Microphone menu, tray slimming), `cfe709f` (an unplugged choice
is hidden and System default is ticked while it's away). Owner-verified on
the work laptop:

- **The mic-in-use indicator shows only while recording**, never during the
  idle re-scan.
- **Record-start (key press → pill can show):** built-in Realtek array
  453–782 ms (was 1000–1938 ms); **Jabra headset 47–62 ms**. What's left is
  the built-in array's driver opening slowly. Holding the stream open was
  rejected by the owner (privacy; other apps need the mic).
- **Hot-plug:** the Jabra was picked in the menu and used. Unplugged:
  `Microphone '…Jabra…' is not connected; using the system default`, and the
  menu hid it and ticked System default. Replugged: ticked again automatically
  and used (record-start 156 ms).
- **Still open:** Finding C. The first loads at 2.5 min and 20 min after
  launch took 12.6 s and 12.0 s (weights ~10 s, offline).

## Finding C: investigated and fixed on `perf/finding-c` (2026-11-03)

**Diagnosis.**
- Imitation runs (windowless `pythonw`, idle, then load exactly like dictatem;
  `C:\Temp\dictatem-perf\idle_load.py`).
- **py-spy with `--native` at 100 Hz distorts timings 10-15×** (C1 60 s, C3
  97 s vs unprofiled 6-9 s), so those runs are only good for relative hot
  spots. Lightweight py-spy (Python-only, 50 Hz) is fine.
- Opting out of power throttling (`SetProcessInformation` /
  `PROCESS_POWER_THROTTLING_EXECUTION_SPEED`) did **not** help, so EcoQoS is
  ruled out as the main cause.
- Clean unprofiled idle runs: 3 min gap 6.2 s, 21 min gap 9.3 s; warm 4.8 s.
- The daemon's own launch prewarm took **45.8 s** about 30 min after the files
  were last loaded (normally 1-4 s): **scan verdicts expire after a gap**.
- A lightweight profile of a real daemon load after a ~50 min gap (`Model loaded
  in 14.5s`: import 4.44, resolve 6.88, construct 3.15):
  - "resolve" was really the lazy import of huggingface_hub/httpx2;
  - 252 of 326 samples were **PySide6's `shibokensupport.feature._mod_uses_pyside`
    calling `inspect.getsource()`** on every newly imported module (it reads
    each `.py` source again to look for "PySide6");
  - the rest was `FileLoader.get_data` (file opens).
- Standalone (with Qt imported), stock vs patched hook: first run 1.82 s + 0.66 s
  vs 0.41 s + 0.33 s; warm runs 0.51 + 0.44 vs 0.43 + 0.33.

**Fix (`1228b77`).**
- (1) `dictatem.qt_import_hook.limit_pyside_source_scan()`, called right after
  the daemon first imports PySide6: non-dictatem modules skip the source scan
  (dictatem never uses `__feature__`).
- (2) The prewarm child writes `~/.dictatem/.slow_engine_load` when it takes
  ≥ 10 s. With `[startup] resident_engine = "auto"`, the daemon then imports
  faster-whisper and maps the NVIDIA DLLs in-process after the launch prewarm,
  and keeps them.

**Verified so far.**
- Without the marker, auto stayed light (the prewarm took 3.2 s).
- With the marker (written by hand from the 14:26 45.8 s run, because today's
  slow prewarms predate the code), the log shows `Engine kept resident in this
  process (1.6s; no model loaded)`.
- RSS 96 MB → 325 MB; `nvidia-smi` shows no compute process and 0 MiB used.
- **Owner dictation after a 35 min gap (16:28): `Model loaded in 3.1s`
  (engine import 0.01s, weights 3.12s (resolve 0.07s, construct 3.05s))**,
  then `Transcribe call took 1.45s`. Before the fix (15:44, ~50 min gap):
  14.5 s (4.44 / 6.88 / 3.15). The load finished while the owner was still
  speaking: stop → paste ~1.5 s (was ~12.8 s). Owner: "wow that was much
  faster". Remaining: the model-file read (construct ~3 s) after a gap.

## Home PC smoke test (2026-11-03, `perf/finding-c` @ `d5083f2`)

Owner's home PC: Windows 11 Home, RTX 3050 Laptop 4 GB, consumer Defender.
Upgraded from an installed v0.7.0 via the real installer (`irm | iex`, SHA
tarball). The owner dictated; the agent read `daemon.log`.

**Verdict: no regression on a normal PC. The work-laptop-only paths stay off.**
There's one open question (the prewarm threshold margin) and one pre-existing
installer bug (below). Neither blocks merging #296/#297.

| Check | Expected | Home PC (branch) | v0.7.0 baseline |
|---|---|---|---|
| Upgrade install (warm uv cache) | — | **17 s** | — |
| Installer `Speech engine ready` | a few s | **8 s** (upgrade); **6 s** (cold, `UV_LINK_MODE=copy`) | n/a |
| `~/.dictatem/.slow_engine_load` | absent | **absent** (after both installs) | — |
| `Engine kept resident…` line | absent | **absent** | — |
| Env size | ~2,490 MB | **2,486 MB** | **2,489 MB** measured (not ~2,930; see note) |
| PySide6 → Essentials migration | tray works | `pyside6_essentials-6.12.0` only; **tray OK** | — |
| Idle daemon RSS (no model) | ~100 MB | **103 MB** | — |
| `Startup timing` total (first launch after upgrade) | ≲ 5 s | **4.99 s** (hw probe 1.40 s) | ~5 s |
| `Startup timing` total (warm relaunch) | — | **1.26 s** (hw probe 0.67 s); 2.95 s after cold install | — |
| Probe line | via nvml | `CUDA device detected (via nvml)` | — |
| Launch `Engine prewarm finished` | a few s | **3.4 s** after upgrade; 0.5–0.6 s afterwards | — |
| First dictation `Model loaded in` | ≈ 3–4 s | **4.2 s** (import 0.13, weights 4.10: resolve 2.29, construct 1.81) | 3.7 s |
| 1st `Transcribe call took` | ≈ 1 s | **0.82 s** | 1.3 s |
| Later transcribes | — | 0.58, 0.40, 0.49, 0.53 s | — |
| `Hotkey KEY_DOWN` (record start, incl. mic open) | ≪ 1 s | 641, 578, 359, 594, 359 ms | — |
| `Hotkey KEY_DOWN` (stop → transcribe) | — | 47–63 ms | — |
| Pill (owner) | — | "felt quick" | — |
| Tray items | no Preload / Start-Stop; Unload + Microphone ▸ | as expected | — |
| USB mic (Jabra EVOLVE 20 SE) | used, select, unplug → default, replug → ticked | all four OK; log shows `Microphone set to 'Headset Microphone (Jabra EVOLVE 20 SE MS)'`, then `…is not connected; using the system default` on the next recording | — |
| Taskbar mic indicator only while recording | yes | **yes** (owner) | — |
| Unload model → VRAM | freed | **433 → 71 MiB**; RSS stays ~776 MB (CUDA/CT2 DLLs stay mapped) | — |
| Offline (proxy → 127.0.0.1:9) | works, no `HTTP Request` | **works, 0 HTTP lines**; load 1.4 s (resolve 0.17 s), transcribe 0.53 s | — |
| `pytest -q` | 2089 passed, 32 skipped | **2075 passed, 46 skipped** (same 2121 total; see note) | — |
| `ruff check .` | clean | **All checks passed** | — |

**Notes.**
- **Prewarm threshold margin (owner flagged, open question).** The upgrade
  install's prewarm took 8 s on this ordinary consumer PC, against the 10 s
  `.slow_engine_load` threshold: a margin of only 1.25×. The cold copy install
  took 6 s. A slower home PC (HDD, older CPU, third-party AV) could plausibly
  cross 10 s and switch on the resident engine (+~230 MB RSS) without needing
  it. The owner is unsure whether 10 s is the right number. Options for the
  work-laptop session: raise the threshold (the work laptop's slow prewarms
  were 45.8 s, far above it), or require it to be exceeded twice or at launch
  as well, not only at install. The launch prewarm right after was 3.4 s here.
- **First-load `resolve` 2.29 s** is a cold disk-cache effect, not network
  access: the offline reload had resolve 0.17 s and no HTTP lines. Model load
  overall is ~0.5 s slower than the v0.7.0 baseline, but it overlaps with
  recording, so the owner didn't notice. First transcribe is faster
  (0.82 vs 1.3 s).
- One `Audio callback status: input overflow` warning came during the first
  recording, while the model was loading in parallel. The text pasted correctly.
- **Env size:** v0.7.0 already measured 2,489 MB on this PC before the
  upgrade, so the ~440 MB PySide6 saving doesn't show here (this v0.7.0 env
  probably never had the full meta Addons). The migration path still left
  Essentials only and a working tray.
- **Tests:** the 14 extra skips are all `test_apple_gpu_extra.py: needs a
  POSIX sh` (no `sh` on PATH in the agent's PowerShell). That's environmental,
  not a regression.
- **Pre-existing installer bug (same code on `main`):** the agent aborted one
  cold-install run partway through (a `2>&1` on `iex` turned uv's stderr into a
  terminating error). That left `Scripts\python.exe` at 0 bytes, and the next
  installer run exposed two faults:
  1. `install.ps1:389`: uv exits 2 → the failure branch calls
     `Test-DictatemEnvBroken`, which runs `uv tool dir` and **resets
     `$LASTEXITCODE` to 0**. The re-check at `install.ps1:402` then passes, the
     `throw` never runs, and the installer goes on to prewarm (`could not run`)
     and launch (`Start-Process: cannot find the file`). Fix: capture uv's exit
     code in a variable straight after each `uv tool install`.
  2. `Test-DictatemEnvBroken` only checks that `python.exe` *exists*, so a
     truncated (0-byte) interpreter isn't treated as broken and repaired.
     Recovered by hand: `uv tool uninstall dictatem` + remove the env dir.
     After that the cold install was clean.

**Resolved by the work-laptop session (2026-11-03).**
- **Threshold:** `SLOW_PREWARM_S` raised to **20 s** (`b5b792b`, PR #297). A
  normal PC measured 6–8 s; the work laptop's cold scans were 45.8–212 s.
  "Exceeded twice" was considered and rejected: more state, and it wouldn't
  change the outcome on either machine.
- **Installer bug:** fixed in its own PR **#298** (`fix/install-exit-code`,
  base `main`). `$uvInstallExit` is captured right after each `uv tool
  install`; a < 1 KB `python.exe` counts as broken. Verified by running the
  real block under a stub `uv`: `main` doesn't throw (bug reproduced), the fix
  throws or repairs as appropriate. Merge after #296/#297, rebasing past
  #296's one-line `@migrateArgs` conflict.
