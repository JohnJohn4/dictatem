# Engine prewarm: load the engine DLLs once in a throwaway child process at launch

Amends [ADR-0025](0025-cold-start-load-on-arm-fetch-on-first-run.md) (launch
still loads **no model** and holds **no GPU memory**; only the engine's DLL
files are touched).

On the managed work laptop (Windows 11 Enterprise, Microsoft Defender for
Endpoint), the first load of each newly seen engine DLL is scanned before it
maps. The measurements are in
`docs/agents/handoffs/2026-11-02-slimming-work-laptop.md`, on branch
`perf/slimming`. In-process, that cost landed on the first dictation:

- 17–46 s importing faster-whisper/CTranslate2.
- 36–74 s in the first transcribe, when cuBLAS/cuDNN load lazily.
- While it ran, the daemon's own threads stalled. The pill appeared late, the
  PortAudio callback overflowed (`input overflow`), and one dictation captured
  0.34 s of audio and came back empty.

A second process loading the same files right after was fast, because the
scan verdict is cached per file. A brand-new copy of the same files (a
reinstall or update) pays again.

## Decision

Shortly after the tray is up (1 s, so first paint isn't competing for disk),
the daemon spawns `python -m dictatem.transcribe.prewarm`:

- **Windows and the faster-whisper engine only** (`cuda`/`cpu`).
- Spawned with **below-normal priority** and **no window**, and never waited
  on. A watcher thread logs `Engine prewarm finished in Xs (exit N)`.
- The child imports faster-whisper (CTranslate2, ONNX Runtime, PyAV) and loads
  every DLL in the NVIDIA wheels' `bin` directories, then exits. It loads no
  model, makes no CUDA context, allocates no VRAM and makes no network call.
- Skipped when `[startup] preload_model = true`, which loads the real model at
  launch anyway.
- On by default; opt out with `[startup] prewarm_engine = false`.

**At install time too.** `install.ps1` runs the same child, blocking, *before* it
launches the daemon, with a "Preparing the speech engine… please wait" message.
The user can't start dictating into a half-scanned engine, because the tray
only appears once it's done. This covers fresh installs and tray-driven
updates (both run `install.ps1`). A failure there is reported and the install
continues. The launch-time prewarm stays: after an install it finishes in
seconds, and it covers later launches where the scan state has gone cold again
(observed after a long gap). This amends ADR-0025's "installer stays thin" for
this one step; it still downloads nothing at install.

## Why not the alternatives

- **Load + transcribe silence at first run** (a model warm-up). It would also
  pay the cuBLAS cost, but it puts a model in VRAM at install/launch, which is
  the thing ADR-0025 rejected. The DLL-only prewarm gets the same scan benefit
  without it.
- **Do the scan in-process on a background thread.** The stall *is* the
  in-process load; a background thread still starves the GUI and audio
  threads.
- **Defender exclusions.** Not ours to set on managed devices, and the wrong
  default for everyone else.

## Consequences

- On scanner-heavy machines the first dictation after launch/install no longer
  pays the engine scan, provided the prewarm finished first. The prewarm took
  ~1 minute cold on the work laptop. If the user arms before it finishes, both
  processes scan concurrently; that is no worse than before.
- On ordinary machines it costs a second or two of below-normal-priority
  background disk/CPU after launch, and leaves the files in the OS cache, which
  helps the first dictation there too. Peak memory of the child is a few
  hundred MB, briefly.
- It does **not** cover a scan that recurs later in a long-lived session
  (observed: warm loads of ~19 s after a long gap; cause still open).

## Amendment (2026-11-03): resident engine on slow-scan machines, and PySide6's import hook

Follow-up QA on the work laptop ("Finding C" in
`docs/agents/handoffs/2026-11-02-slimming-work-laptop.md`) showed that the
scanner's per-file verdicts **expire after a gap**: ~6–30 minutes was observed.
The launch prewarm then took 45.8 s instead of 1–4 s. The first dictation after
a gap re-paid ~12–15 s in a fresh daemon even though the prewarm had run. So a
one-off prewarm is not enough on such machines. Two changes:

1. **PySide6's import hook stops re-reading every module's source.** PySide6
   wraps `__import__` for its optional `__feature__` switches, and for each new
   module calls `inspect.getsource()` to look for the text "PySide6". That
   doubled the file reads of every module imported after Qt (faster-whisper,
   huggingface_hub, httpx2…), and on the work laptop it was ~5 s of one slow
   load. Dictatem never uses `__feature__`, so `dictatem.qt_import_hook`
   answers "no" for non-dictatem modules without reading any source. It is a
   patch to a private shiboken module, guarded: if the layout changes it does
   nothing.

2. **Resident engine where a prewarm was slow.** The prewarm child times
   itself. If it took ≥ 10 s, it writes `~/.dictatem/.slow_engine_load` (a
   machine property; never removed automatically). With `[startup]
   resident_engine = "auto"` (default), once the launch prewarm finishes and
   that marker exists, the daemon imports faster-whisper and maps the NVIDIA
   DLLs **into its own process** and keeps them. No model, no CUDA context, no
   VRAM. Mapped images aren't rescanned, so a later first dictation opens none
   of those files; CTranslate2's `LoadLibrary("cublas64_12.dll")` gets the
   already-loaded module. `"on"` / `"off"` force it.

Consequences: on scanner machines the daemon holds a few hundred MB more RAM
while idle, in exchange for not re-paying the scan on every first dictation
after a gap. Machines that prewarm quickly never get the marker and keep the
light idle footprint. Reading the model file itself after a gap (~3 s on the
work laptop) is not covered.
