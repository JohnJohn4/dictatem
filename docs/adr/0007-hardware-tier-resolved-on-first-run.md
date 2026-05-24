# Hardware Tier is resolved once on first run, config authoritative thereafter

Dictatem must run on machines from a 16 GB NVIDIA desktop down to a CPU-only
laptop, but the transcription model, compute device, and compute type must be
chosen *together* (e.g. `float16` is GPU-only; `large-v3-turbo` OOMs a small
GPU). So on **first run only** — when no `config.toml` exists — we probe the
hardware (CUDA presence via CTranslate2, VRAM via `nvidia-ml-py`) and write
concrete values for the chosen [Hardware Tier](../../CONTEXT.md#hardware-tier)
into the config. On every later launch the config file is **authoritative**: we
do not re-probe and never overwrite the user's values.

We chose bake-once over re-resolving each launch because it is predictable
(what's in the file is what runs) and never silently undoes a user's tuning.
The cost is that swapping hardware later requires editing or deleting the
config — an accepted trade-off.

## Consequences

- Two machines legitimately end up with different `model.name`; this is
  expected, not a bug.
- A config carried to a weaker machine (or a removed GPU) would request a
  device that no longer exists. To avoid a hard crash, startup includes a
  **non-crashing guard**: if the configured device is unavailable, fall back to
  the CPU tier for that session and log it once, without editing the file.
- `tiny` is never auto-selected; `base` is the smallest automatic Tier.
- Instead of repeated warnings, a single per-session tip is shown when the
  measured real-time factor is poor ("transcriptions are slow; a smaller model
  may help").
