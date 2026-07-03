# macOS captures audio natively via AVAudioEngine, not PortAudio

The macOS "first-dictation freeze" (#161) is a **PortAudio ↔ CoreAudio HAL
deadlock in `audio_capture.stop()`**. When the hotkey is released,
`SoundDeviceCapture.stop()` runs `Pa_StopStream` on the Qt main thread, which
blocks on the CoreAudio HAL device mutex and deadlocks against the audio IO
thread (a classic AB/BA lock inversion inside PortAudio's CoreAudio host API).
It is a **PortAudio-on-macOS library bug we cannot fix in-app, only avoid**, and
it is **macOS-only** — Windows' MME/WASAPI host APIs have no such lock inversion.
Full root cause, stacks, and the A/B/C/D option ladder are in
[`RESOLUTION.md`](../diagnostics/dictatem-161-FIX-PACKAGE-20260630/RESOLUTION.md)
(§1 cause, §4 options).

The bug is **latent**: it needs concurrent CPU load to race the IO thread. A
standalone repro on the affected Mac (Apple M3, macOS 26.5) hangs **2 / 100**
stop cycles under a real model load, and never in a quiet process (**0 / 300**).
That is why it regressed at v0.6.0: load-on-arm ([ADR-0025](0025-cold-start-load-on-arm-fetch-on-first-run.md))
starts the faster-whisper load — and its ctranslate2 thread pool — *during*
recording, so the pool is resident and active exactly when `stop()` runs on
release. v0.5.x loaded the model *after* stop, in a quiet process, so the race
was never observed.

## Decision

**On macOS, capture the microphone with Apple's `AVAudioEngine` (via PyObjC),
behind the existing `AudioCapture` protocol.** A new
[`MacAudioCapture`](../../src/dictatem/audio/mac_audio_capture.py) installs an
input-node tap, resamples each native-rate buffer to 16 kHz mono float32, and
appends it to the shared `AudioBuffer`; `stop()` removes the tap and stops the
engine. There is **no `Pa_StopStream` on any code path**, so the deadlock class
is **deleted, not merely avoided**. **Windows keeps `SoundDeviceCapture`
(sounddevice/PortAudio)** unchanged — it never deadlocked, and the swap is
per-platform in `_start_macos_daemon` (option D was made a one-line factory
change by the [PR #183](0018-cross-platform-input-and-foreground-neutral-identities.md)
seam de-leak: a `make_audio_capture` factory + an injected, thread-safe
`AudioBuffer`).

Resampling is done by a **pure numpy polyphase resampler**
([`resampler.py`](../../src/dictatem/audio/resampler.py)), not by Apple's
`AVAudioConverter`. Downsampling 44.1/48 kHz to 16 kHz is a >2× decimation, so
content above the 8 kHz destination Nyquist must be low-pass filtered out or it
aliases into the speech band; a windowed-sinc polyphase FIR does the filtering
and rate change in one rational `L/M` step. Keeping it pure means it is
**unit-testable on every CI platform** (an on-device `AVAudioConverter` is not)
and **shared with the Windows WASAPI switch (#184)**, which needs the identical
"native rate → 16 kHz" path.

This decision **restores per-dictation mic release on macOS** — the engine stops
between dictations, so the menu-bar mic indicator turns off when not recording —
without the always-on-mic cost of the keep-open reserve.

## Considered options

- **(D) Native AVAudioEngine capture on macOS (chosen).** Deletes the PortAudio
  HAL stop path entirely, so the deadlock class is gone rather than contained;
  restores per-dictation mic-off with no keep-open; keeps Windows on sounddevice.
  Spike-proven viable on the **affected hardware** (Apple M3 / macOS 26.5 /
  pyobjc 12.2.1): **0 / 11 deadlocks** under a real faster-whisper load (PortAudio
  was 2 / 100 *unbounded* hangs), mic-off between dictations, the Microphone TCC
  prompt fires, and a captured-then-resampled clip transcribed word-for-word.
  Cost: a new native code path with audio-format/threading nuance and more QA —
  bounded because it sits behind the existing protocol and only swaps the macOS
  backend.
- **(A) Keep-open only.** Open the PortAudio stream once for the daemon's life
  and never stop it per dictation, so `Pa_StopStream` never runs on the hot
  path. Simplest and robust, but the **mic indicator stays lit whenever the
  daemon runs** — an always-on-mic trust cost we won't ship as the default.
- **(B) Keep-open + idle-close.** (A) plus releasing the stream after an idle
  window so the mic indicator eventually turns off. Validated safe on the
  affected Mac (idle-close runs in a quiet process, 0 / 300, behind a watchdog).
  **Kept as the reserve interim** — but the mic still stays on *during* an active
  back-to-back session, and it leaves the buggy PortAudio path in place rather
  than removing it. The implemented patch lives in the #161 fix-package
  (`fix/keepopen-idleclose-fix.patch`), unshipped.
- **(C) Revert load-on-arm (#161).** Go back to lazy load-on-worker so the model
  isn't resident at stop time and the race is rare again (as in v0.5.x). Only
  makes the bug **rare, not gone** (other incidental CPU load can still trigger
  it) and **loses the load-on-arm latency win** — the cold first dictation would
  again wait ~6 s instead of hiding the load behind speech. Rejected as a fix;
  with (D) the per-dictation `stop()` is safe again, so load-on-arm no longer
  creates instability and its latency win is **kept** (ADR-0025 stands).
- **`AVAudioConverter` for resampling (rejected in favour of the pure numpy
  resampler).** The Apple-native converter is idiomatic but **cannot be
  unit-tested off-device** and could not be shared with the Windows WASAPI path
  (#184). The pure polyphase resampler is CI-testable and cross-platform; the
  small extra DSP code is worth the testability and reuse.
- **Status quo — unguarded PortAudio `stop()` on macOS.** The freeze itself.
  This is also why `AudioCapture.close()` was deliberately deferred from the #183
  de-leak: wiring an unguarded `Pa_StopStream` into daemon shutdown re-introduced
  the deadlock. With (D) it is safe to add back (see Consequences).

## Consequences

- **A native macOS capture backend now sits behind `AudioCapture`.** The daemon
  is unchanged — it reads level/duration/idle off the injected `AudioBuffer` and
  calls `start()`/`stop()`/`close()` without knowing which backend it got. The
  backend is manual-QA / real-Mac-QA only, like the other `mac_*` adapters, and
  excluded from pyright; the CI-testable logic is the pure resampler. The new
  `pyobjc-framework-AVFoundation` dependency is Darwin-gated so the macOS CI leg
  proves the wheel resolves and the `AVAudioEngine` binding imports.
- **Windows is untouched.** `SoundDeviceCapture` remains the only sounddevice
  caller; the switch is per-platform.
- **`stop()` is bounded, not instant.** AVAudioEngine `stop()` is deadlock-free
  but can take up to ~1.5 s under active concurrent model load (usually
  ~10–40 ms). It runs on the Qt main thread (`_do_transcribe`), and because
  load-on-arm means the cold first dictation is exactly when the model is still
  loading at release, that slow case is the *common* one on the first dictation.
  A ~1.5 s main-thread block is a brief UI hitch (overlay/tray), **not** a freeze
  — an infinite improvement over the unbounded deadlock. We ship this as-is;
  moving the teardown off the main thread (return the buffered audio immediately,
  tear the engine down on a worker — safe precisely because AVAudioEngine cannot
  deadlock) is a noted follow-up if the first-dictation hitch is felt in QA.
- **The native input rate is read at `start()`, never hard-coded.** The same
  machine reported 44.1 kHz and 48 kHz across runs, so `MacAudioCapture` reads
  `inputNode.outputFormatForBus_(0)` and builds a fresh resampler each `start()`.
- **The resampler streams.** It appends 16 kHz to the shared buffer *as each tap
  block arrives* (not only at flush), so the live level/duration/idle reads work
  during recording; carried filter state makes the per-block output identical to
  a single whole-signal call (a pinned unit test).
- **`AudioCapture.close()` is re-added and wired into daemon shutdown.** Deferred
  from #183, now safe on both backends (AVAudioEngine cannot deadlock; Windows
  MME never did). It is idempotent and distinct from `stop()`.
- **Open item — TCC under the packaged identity.** The spike confirmed the
  Microphone (TCC) prompt fires, but under a terminal/uv identity. Grants attach
  to the running binary ([ADR-0014](0014-macos-permissions-and-app-identity-shell.md)),
  so real-Mac QA must confirm the prompt fires and works under the packaged
  `Dictatem.app` / launchd identity before ship — the one thing the standalone
  spike could not cover.
- **v0.6.2-rc1 misdiagnosed the layer.** It attributed the freeze to a
  ctranslate2 cross-thread issue and added a model warm-up; at freeze time every
  ctranslate2 thread is idle and inference never starts. The warm-up added
  concurrent CPU and could only *worsen* the real (PortAudio) race. `v0.6.2-rc1`
  is superseded by this ADR; no final `v0.6.2` was released. The unrelated
  `ctranslate2>=4.7,<4.8` pin from that work is fine to keep as hygiene.
