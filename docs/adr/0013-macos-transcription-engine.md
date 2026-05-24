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
