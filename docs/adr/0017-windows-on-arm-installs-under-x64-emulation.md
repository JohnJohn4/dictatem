# Windows on ARM installs under x64 emulation, not native ARM64

Dictatem advertised "Windows support" but was **x64-only in practice** — a user's
Windows-on-ARM (ARM64 / Snapdragon-class) machine failed the one-line install.
The wall is the transcription engine: `ctranslate2` (pulled by `faster-whisper`)
ships **no `win_arm64` wheel** and is **wheel-only (no sdist)**, so on a *native*
ARM64 interpreter there is nothing to install or build. And on Windows on ARM,
[`uv`](https://docs.astral.sh/uv/) provisions a **native ARM64 CPython by
default**, so the existing [thin install script](0011-install-via-thin-uv-tool-script.md)
silently lands on the one interpreter where the engine cannot run.

**Decision:** on ARM64, `install.ps1` pins an **x64 CPython**
(`cpython-3.11-windows-x86_64`) for the tool environment and lets the whole stack
run under Windows' built-in x64 emulation (Prism). Every dependency works there:
`ctranslate2`, `faster-whisper`, `sounddevice` and `PySide6` all resolve from
their `win_amd64` wheels and run. This was verified end-to-end on a Snapdragon X
laptop — model load, Faster-Whisper transcription, and clipboard paste all
succeed; the user dictated four sentences with zero errors.

This is the **same shape** the macOS engine ADR
([0013](0013-macos-transcription-engine.md)) and the tarball-transport ADR
([0015](0015-install-from-tag-tarball-not-git-url.md)) take: a platform concern
solved entirely inside the provisioning script, with **no new transcription code
and no change to the running daemon**.

## No application-code change is needed

`sounddevice` selects its bundled PortAudio binary from `platform.machine()`. On
a *native* ARM64 interpreter that is `ARM64`, so it loads `libportaudioarm64.dll`
— which then failed to load (`error 0x7e`) on the test machine. On an **x64**
interpreter `platform.machine()` reports `AMD64`, so `sounddevice` loads
`libportaudio64bit.dll` on its own and succeeds. Pinning the x64 interpreter
therefore fixes audio capture as a side effect — no monkeypatch, no env shim, no
edit to `audio/sounddevice_capture.py`.

The [Hardware Tier](0007-hardware-tier-resolved-on-first-run.md) logic is **left
untouched**. The NVIDIA probe + `HardwareTierResolver` already pick the tier from
detected CUDA/VRAM, architecture-agnostic; a Snapdragon has no NVIDIA GPU, so it
resolves to a CPU tier on its own. We deliberately do **not** add an `if ARM →
CPU` branch — only `install.ps1` is arch-aware, and only for Python selection.

## Considered options

- **Pin an x64 CPython and run under emulation (chosen).** A ~30-line, ARM-only
  branch in `install.ps1`; the x64 and GPU paths are a byte-for-byte no-op (the
  added `--force`/`--python` arguments expand to nothing off ARM). Ships today
  with zero engine work. The cost is emulation overhead — transcription runs at
  roughly 1.5× real-time on a Snapdragon X (e.g. ~5 s of compute for ~3.5 s of
  audio), slower than native but well within usable for dictation.
- **Native ARM64 now.** The proper long-term path (full-speed, no emulation), but
  blocked solely on a `ctranslate2 win_arm64` wheel that does not exist on PyPI
  and is not published by the usual community source (cgohlke's `win_arm64-wheels`
  is Python-3.13-only and omits `ctranslate2`). Deferred, not abandoned.
- **Build `ctranslate2` from source for ARM64.** Removes the wheel gap but needs
  a CMake + MSVC ARM64 toolchain and a BLAS on the user's machine, which breaks
  the signed-wheels-only thin-script posture (ADR-0011) the same way `whisper.cpp`
  did for macOS (ADR-0013). Rejected for the install path.
- **Swappable transcription backend with an arm64-friendly engine (ADR-0013).**
  The clean architectural escape hatch — add a backend that *has* arm64 wheels
  rather than forcing CTranslate2, mirroring the planned `mlx-whisper` move on
  Mac. The right home for native ARM64 when we pursue it; out of scope for this
  install-only fix.

## Consequences

- `install.ps1` detects ARM64 via `PROCESSOR_ARCHITECTURE` / `PROCESSOR_ARCHITEW6432`
  and pins `cpython-3.11-windows-x86_64`. Re-running over a prior failed
  native-ARM64 attempt is handled with `--force` (it overwrites the stale
  launcher). The x64/GPU path is unchanged.
- **GPU acceleration on ARM is not feasible today** regardless — NVIDIA's
  Windows-on-ARM drivers are nascent and the CUDA wheel stack
  (`ctranslate2` CUDA build, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) has no
  `win_arm64` builds. This is an external limitation, not encoded in our logic; if
  those land, the existing GPU path resolves on its own.
- Re-running the installer while the daemon is **running** still hits the tool-dir
  lock (the daemon's interpreter holds `…\dictatem\Scripts`) — the same friction
  tracked for uninstall as #69. First installs are unaffected (nothing is running
  yet); the broader "stop the daemon before (re)install" fix stays with #69.
- Native ARM64 remains a future follow-up via the swappable backend (ADR-0013).

## Amendment (2026-06-22): interpreter version aligned to the project-wide pin (#90)

The original decision pinned `cpython-3.11-windows-x86_64`. The `3.11` carried
**no arch- or wheel-specific rationale** — it was the example value from #78's
strategy notes; the Snapdragon QA validated the *stack* (`ctranslate2` 4.7.2,
`faster-whisper` 1.2.1, `sounddevice` 0.5.5, `PySide6` 6.11.1), none of which is
3.11-bound (all ship `cp312` x64 wheels too).

As of #90 the pinned minor version is **3.12**, matching `install.sh` and the
macOS pin so the whole project shares one managed interpreter. `install.ps1` now
also pins on **x64** (`--managed-python --python 3.12`); previously x64 let `uv`
discover any PATH Python ≥3.11 — the same interpreter-discovery hazard
(`python.org` 3.14+ → missing-wheel resolution failures, or an untested
interpreter) that #90 closes. The pinned versions are kept inside the CI matrix
and `tests/test_install_python_pin.py` asserts every installer pin appears there,
so the version can no longer silently drift.

**Consequence:** like macOS, an x64 install now has `uv` *fetch* a managed CPython
(from the same GitHub host the pinned tarball already requires) instead of reusing
a discovered system Python. `DICTATEM_PYTHON` chooses the version, but there is no
opt-out back to a discovered interpreter — the accepted trade-off for a
reproducible install (ADR-0011/0015). The one regression is an air-gapped /
strict-proxy x64 box that previously installed against a pre-existing local Python;
an opt-out env var could be added later if that case shows up in the wild.

Native ARM64 (the real fix, via ADR-0013's swappable backend) remains the
follow-up; until then the x64-under-emulation pin simply tracks the shared
version. The ARM bump 3.11 → 3.12 is reasoned-safe and CI-tested but **not yet
re-verified on real ARM hardware** (no device on hand) — re-run the Snapdragon
smoke test when one is available.
