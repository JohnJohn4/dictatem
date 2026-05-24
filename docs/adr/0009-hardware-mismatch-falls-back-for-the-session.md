# A hardware mismatch falls back to CPU for the session, never rewriting the config

ADR-0007 resolves the [Hardware Tier](../../CONTEXT.md#hardware-tier) once on
first run and bakes concrete `(model, device, compute_type)` values into
`~/.dictatem/config.toml`, which every later launch reads unchanged. That leaves
one gap ADR-0007 explicitly deferred: a config baked on a GPU machine (e.g.
`device = "cuda"`, `compute_type = "float16"`) and then run on a CPU-only
machine — a removed/dead GPU, an unplugged eGPU, or a config copied between
boxes. faster-whisper does not transparently fall back from CUDA to CPU; it
raises at model load and the daemon never transcribes.

On startup the daemon now **reconciles** the config's pinned transcription
hardware against the current `HardwareProfile` from the probe. When the config
pins `cuda` but the machine reports no CUDA, `HardwareTierResolver.reconcile`
returns the whole CPU tier row (`base` / `cpu` / `int8`) and `did_fall_back =
True`. The fallback is **for that session only**: the config file is never
rewritten, so the user's pinned GPU values are preserved and take effect again
automatically once the hardware returns.

We adopt the **whole** CPU row, not just `device = "cpu"`. The cuda compute
types (`float16`, `int8_float16`) and cuda-sized models won't run on CPU either,
so flipping only the device would still crash; the CPU tier is the one
self-consistent target. The reconcile is **pure** (no I/O, no native imports):
it takes the config's values and a `HardwareProfile` and returns
`(ResolvedHardware, did_fall_back)`, so the crash-guard logic is fully unit
tested across present/absent hardware without a real probe.

Scope is the transcription hardware only. The Transform (Ollama) model is
independent of CUDA, so a CPU fallback does **not** change `transform.model_name`
— the daemon ignores the CPU tier's `transform_model` that `reconcile` returns
as a byproduct of handing back the whole row.

## Considered options

- **Rewrite the config to the CPU tier on mismatch.** Stops the crash but
  silently destroys the user's pinned GPU choice: when they plug the GPU back in
  (or copy the config back to the GPU box) it would now run on CPU forever with
  no signal. The config is authoritative and user-owned (ADR-0007); a transient
  hardware absence must not mutate it.
- **Re-tier on every launch against the current VRAM (drop ADR-0007).** Re-runs
  the full resolver each start, so a smaller-but-present GPU would be silently
  downgraded and the config would again become "a lie" — exactly what ADR-0007
  rejected. We only guard the absent-GPU crash; we never re-tier a GPU that is
  present.
- **Session fallback to the CPU tier, config untouched (chosen).** The machine
  starts and transcribes, the user keeps their pinned values, and they are told
  once why they're on CPU so the degradation is never silent.

## Consequences

- `HardwareTierResolver` gains a pure `reconcile(*, device, model, compute_type,
  profile)` method returning `(ResolvedHardware, did_fall_back)`. It is added
  without reshaping `resolve` or the `_TIER_TABLE`, as ADR-0007 anticipated.
- Reconcile guards **only** the `device == "cuda"` + `not cuda_available` case.
  A `cpu` config never falls back; a `cuda` config on a CUDA machine is returned
  unchanged. There is no VRAM re-tiering — a present GPU is never second-guessed.
- The unchanged path returns a `"configured"`-tier `ResolvedHardware` carrying
  the config's own values, so the daemon threads one effective
  `(model, device, compute_type)` triple into `FasterWhisperBackend` whether or
  not a fallback happened.
- On fallback the daemon logs a `warning` and surfaces exactly one tray
  notification ("Running on CPU"), scheduled just after the Qt event loop starts
  (a balloon needs a visible icon and a running loop). The config file on disk
  is byte-for-byte unchanged.
- Like the rest of the resolver, the reconcile logic is unit tested; the daemon
  wiring and Qt notification are manual-QA only (excluded from pyright/tests).
