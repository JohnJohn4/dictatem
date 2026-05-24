# Hardware Tier is resolved once on first run and baked into the config

The [Hardware Tier](../../CONTEXT.md#hardware-tier) is resolved exactly once —
on first run, when no `~/.dictatem/config.toml` exists. A `HardwareProbe`
inspects the machine (CUDA presence via `ctranslate2.get_cuda_device_count()`,
total VRAM via `nvidia-ml-py`), a pure table-driven `HardwareTierResolver` maps
the resulting `HardwareProfile` to concrete `(whisper model, device,
compute_type)` plus a Transform (Ollama) tag, and those concrete values are
written into the config file. Every later launch reads that file unchanged; the
probe is never consulted again.

## Considered Options

- **Probe on every launch and pick the tier at runtime.** Re-detects hardware
  each start, so a GPU that disappears (eGPU unplugged, driver crash) silently
  re-tiers the user down without their knowledge, and the user has no single
  place to see or override what was chosen. Detection cost (NVML init) is paid
  on every start. Worse, it makes the config a lie: `[model].name` in the file
  would not be what actually runs.
- **Resolve once and bake into config (chosen).** The probe runs only when
  there is no config to read. The resolved tier becomes ordinary config the
  user can read, tune, and round-trip like any other setting. A machine with a
  hand-edited config is authoritative — the resolver never second-guesses it.
- **Ship `device = "cuda"` as a static default and let faster-whisper fall
  back.** This is the pre-#36 behaviour. faster-whisper does not transparently
  fall back from CUDA to CPU; on a CPU-only machine it raises at model load and
  the daemon never transcribes. The default has to be resolved, not guessed.

Baking-on-first-run was chosen because it makes the chosen tier visible and
overridable, keeps the steady-state launch path free of native probing, and
lets a CPU-only machine start and transcribe out of the box.

## Consequences

- `ModelConfig` gains a `device` field (default `"cuda"`) that is now written
  to the config. Before #36 the daemon constructed `FasterWhisperBackend`
  without a `device`, so it was always `cuda`; the daemon now threads
  `config.model.device` through.
- `load_config(path, probe=...)` takes an optional `HardwareProbe`. With a
  probe and no file, it probes once, resolves, logs the tier
  (`Detected <gpu>, <vram> -> tier <tier>: <model>/<device>/<compute>`), and
  writes concrete values. Without a probe (e.g. unit tests) it writes plain
  defaults. With an existing file it reads it unchanged and never probes.
- `HardwareTierResolver` is pure (no Qt/win32/native imports) and fully unit
  tested across every tier boundary via `FakeHardwareProbe`. The native
  `NvidiaHardwareProbe` is manual-QA only and excluded from pyright/tests, like
  the other native adapters.
- The VRAM thresholds (3 GB, 6 GB) are tunable, not contractual. Changing them
  only affects machines that have no config yet; existing users are unaffected.
- This ADR deliberately does **not** cover reconciling a stale baked config
  against the current machine (e.g. a config baked on a GPU now running on
  CPU). That crash-guard / reconcile-on-startup behaviour is a separate slice
  (#39). `HardwareTierResolver` is shaped so a `reconcile(config_values,
  profile)` method can be added without reshaping it.
