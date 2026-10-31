# macOS transcribes on CPU faster-whisper first, with mlx-whisper as a GPU follow-up

The current transcription engine (faster-whisper / CTranslate2) has **no Metal
backend**, so on Apple Silicon it cannot use the GPU. Rather than block the macOS
launch on a new GPU engine, **macOS v1 reuses the existing
[`TranscriberBackend`](../../src/dictatem/interfaces.py) (CTranslate2) on
CPU**, and a Metal-accelerated `mlx-whisper` backend is added later as a second
backend + an Apple-Silicon [Hardware Tier](../../CONTEXT.md#hardware-tier) — the
"add a backend + a tier" path ADR-0007 was shaped to enable.

CPU-only is genuinely viable on Apple Silicon, not a stopgap that limps: unified
memory + AMX make `faster-whisper` INT8 fast — a fanless M2 Air runs the `medium`
model at ~0.32× real-time (≈0.3 s of compute per 1 s of audio). CTranslate2 ships
stable pre-built macOS arm64 wheels on PyPI, so the v1 engineering effort is
isolated entirely to the hard macOS platform integration (I/O adapters, platform
dispatch, and TCC privacy permissions) with **zero new transcription engine**.

## Considered options

- **CPU faster-whisper first, mlx-whisper follow-up (chosen).** No new engine for
  v1; the existing CPU profile and tier table already cover it. mlx-whisper slots
  in cleanly later behind the same Protocol.
- **mlx-whisper (Apple MLX) in v1.** Metal GPU acceleration and a snappy first
  impression, but a new dependency, a different model format, Apple-Silicon-only
  (no Intel Mac GPU, macOS 14.0+), and it couples the Mac launch to new-engine
  work. Deferred to the follow-up, not abandoned.
- **whisper.cpp (Metal, Intel + Apple Silicon).** Mature and fast, but
  **disqualified by the install posture (ADR-0011)**: Python wrappers (e.g.
  `pywhispercpp`) need a local C++ toolchain (Xcode CLT, CMake) to build, breaking
  the thin signed-wheels-only script; and the pre-built PyPI wheels frequently
  fail to locate their `ggml-metal.metal` shader at runtime, crashing or silently
  reverting to CPU. The native-component packaging cost outweighs the benefit.
- **Apple `SFSpeechRecognizer` (zero-dependency native).** Rejected outright: a
  hard 1-minute audio limit, undocumented daily rate limits, and poor accuracy on
  developer jargon (e.g. "kubernetes" → "communities").

## Consequences

- macOS v1 resolves to a CPU tier (`base`/`small`/`medium` at `int8`) via the
  existing `HardwareTierResolver`; no new transcription code ships in v1.
- Microphone capture goes through the existing `sounddevice`/PortAudio path
  (CoreAudio under the hood), so it is an adapter that likely already works — but
  it triggers a macOS Microphone (TCC) permission prompt (see the permissions
  ADR/slice).

### Forward constraints for the mlx-whisper follow-up

These are recorded now so the follow-up is designed, not discovered:

- **Model-format bifurcation.** CTranslate2 model files are incompatible with
  MLX (which needs `.npz` weights / the MLX-community format). The download +
  cache layer must route by the active backend tier — a dual pipeline, not one
  shared model store.
- **Runtime hardware dispatch.** MLX is Apple-Silicon + macOS 14.0+ only.
  Initialization must probe at runtime and **fall back to the faster-whisper CPU
  backend** on Intel Macs or older OSes rather than failing.
- **Brittle dependency resolution.** mlx-whisper wheels are tiny (~588 KB, JIT
  Metal kernel compilation), but `uv` resolution can be fragile around Python ABI
  tags; CI must exercise environment resolution across supported Python versions.

## Amendment (2026-10-31): the Apple-GPU tier uses mlx-whisper (#224)

This records the design of the mlx-whisper follow-up before any code lands. The
decisions above still hold. CPU faster-whisper stays the macOS baseline and the
fallback engine. The GPU engine is one more `TranscriberBackend` plus new
[Hardware Tier](../../CONTEXT.md#hardware-tier) rows (ADR-0007). It corrects two
forward constraints above: MLX Whisper weights are now safetensors (not only
`.npz`), and the install is not tiny, because mlx-whisper hard-depends on torch.

### Facts re-verified against primary sources (2026-10-31)

- **mlx-whisper** 0.4.3 (PyPI, 2025-08-29) is MIT-licensed and ships a
  pure-Python `any` wheel. It lives in Apple's `ml-explore/mlx-examples` repo,
  which is not archived; the last `whisper/` commit is 2025-12-15. Maintenance
  is slow but alive. Dependencies: `mlx>=0.11`, numba, numpy, **torch**, tqdm,
  more-itertools, tiktoken, huggingface_hub, scipy. torch is a hard dependency
  (~139 MB on macOS arm64, and its arm64 wheel is macOS 14+ only). numba plus
  llvmlite add ~44 MB. `transcribe()` takes a numpy array, `language` and
  `initial_prompt`. It has **no `hotwords`** and **no VAD**. Weights live in a
  process-global `ModelHolder`.
- **mlx** 0.32.4 (2026-10-14) is actively released. Its macOS wheels are
  **arm64 only, tagged `macosx_14_0` / `15_0` / `26_0`**, and there is no sdist.
  The Metal runtime (`mlx-metal`) is also macOS 14+ arm64 only. mlx now also
  ships Windows and Linux wheels, so `sys_platform == 'darwin'` alone is not a
  sufficient guard. macOS 13 has no wheel, so an unconditional dependency fails
  the whole `uv tool install` (the same failure class as the `av` pin).
- **Weights.** `mlx-community/whisper-large-v3-turbo` is ~1.6 GB of fp16
  safetensors, and `mlx-community` repos exist for every Whisper size. They are
  different files from the CTranslate2 `Systran/faster-whisper-*` repos but
  share the HuggingFace cache root (`HF_HOME`).
- **Headroom.** One public M4 / 24 GB benchmark on one short sentence puts
  `large-v3-turbo` at ~7.0 s on faster-whisper CPU and ~1.0 s on mlx-whisper.
  That is a single data point, so the acceptance targets below gate the tier,
  not the benchmark.

### Decision

- **Engine: mlx-whisper**, pinned to an exact tested version (0.4.3), with `mlx`
  constrained to a CI-tested minor range. It sits behind `TranscriberBackend`,
  and MLX is imported lazily inside that backend only. A later swap is one
  adapter.
- **Tiers.** Two new rows. They are chosen on first run only when MLX is usable,
  meaning Apple Silicon, macOS 14+, and the mlx-whisper package installed:
  - `Apple-GPU`: `large-v3-turbo` / `mlx` / `float16`, at 12 GB or more of
    unified memory.
  - `Apple-GPU-low`: `small` / `mlx` / `float16`, below 12 GB or when memory is
    unknown.

  Apple Silicon without MLX keeps the `Apple-Silicon` CPU tier (`small` /
  `cpu` / `int8`, #207), and Intel keeps `CPU`. The 12 GB split is tunable, not
  contractual, like the VRAM thresholds. The Transform tag stays `gemma4:e2b`.
- **Config.** `[model].device = "mlx"` selects the MLX backend; `cuda` and
  `cpu` keep faster-whisper. `[model].name` keeps the Whisper size names
  (`tiny` … `large-v3-turbo`, plus `.en` variants). A pure mapping turns them
  into their `mlx-community` repo ids. A full repo id (`org/name`) passes
  through, and an unknown name is a typed error. `compute_type` defaults to
  `float16`, and `float32` is accepted. The two engines never share model files.
- **Install gate.** A new optional extra, `apple-gpu`: the runtime extra plus
  mlx-whisper and the mlx constraint, marker-guarded to `darwin` + `arm64`.
  The marker cannot express "macOS 14+". So `install.sh` chooses
  `dictatem[apple-gpu]` only when `uname -m` is arm64 **and** the
  `sw_vers -productVersion` major is 14 or more, and `dictatem[runtime]`
  otherwise. `DICTATEM_NO_APPLE_GPU=1` forces the runtime extra. The installer
  prints which engine set it chose. The extra adds ~230 MB of install weight
  (torch, mlx-metal, llvmlite, scipy, …). faster-whisper is always installed,
  as the fallback engine. `install.ps1` is unchanged. Existing configs are
  never re-tiered: existing Apple-Silicon users opt in by editing `[model]`.
- **Fallback in two layers, config never rewritten** (extends ADR-0009):
  1. *Startup reconcile.* A config pinning `mlx` on a machine where MLX is not
     usable falls back for the session. It gets the whole `Apple-Silicon` row
     on Apple Silicon, or the `CPU` row elsewhere (including Windows).
  2. *Runtime load failure.* A fallback-composing transcriber wraps the MLX
     backend. MLX may fail to load (an import or Metal error, weights missing
     while offline, an unknown model name). Then the transcriber switches to a
     faster-whisper backend built from the `Apple-Silicon` row for the rest of
     the session. It re-transcribes the same audio, so the dictation is not
     lost (ADR-0023). The user gets one warning log line and one tray
     notification. The next launch tries MLX again.
- **Vocabulary degrades from `hotwords` to `initial_prompt`.** The MLX backend
  uses the existing hint selection with "no hotwords support". The log names
  the mechanism (`via initial_prompt`). Biasing may be weaker than with
  `hotwords`, and the README says so.
- **VAD.** When `[model].vad_filter` is on, the MLX backend pre-trims
  non-speech with the Silero VAD bundled in faster-whisper. That keeps the
  silence-hallucination guard on par with the CPU path. If VAD finds no speech,
  the result is empty.
- **Memory.** The same `idle_unload_minutes` reaper applies. Unloading drops
  the global model holder and clears the MLX buffer cache, so the unified
  memory is actually returned. All MLX work (load, transcribe, unload) runs on
  one backend-owned thread, so MLX never sees concurrent or cross-thread use.
  No OOM retry is added for MLX.
- **Fetch and load (ADR-0025 unchanged in shape).** First run fetches only the
  active tier's MLX repo. Loading uses the local cached snapshot first, so the
  GPU tier stays offline after setup. The CPU fallback's weights are not
  prefetched.

### Acceptance targets that gate auto-selection

The tier is auto-selected only once real-Mac QA meets these targets. QA runs on
an M-series Mac on macOS 14+ with a warm model, and measures stop-to-paste from
`daemon.log` timestamps.

- ~5 s utterance: p50 ≤ 1.5 s, worst of 10 ≤ 2.5 s.
- ~15 s utterance: p50 ≤ 2.5 s.
- Each is faster than the `Apple-Silicon` CPU `small` tier on the same Mac,
  measured back to back.
- Cold load from cached weights takes ≤ 6 s. Load-on-arm hides it for a 5 s
  utterance on a ≥16 GB machine.
- The first-run fetch completes, and a later `HF_HUB_OFFLINE=1` dictation
  succeeds.
- After idle unload (or tray Unload), process RSS is within 300 MB of the
  pre-load baseline.
- `Apple-GPU-low` on an 8 GB Mac: ~5 s utterance p50 ≤ 1.5 s, with no swap
  pressure while the Ollama Transform model is resident.
- Accuracy: on a fixed 10-sentence jargon script, `Apple-GPU` word errors are
  ≤ the CPU `small` tier.
- Vocabulary: a term mis-heard without the file is recognised with it in at
  least 3 of 5 tries.

### Considered options (re-evaluated 2026-10-31)

- **mlx-whisper (chosen).** It is Whisper-compatible (same model names,
  languages and `initial_prompt`), ships a pure-Python wheel, and is maintained
  by Apple's MLX org. The costs are torch as an install-time dependency and a
  slow release cadence. The cadence is the main long-term risk, and the backend
  seam keeps a swap cheap.
- **lightning-whisper-mlx.** Rejected because it is unmaintained: the last
  release is 0.0.10 (2024-04), it has no licence metadata, and it pins
  `tiktoken==0.3.3`.
- **pywhispercpp (whisper.cpp).** Still rejected. It is active (1.5.1,
  2026-08), but its PyPI wheels are documented as CPU-only. Metal and Core ML
  need a source build, which breaks the wheels-only install posture (ADR-0011).
- **mlx-audio.** Rejected for the default tier. It is very active (0.6.3,
  2026-10-28), but it pulls `transformers>=5` and pins `mlx` exactly, so its
  dependency surface is far heavier and churns fast. It is the documented swap
  target if mlx-whisper rots, behind the same backend seam.
- **parakeet-mlx.** The fastest option (~0.5 s in the same benchmark), but it
  is not Whisper. It covers English (v2) or ~25 European languages (v3), has no
  prompt or vocabulary biasing, and needs librosa. It is out of scope here and
  recorded as a possible future **opt-in** English/European mode.

### Consequences

- `HardwareProfile` gains `mlx_available` and an optional `unified_memory_mb`.
  The pure Mac probe computes them from injected inputs, without importing MLX.
- The resolver gains the two `Apple-GPU` rows. Reconcile gains the `mlx` guard
  and a machine-readable fallback reason (cuda-absent vs mlx-unavailable), so
  the notification names the right cause.
- CI's macOS leg must resolve the `apple-gpu` extra on every supported Python.
  A static test guards the `install.sh` gate.
- Importing the daemon on Windows or Intel never imports `mlx`.
