# Handoff — Fix the macOS #161 freeze for good: native AVAudioEngine capture (option D)

**Your mission:** build the production **native macOS microphone-capture backend
(`MacAudioCapture`, AVAudioEngine via PyObjC)** that deletes the PortAudio/CoreAudio
stop deadlock, drop it into the capture seam **already merged on `main`** (PR #183),
write the ADR, clean up, and drive a final real-Mac QA. **Option D is already
decided and spike-proven on the affected hardware — do NOT re-litigate B vs D.**

This is an **AFK build session**: implement end-to-end, keep pure logic unit-tested
and native adapters manual-QA (the project's architecture seam), run `/code-review`,
open a PR to `main`. The one thing you cannot do on Windows is verify the native
backend at runtime — that's a **real-Mac QA** step (§6), same remote-proxy loop the
spike used.

---

## 1. The bug and why D (settled — don't reopen)

The macOS "first-dictation freeze" (#161) is a **PortAudio ↔ CoreAudio HAL deadlock
in `audio_capture.stop()`** on hotkey-release, triggered by concurrent CPU load
(the load-on-arm model load racing the audio IO thread). It is a PortAudio-on-macOS
library bug — **not fixable in-app, only avoidable** — and **macOS-only** (Windows'
MME/WASAPI host APIs have no such lock inversion). Full root cause, the A/B evidence,
and the options ladder (A/B/C/**D**) are in
`docs/diagnostics/dictatem-161-FIX-PACKAGE-20260630/RESOLUTION.md` (§1 cause, §4
options) — read §4 for the deep context.

**Option D** replaces PortAudio on macOS with Apple's **AVAudioEngine** behind the
existing `AudioCapture` protocol. It **deletes the deadlock class entirely** (no
`Pa_StopStream`), **restores per-dictation mic-off** (privacy), and **keeps Windows
on sounddevice** (cross-platform). Option **B** (keep-open + idle-close;
`…/fix/keepopen-idleclose-fix.patch`) is the **reserve interim only** — you should
not need it.

## 2. Spike PROOF — D is viable (don't re-run to decide; this is settled)

A throwaway AVAudioEngine harness was run on the **affected machine class: Apple M3,
macOS 26.5 (25F71), arm64, pyobjc 12.2.1, Python 3.12.13** — the same environment
where the freeze reproduces. All four unknowns PASS:

- **(b) No deadlock under load — PASS.** 11 start/stop cycles across 3 runs under a
  **real faster-whisper model load** → **0 deadlocks** (10 s watchdog never fired).
  PortAudio was **2/100 unbounded hangs** under this exact load class; AVAudioEngine
  **0/11**. `stop()` latency is bounded — usually ~10–40 ms, **max observed 1.45 s**
  under active concurrent model load (see §4e — this matters).
- **(c) Mic off between dictations — PASS.** Human confirmed the menu-bar mic
  indicator on a gapped run: *"off during gaps, on during recording."*
- **(d) TCC Microphone prompt — PASS.** Fired on first run, granted. **Open item:**
  the prompt fired under a terminal/uv identity; **verify it fires under the real
  packaged-`.app`/launchd identity before ship** (the ADR-0014 `python3.12`-label
  issue — grants attach to the running binary).
- **(a) Capture + resample intelligible — PASS.** Word-for-word transcript match
  (48 kHz native → linear-interp resample to 16 kHz → faster-whisper).

**De-risked details for the build:**
- The one fiddly PyObjC line — reading `floatChannelData()` — **worked first try via
  the PRIMARY slice-read** `np.array(chan[:frames])` on pyobjc 12.2.1. No
  ctypes/buffer-protocol fallback needed.
- **Native input rate varied on the same machine (44.1 kHz vs 48 kHz across runs)** →
  the backend **must read the rate from the input node's format at `start()`**, never
  hard-code it.
- Spike used linear-interp resampling (fine for the spike); **production wants a
  proper resampler** (AVAudioConverter or a polyphase filter) for anti-aliasing.

## 3. What's already on `main` (the seam you build on — PR #183)

The capture seam was de-leaked so D is a small, contained swap:

- **`_PlatformAdapters.make_audio_capture`** (`daemon.py:1549`) — a per-platform
  `(Config, AudioBuffer) -> AudioCapture` factory. Field + docstring at
  `daemon.py:1514`.
- **`_make_sounddevice_capture`** (`daemon.py:1563`) — the Windows/macOS factory today.
- The shared **`AudioBuffer` is constructed in `_run_daemon` and injected** into the
  backend (`daemon.py:1810`); the daemon reads level/idle off it (no more
  `capture._buffer` reach-through). `AudioBuffer` (`src/dictatem/audio/buffer.py`) is
  now thread-safe (snapshot-under-lock).
- **The ONE line to change:** `_start_macos_daemon` (`daemon.py:2181`) currently
  passes `make_audio_capture=_make_sounddevice_capture` (`daemon.py:2252`) → swap to
  your `_make_macaudio_capture`. **Windows (`daemon.py:2169`) stays on sounddevice.**
- **`close()` was intentionally deferred to you** — it was cut from the de-leak
  because wiring an unguarded PortAudio `stop()` into shutdown re-introduced the very
  deadlock. With AVAudioEngine (and Windows MME) it's now safe to add — see §4c.

## 4. Build plan

Reference implementation to mirror: `src/dictatem/audio/sounddevice_capture.py`
(the protocol shape) + the spike
`docs/diagnostics/dictatem-161-FIX-PACKAGE-20260630/spike-macaudiocapture/mac_audio_spike.py`
(the working AVAudioEngine calls: `installTapOnBus_bufferSize_format_block_`,
`outputFormatForBus_`, `floatChannelData`, `removeTapOnBus_` + `engine.stop()`).

### 4a. `MacAudioCapture` — new `src/dictatem/audio/macaudio_capture.py`
- Implements `AudioCapture`: `start()`, `stop() -> AudioChunk`, `close()`.
- Takes the injected `AudioBuffer` (required, like `SoundDeviceCapture`), and appends
  resampled 16 kHz mono float32 to it from the tap block. The daemon's
  level/duration/idle reads then work unchanged.
- **Read the native rate from `inputNode.outputFormatForBus_(0)` at `start()`** (it
  varies — see §2). Resample native → 16 kHz in the tap or on flush.
- Lazy-import PyObjC (`from AVFoundation import AVAudioEngine` inside a function, like
  the other `mac_*` native adapters) so `dictatem.daemon` stays importable on any OS
  (`test_import_safety` / the pyright + ruff `mac_*` exclusions in `pyproject.toml`).
- Handle the Microphone TCC path (same permission bucket as today).

### 4b. Resampler — new, **pure and unit-tested**
- native-rate mono float32 → 16 kHz mono float32. Prefer a **pure implementation**
  (numpy polyphase / good linear+filter) in its own module so it's CI-testable on
  every platform and **shareable with the Windows WASAPI switch (#184)**, which needs
  the identical "capture native-rate → resample to 16 kHz". (AVAudioConverter is the
  Apple-native alternative but isn't unit-testable off-device.)
- Unit tests: rate pairs (44100→16000, 48000→16000, 16000→16000 passthrough), length
  correctness, a tone's frequency preserved, silence stays silence.

### 4c. Re-add `close()` — now safe on both platforms
- Add `close()` back to the `AudioCapture` protocol (`interfaces.py`, after `stop()`)
  + `tests/fakes/fake_audio.py` + the `test_interfaces`/`test_fakes` asserts (see the
  reverted diff in PR #183 history for the exact shape).
- Implement in `SoundDeviceCapture` (re-add the `_close_stream()` helper) and
  `MacAudioCapture` (`removeTapOnBus_` + `engine.stop()`; idempotent).
- **Re-wire the shutdown release** in `_run_daemon` (the `try/finally: audio_capture.
  close()` around `app.exec()`). This is now safe: macOS runs AVAudioEngine
  (deadlock-free) and Windows runs MME (never deadlocked). This closes the deferral.

### 4d. Wire it
- Add `_make_macaudio_capture(config, buffer)` next to `_make_sounddevice_capture`
  (lazy-imports `MacAudioCapture`).
- `_start_macos_daemon`: `make_audio_capture=_make_macaudio_capture` (the one line).
- Update `TestStarterAdapterSets::test_macos_starter_…` (`tests/test_daemon.py`) to
  assert `adapters.make_audio_capture is daemon._make_macaudio_capture`.

### 4e. The one real design decision — `stop()` on the Qt main thread
`_do_transcribe` (`daemon.py:604`) calls `audio_capture.stop()` on the **Qt main
thread**. AVAudioEngine `stop()` is deadlock-free but **bounded up to ~1.45 s under
concurrent model load** — and load-on-arm means the cold **first** dictation is
exactly when the model is still loading at release, so the slow case is the common
one on the first dictation. A ~1.45 s main-thread block is a brief UI hitch (overlay/
tray), **not** a freeze — already an infinite improvement over the unbounded deadlock.
Decide one of:
- **(i) Accept the bounded hitch** — simplest; ship it, revisit only if it annoys.
- **(ii) Return the audio immediately, tear the engine down async** — `stop()` flushes
  the (already-buffered) audio and returns instantly, and does `removeTap`/`engine.
  stop()` on a worker (safe — AVAudioEngine can't deadlock, unlike PortAudio where the
  RESOLUTION found worker-placement didn't help). Costs a ~1 s lingering mic-off.
- **(iii) Move the whole `stop()` call off the main thread** in `_do_transcribe` (a
  shared change; Windows `stop()` is fast so it's harmless there).

**Recommendation:** ship **(i)** first (correctness over polish — the freeze is
gone), and note (ii)/(iii) as a follow-up if the first-dictation hitch is felt in QA.
Don't block the fix on it. Grill it with the user if you want a firm call.

## 5. Cleanup (part of "once and for all")

- **ADR** — new `docs/adr/` (next free number), sibling to **ADR-0013** (macOS
  transcription engine). Record: the decision (D), the considered-and-rejected options
  (A keep-open-only, B keep-open+idle-close, C revert load-on-arm), the consequences
  (native mac backend behind the protocol; Windows unchanged; bounded-not-instant
  stop; rate-at-start; resampler; the TCC-under-launchd open item), and that
  **v0.6.2-rc1/v0.6.2 misdiagnosed the layer** (ctranslate2 theory — superseded).
- **Preserve the rest of the #161 fix-package (optional).** `RESOLUTION.md` and
  `spike-macaudiocapture/` (spike + agent runbook) are **already committed** with this
  handoff. Still **untracked** and carrying machine paths — **this repo is PUBLIC**, so
  sanitize or omit: the `audio-repro/` harness + logs, the `round4-sample*.txt` stack
  dumps, `ORIGINAL-REPORT-superseded-…md`, and the B patch
  `fix/keepopen-idleclose-fix.patch`. These are reference/reserve, not required for the
  build — preserve them sanitized or leave them local, your call.
- **Reconcile the superseded work.** The failed-QA warm-up + stall-watchdog live on
  branch `fix/macos-coldstart-deadlock-161` + tags `v0.6.2-rc1`/`v0.6.2` (pushed to
  origin). They are **NOT on `main`** (the de-leak branched off clean `origin/main`),
  so main is unaffected — but delete/annotate the stale branch and note the
  superseded tags. Keep the `ctranslate2>=4.7,<4.8` pin if you re-apply anything (good
  hygiene, unrelated to the cause).
- **#161 / load-on-arm.** With D, per-dictation `stop()` is safe again, so load-on-arm
  no longer creates instability — **keep the latency win.** Confirm in the ADR.
- **Roadmap.** Update the ledger + Current Session Prompt when you hand off.

## 6. QA — final real-Mac verification (Mac-gated, remote-proxy)

You author on Windows; a person on a real Mac runs the QA. **Reuse the runbook
pattern** — `docs/diagnostics/dictatem-161-FIX-PACKAGE-20260630/spike-macaudiocapture/
MAC-AGENT-RUNBOOK.md` is the template (a self-contained agent runbook that prompts the
human, collects evidence, and zips it back). Write the equivalent for the **real
`MacAudioCapture` in the daemon** (not the standalone spike). It must confirm, on a
real Mac, observably (not from logs alone — #93's lesson):
1. **No freeze on the cold first dictation** (hotkey → speak → release, with
   load-on-arm loading the model *during* recording) — the original repro. Repeat ×N.
2. **Records → transcribes → pastes** correctly (regular dictation).
3. **Mic indicator turns off between dictations** (per-dictation release).
4. **TCC Microphone prompt fires + works under the packaged-`.app`/launchd identity**
   (the §2 open item — the one thing the spike didn't cover).
5. Back-to-back + a long (~30 s) dictation (exercise the buffer/lock live).

**Do not merge / do not claim macOS PASS without the human confirming the observable
behaviour** (roadmap rule).

## 6b. Getting this version onto the Mac + releasing it

**The installer already has a QA path — use it.** `install.sh` installs Dictatem
from a git ref's release *tarball*, and the **`DICTATEM_REF`** env override installs
any branch/tag/SHA instead of the pinned tag (it adds `--force --refresh-package
dictatem` so uv doesn't serve a stale cached copy of a moving branch). So once your
D branch is pushed, the Mac tester installs the **real daemon build** with one line:

```sh
curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/<D-branch>/install.sh \
  | DICTATEM_REF=<D-branch> sh
```

This `uv tool install`s `dictatem[runtime]` on managed CPython 3.12, generates the
`Dictatem.app` identity shell (`dictatem --install-macos-app`), and starts the daemon
under **launchd** — so it exercises the **real `.app`/launchd TCC identity**, which is
the one QA item the standalone spike could NOT cover (§2 (d)). **This install path is
how you close that gap** — the TCC prompt the tester sees here is the production one.

**The loop** (you on Windows, tester on the Mac — remote proxy, per §6):
1. Push the D branch; hand the tester the one-liner above.
2. Point them at a QA runbook you write for the **installed daemon** (model it on
   `spike-macaudiocapture/MAC-AGENT-RUNBOOK.md`, but drive the real hotkey→dictate→
   paste flow, not the standalone spike). Build on the existing macOS tester guide
   `docs/agents/qa-handoffs/08-s10-macos-tester-guide.md`.
3. They run it, confirm the observable checks (§6), zip the evidence back.
4. **On PASS → close #161** on that evidence.

**Cutting the release (on QA PASS):** follow the established flow (`chore(release):
vX.Y.Z` commits + tags). **Bump the pin in BOTH `install.sh` (`DICTATEM_TAG`, ~line
49) and `install.ps1`, and the README install one-liner URL, together** —
`tests/test_install_python_pin.py` guards the pins from drifting. Tag `vX.Y.Z`, cut a
`gh release`, and the README `curl …/vX.Y.Z/install.sh | sh` now serves the fix to
everyone. Frame it as the **macOS-audio fix that deletes the PortAudio dependency on
macOS** (RESOLUTION §4D), superseding the misdiagnosed v0.6.2.

## 7. Key files & symbols (current `main`)

- Protocol: `src/dictatem/interfaces.py:142` `AudioCapture` (`start`/`stop`; add `close`).
- Windows backend to mirror: `src/dictatem/audio/sounddevice_capture.py`.
- Pure buffer (thread-safe): `src/dictatem/audio/buffer.py`.
- Seam: `daemon.py` — `_PlatformAdapters.make_audio_capture:1549`,
  `_make_sounddevice_capture:1563`, injection `:1810`, `_start_macos_daemon:2181`
  (swap line `:2252`), `_start_windows_daemon` swap `:2169`.
- Main-thread stop() call: `_do_transcribe` `daemon.py:604`.
- Starter construction test: `tests/test_daemon.py::TestStarterAdapterSets`.
- Spike + runbook + RESOLUTION: `docs/diagnostics/dictatem-161-FIX-PACKAGE-20260630/`.

## 8. Definition of Done + guardrails

- [ ] `MacAudioCapture` + a pure, unit-tested resampler; `close()` re-added + wired;
      macOS starter swapped; Windows untouched (only `SoundDeviceCapture` caller).
- [ ] `pytest` + `pyright` + `ruff` green; native `mac_*` bits in the pyright/ruff
      exclusion + import-safety lists as needed.
- [ ] `/code-review` run on the diff; PR to `main` (branch per issue).
- [ ] **ADR written**; fix-package preserved (sanitized); superseded branch/tags
      reconciled; roadmap updated.
- [ ] **Real-Mac QA PASS** (§6) — recorded by a human; #161 closed on that evidence.

**Guardrails:** don't re-litigate D. Don't reintroduce an unguarded blocking `stop()`
on a backend that can deadlock. Keep Windows on sounddevice. Keep the pure-logic /
native-adapter test seam. Don't hard-code the input sample rate. The freeze fix is
the win — don't let the `stop()`-latency polish (§4e) block shipping it.
