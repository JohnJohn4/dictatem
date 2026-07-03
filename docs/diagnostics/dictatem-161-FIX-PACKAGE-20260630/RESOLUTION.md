# RESOLUTION — Dictatem macOS first-dictation freeze (#161)

**Status: ROOT CAUSE CONFIRMED. A fix (keep-open + idle-close) is implemented and validated
on the affected Mac (Apple M3, macOS 26.5) — but please weigh the option ladder in §4 before
committing; the maintainer/owner explicitly wants all options on the table.**
Date 2026-06-30. Supersedes the ctranslate2 cross-thread theory in the original runbook/REPORT
and the `v0.6.2-rc1` fix (both misdiagnosed the layer — see §1).

---

## 1. Root cause (CONFIRMED by a live native sample, 2× identical, + a standalone repro)

A **PortAudio ↔ CoreAudio HAL deadlock in `audio_capture.stop()`** when the hotkey is
released. **Not** a ctranslate2/OpenMP issue — at freeze time every ctranslate2 thread is
idle and inference never starts.

`SoundDeviceCapture.stop()` (called on the Qt main thread by `_do_transcribe`) calls
`self._stream.stop()` → **`Pa_StopStream`**, which blocks on the CoreAudio HAL device mutex
and deadlocks against the audio IO thread (AB/BA inversion):

```
MAIN thread:  _do_transcribe -> audio_capture.stop() -> Pa_StopStream
  -> FinishStoppingStream (libportaudio) -> AudioOutputUnitStop
  -> HALC_ProxyIOContext::StopIOProc -> HALB_Mutex::Lock() -> __psynch_mutexwait   [BLOCKED]
IO thread (com.apple.audio.IOThread.client):
  IOWorkLoop -> startStopCallback (libportaudio)
  -> AudioUnitGetProperty -> std::recursive_mutex::lock() -> __psynch_mutexwait   [BLOCKED]
```
sounddevice 0.5.5, PortAudio V19.7.0-devel. Dumps: `round4-sample.txt`, `round4-sample-2.txt`.

**Why it was misdiagnosed:** the only prior signal was the log (`Model loaded` → silence, no
`Processing audio`), which is identical whether the worker is stuck in `transcribe()` or the
main thread is stuck in `audio.stop()` *before the worker spawns*. No live stack existed until
this QA. The 180-iteration ctranslate2 stress never reproduced it because it fed numpy arrays
and never used the mic/PortAudio path.

**Why it regressed at 0.6.0 (load-on-arm, #161):** the PortAudio stop deadlock is latent and
needs *concurrent CPU load* to trigger (it races the IO thread). #161 loads the model — and
its ~8–10-thread ctranslate2 pool — *during* recording, so that pool is resident/active when
`audio.stop()` runs on release. 0.5.6 loaded the model *after* stop (quiet process) → the race
was never observed. The `v0.6.2-rc1` warm-up adds even more concurrent CPU and can worsen it.

---

## 2. Reproduction & evidence (standalone, on the affected Mac)

Harness `audio-repro/audio_stop_repro.py` drives a real `sd.InputStream` start→teardown cycle,
one cycle per fresh process, watchdog = exit 7 if teardown hangs >10s:

| teardown call | thread | concurrent load | deadlock rate | meaning |
|---|---|---|---|---|
| `Pa_StopStream` (`.stop()`) | main | model | **2 / 100** | the bug |
| `Pa_AbortStream` (`.abort()`) | main | model | **2 / 198** | abort is NOT a fix |
| `Pa_StopStream` (`.stop()`) | worker | model | **2 / ~90** | thread placement irrelevant |
| `Pa_StopStream`+close | main | **none** | **0 / 300** | quiet process is safe → idle-close OK |
| **keep-open fix** (real patched class) | — | model | **0 / 100** | hot path can't deadlock |
| **idle-close** (real patched class) | — | model+idle | **8 / 8 clean** | mic released, reopen works |

Dumps: `audio-repro/deadlock-*.log`, summaries `audio-repro/stress-audio-*.log`,
validations `audio-repro/validate-keepopen.log`, `audio-repro/validate-idle-close.log`.

---

## 3. PROPOSED FIX (implemented + validated): keep-open + idle-close

`audio/sounddevice_capture.py` — patch **`fix/keepopen-idleclose-fix.patch`** (git-applies to
v0.6.2-rc1, +115/−22; full file `fix/sounddevice_capture.py.patched`):

- The `InputStream` is opened **once** and kept open. `start()` re-arms a `_recording` flag;
  `stop()` just disarms + flushes the buffer — **no `Pa_StopStream`/`Pa_AbortStream`/`close`
  on the dictation hot path**, so it provably cannot deadlock there.
- To avoid keeping the mic indicator lit forever, the stream is **closed after `idle_close_s`**
  of no dictation (defaults to `config.model.idle_unload_minutes`). The idle close runs **off
  the hotkey path, in a quiet process** (where stop()+close() is 0/300), **behind a 5s
  watchdog** that drops the stream reference first — so even a rare hang can't wedge the daemon
  and the next dictation reopens a fresh stream.

**Validated in-app** (patched daemon, launchd): cold dictation → no freeze; **mic indicator
turns OFF ~60s after last dictation** (`Idle: releasing the microphone after 60s`); next
dictation **reopens** and transcribes; repeat. Logs: `qa-inapp-keepopen-log.txt`,
`phase2-rounds.log`.

**Residual items for the implementer (small):**
- Wire `SoundDeviceCapture.close()` into daemon shutdown.
- `AudioBuffer` has no lock; `stop()` disarms before flush so the callback returns early, but a
  boundary callback could append one chunk — same concurrency class the code already has
  (overlay reads levels while the callback appends). Add a `threading.Lock` to `AudioBuffer`
  for strictness.
- `start()` reuses an existing stream; add a liveness check to reopen if the stream ever dies.
- Drop the `v0.6.2-rc1` warm-up (wrong layer; adds latency, may worsen the race). **Keep** the
  `ctranslate2>=4.7,<4.8` pin (good hygiene, unrelated).

---

## 4. OPTIONS CONSIDERED — please weigh before committing

The true bug is a **PortAudio-on-CoreAudio library bug** we can't cleanly fix in-app; we can
only choose how to avoid/contain it. Ladder, shallow → deep:

### (A) Keep-open only
Stream open for the daemon's life; never close per dictation. Robust, simplest. **Cost: mic
indicator lit whenever the daemon runs (always).** Rejected as the shipping default because of
the always-on-mic trust cost.

### (B) Keep-open + idle-close — **PROPOSED (§3)**
Adds idle release so the mic indicator turns off when not in use. Robust on the hot path;
idle-close validated safe (0/300 in a quiet process) and watchdog-guarded. **Cost:** mic stays
on *during an active session* between back-to-back dictations (released after the idle window);
a tiny residual idle-close hang risk, contained by the watchdog. Modest extra code.

### (C) Reconsider load-on-arm (#161)
Revert to lazy load-on-worker (0.5.x): the model isn't resident at stop time, so `audio.stop()`
runs in a quiet process and the race is ~never (as in 0.5.x). **This is a product call, and only
makes the bug rare again — it does NOT eliminate it** (other incidental load could still trigger
it). **Cost:** loses the load-on-arm latency win — the first dictation after launch/idle waits
~6s for the cold load instead of hiding it behind talking. Could be combined with (B) as
defense-in-depth, or shipped instead of (B) if the maintainer decides #161 isn't worth its
instability. Note #161 is also what caused the original misdiagnosis.

### (D) DEEPEST — replace PortAudio with native CoreAudio capture (recommended if eliminating the bug class)
Stop using sounddevice/PortAudio for mic capture **on macOS** and capture via Apple's own
**AVFoundation `AVAudioEngine`** (or Audio Queue Services) through **PyObjC** (already a
dependency — `pyobjc-framework-AVFoundation`/`Cocoa`). This removes the buggy PortAudio HAL
stop path entirely, so per-dictation start/stop becomes safe again (mic off when idle, no
keep-open needed) and the whole deadlock class disappears.

Sketch (behind the existing `AudioCapture` protocol, so the daemon is unchanged):
```
engine = AVAudioEngine.alloc().init()
input  = engine.inputNode()
fmt    = input.outputFormatForBus_(0)                 # native HW format
input.installTapOnBus_bufferSize_format_block_(0, 1024, None, tap_block)
#   tap_block(AVAudioPCMBuffer, AVAudioTime): pull float samples -> resample 16k mono -> buffer
engine.startAndReturnError_(None)                     # start
...
input.removeTapOnBus_(0); engine.stop()               # stop — no PortAudio, no HAL deadlock
```
Implementation notes / cost:
- New `MacAudioCapture` adapter implementing the same `start()/stop()->np.ndarray` contract;
  keep `SoundDeviceCapture` for Windows. Wire by platform in `_start_macos_daemon`.
- Convert the tap's native-rate float buffers to **16 kHz mono float32** (AVAudioConverter or a
  light resampler) to match `SAMPLE_RATE`. Handle the PyObjC block signature + buffer pointer
  access (`buffer.floatChannelData()`), and Microphone TCC (same prompt as today).
- **Pros:** eliminates the PortAudio deadlock permanently; per-dictation device open/close;
  mic off when idle with no keep-open; fewer bundled-C surprises. **Cons:** new code path +
  audio-format/threading nuances, more QA, a larger change than (B). Lower-risk than it sounds
  because it sits behind the existing capture protocol and only swaps the macOS backend.

**Recommendation:** ship **(B)** now (validated, low-risk, fixes the freeze and the mic
concern), and schedule **(D)** as the durable follow-up to delete the PortAudio dependency on
macOS. Treat **(C)/#161** as an independent product decision about latency-vs-stability.

---

## 5. How to apply + QA
```bash
git checkout -b fix/macos-audio-stop-deadlock v0.6.2-rc1   # or off main
git apply fix/keepopen-idleclose-fix.patch
# QA: kickstart -> cold first dictation (×N) + back-to-back reuse; then idle ~idle_unload_minutes
#     and confirm the mic indicator turns off + log shows "Idle: releasing the microphone".
```
PASS = `Processing audio → Transcription complete → Paste: sent` with **no** silent gap after
`Model loaded`, across cold starts AND reuse; mic released on idle; reopen works.
```
