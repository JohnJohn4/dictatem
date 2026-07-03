# Spike — native macOS mic capture (AVAudioEngine), option D / #161

**Throwaway.** Proves (or kills) RESOLUTION.md §4's **option D** — replacing
PortAudio with Apple's AVAudioEngine on macOS — *before* any production code.
Run it on a **real Mac** (the Windows dev box can't). If it passes, the next
session builds `MacAudioCapture` behind the existing `AudioCapture` protocol and
wires it into `_start_macos_daemon`'s new `make_audio_capture` factory (the
`audio-capture-seam` refactor already opened that seam — the swap is one line).

The spike is shaped like the real backend will be: `start()` / `stop() -> np` /
`close()`, resampling the tap to **16 kHz mono float32** (the `AudioBuffer`
contract). It reuses the `audio-repro/` harness's deadlock watchdog: a `stop()`
that hangs >`--timeout` dumps all thread stacks and exits **7**.

---

## Prerequisites
- A Mac with a microphone (Apple Silicon ideally — the affected M3 box).
- `uv` (or any Python 3.11+ with `pip`). No repo install needed — the command
  pulls the two deps inline.
- For `--transcribe` / `--load model`: network on first run (faster-whisper
  fetches the `base` model once), or a warm HF cache.

## The command block (copy-paste; relay output verbatim)

```bash
cd docs/diagnostics/dictatem-161-FIX-PACKAGE-20260630/spike-macaudiocapture

# (b)+(c)+(d) — the core test: 5 per-dictation start/stop cycles under REAL
# concurrent model load (the load-on-arm condition that wedges PortAudio today).
# Talk during each cycle. First run should raise the macOS Microphone prompt.
uv run --with pyobjc-framework-AVFoundation --with numpy --with faster-whisper \
    python mac_audio_spike.py --cycles 5 --record-ms 1500 --load model

# (a) — capture+resample correctness: record ~4s, then transcribe it.
# Say a known sentence; confirm the TRANSCRIPT line matches what you said.
uv run --with pyobjc-framework-AVFoundation --with numpy --with faster-whisper \
    python mac_audio_spike.py --cycles 1 --record-ms 4000 --load none --transcribe
```

If `AVAudioEngine.start failed` mentions permission, grant Microphone (below),
then re-run. If a cycle prints `DEADLOCK` + a stack dump (exit 7), that is a
real result — **paste the whole dump**; it would mean D does *not* clear the
deadlock class and we fall back to B.

## What each question needs (tick + paste evidence)

- [ ] **(b) No deadlock under load** → all 5 cycles print `stop=…ms` (expect a
      few ms–tens of ms, never near 10 000), **no** `DEADLOCK`, final line
      `PASS`. *Paste the 5 cycle lines.* This is the crux: PortAudio hit
      2/100 here; AVAudioEngine should be 0.
- [ ] **(c) Mic released between dictations** → watch the macOS **menu-bar mic
      indicator** (orange dot / Control Center "microphone in use"): it should
      turn **off** after each cycle's `stop()` and back on at the next `start()`.
      *Report what you saw.*
- [ ] **(d) TCC prompt fires** → first ever run raises **"…would like to access
      the microphone"**. *Report: did it prompt? Under what identity?* (see note)
- [ ] **(a) Capture + resample correct** → the `--transcribe` run prints a
      `TRANSCRIPT:` line matching your spoken sentence, and cycle lines show
      `audio OK` (rms > 0), never `SILENT?`. *Paste the transcript + a cycle line.*

## macOS TCC / identity note (why (d) matters)

Microphone grants attach to the **binary that asks**. Run ad-hoc like above and
the prompt attaches to the `uv`/`python` interpreter — fine for the spike. But
the shipped daemon runs under **launchd**, and grants only stick to the
generated **`Dictatem.app`** identity (ADR-0014; the `python3.12` label issue).
So a clean spike here proves the *API* works; production must still confirm the
prompt fires **under the `.app`/launchd identity** — verify AVAudioEngine uses
the same `NSMicrophoneUsageDescription` / Microphone TCC bucket the current
sounddevice path does. Flag this for the production wiring.

## If `_read_channel0` raises (the one likely-fiddly line)

`floatChannelData()` pointer access is the single PyObjC detail the Windows box
can't pin down. `mac_audio_spike.py::_read_channel0` ships the PRIMARY idiom and
two commented FALLBACKs — if the primary raises, swap to A or B and note which
one worked (that's a real deliverable for the production port).

## On result
- **PASS** (no deadlock, mic releases, audio transcribes) → D is viable. Next:
  build `MacAudioCapture(config, buffer)` behind `AudioCapture`, swap it into
  `_start_macos_daemon`'s `make_audio_capture`, keep Windows on sounddevice,
  add the resampler (production: AVAudioConverter/polyphase), write the ADR.
- **FAIL** (deadlock persists, or capture unreliable) → fall back to option **B**
  (keep-open + idle-close; patch in `../fix/keepopen-idleclose-fix.patch`) as
  the interim freeze-stopper and reassess. Paste the failing output.
