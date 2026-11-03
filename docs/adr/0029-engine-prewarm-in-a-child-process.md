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
