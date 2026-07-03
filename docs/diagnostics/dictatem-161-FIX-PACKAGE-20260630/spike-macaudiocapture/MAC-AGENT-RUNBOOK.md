# Dictatem #161 — macOS native-audio-capture spike · AGENT RUNBOOK

> **You are a Claude Code agent running on a macOS device.** This is a
> self-contained runbook. Follow it top to bottom: set up, run one automated
> harness, drive a few **manual** steps with the human at the keyboard, then
> package all evidence into a **zip** the human sends back. You do not need any
> other file — the spike script is embedded in Step 2.

---

## 0. What this is and why (enough to interpret results)

Dictatem's macOS "first-dictation freeze" (#161) is a **PortAudio ↔ CoreAudio
HAL deadlock** in `audio_capture.stop()` under concurrent CPU load — a library
bug we can only *avoid*. The chosen fix (**option D**) is to stop using
PortAudio on macOS and capture natively via Apple's **AVAudioEngine** (PyObjC).

**Your job: prove option D is viable — or find the blocker — before anyone
writes production code.** You'll run a throwaway AVAudioEngine capture harness
that mirrors the real backend's shape (`start` / `stop`→samples / `close`) and
answer four questions:

| ID | Question | How it's answered |
|----|----------|-------------------|
| **b** | No deadlock under concurrent model load? | 5 start/stop cycles under a real faster-whisper load; a watchdog force-exits `7` on any hang. **This is the crux** — PortAudio hit 2/100 here. |
| **c** | Mic released between dictations? | Human watches the menu-bar mic indicator across cycles. |
| **d** | Microphone TCC prompt fires? | First run should raise the macOS permission prompt. |
| **a** | Capture + resample intelligible? | Transcribe a spoken sentence, compare to what was said. |

## 1. Ground rules (important)

- **This is a real device. NEVER record a manual step as PASS without the human
  confirming what they SAW / HEARD.** Logs alone are not enough.
- If a command errors, **capture the exact error text** — do not paper over it.
  A `DEADLOCK` + stack dump (exit 7) is a *real result*, not a failure to fix.
- **Keep every output.** You will zip the whole working directory at the end.
- Talk to the human in plain language. When you need them to do something
  physical (speak, watch an indicator, click Allow), **stop and ask**, then wait
  for their reply before continuing.

## 2. Set up the working directory + write the spike

```bash
mkdir -p ~/dictatem-161-spike && cd ~/dictatem-161-spike
```

Write this file **exactly** as `mac_audio_spike.py` in that directory:

```python
#!/usr/bin/env python3
"""THROWAWAY SPIKE — native macOS mic capture via AVAudioEngine (option D, #161)."""
from __future__ import annotations

import argparse
import faulthandler
import os
import sys
import threading
import time

import numpy as np

try:
    from AVFoundation import AVAudioEngine
except Exception as exc:  # noqa: BLE001
    sys.stderr.write(
        f"Could not import AVFoundation ({exc!r}). Install the PyObjC binding:\n"
        "  uv run --with pyobjc-framework-AVFoundation --with numpy python "
        "mac_audio_spike.py ...\n"
    )
    raise SystemExit(2) from exc

SAMPLE_RATE = 16_000  # dictatem.types.SAMPLE_RATE — the contract the buffer expects


def resample_to_16k(samples: np.ndarray, src_rate: float) -> np.ndarray:
    """Native-rate mono float32 -> 16 kHz mono float32 (spike-grade linear interp)."""
    if samples.size == 0 or int(round(src_rate)) == SAMPLE_RATE:
        return samples.astype(np.float32, copy=False)
    n_dst = int(round(samples.size * SAMPLE_RATE / src_rate))
    if n_dst <= 0:
        return np.zeros(0, dtype=np.float32)
    x_src = np.linspace(0.0, 1.0, num=samples.size, endpoint=False)
    x_dst = np.linspace(0.0, 1.0, num=n_dst, endpoint=False)
    return np.interp(x_dst, x_src, samples).astype(np.float32)


def _read_channel0(mbuf: object, frames: int) -> np.ndarray:
    """Pull `frames` float samples of channel 0 out of an AVAudioPCMBuffer.

    THE #1 THING TO VERIFY ON-DEVICE. If the PRIMARY line raises, comment it out
    and try FALLBACK A or B (one of the three works — noting which is a real
    deliverable for the production port).
    """
    chan = mbuf.floatChannelData()[0]  # type: ignore[attr-defined]
    return np.array(chan[:frames], dtype=np.float32)  # PRIMARY
    # FALLBACK A (ctypes):
    #   import ctypes
    #   arr = (ctypes.c_float * frames).from_address(int(chan))
    #   return np.frombuffer(arr, dtype=np.float32).copy()
    # FALLBACK B (buffer protocol):
    #   return np.frombuffer(chan.as_buffer(frames * 4), dtype=np.float32).copy()


class MacAudioSpike:
    """Shaped like the real backend: start() / stop()->np / close()."""

    def __init__(self) -> None:
        self._engine = AVAudioEngine.alloc().init()
        self._input = self._engine.inputNode()
        self._native_fmt = self._input.outputFormatForBus_(0)
        self.src_rate = float(self._native_fmt.sampleRate())
        self._chunks: list[np.ndarray] = []
        self._tapped = False

    def start(self) -> None:
        self._chunks = []

        def tap(mbuf, when):  # noqa: ANN001, ARG001 — PyObjC block
            frames = int(mbuf.frameLength())
            if frames:
                self._chunks.append(_read_channel0(mbuf, frames))

        self._input.installTapOnBus_bufferSize_format_block_(0, 4096, self._native_fmt, tap)
        self._tapped = True
        ok, err = self._engine.startAndReturnError_(None)
        if not ok:
            raise RuntimeError(
                f"AVAudioEngine.start failed: {err!r} — if this is a permission "
                "denial, grant Microphone access and re-run."
            )

    def stop(self) -> np.ndarray:
        if self._tapped:
            self._input.removeTapOnBus_(0)
            self._tapped = False
        self._engine.stop()
        native = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
        self._chunks = []
        return resample_to_16k(native, self.src_rate)

    def close(self) -> None:
        if self._tapped:
            self._input.removeTapOnBus_(0)
            self._tapped = False
        self._engine.stop()


def _start_load(kind: str, busy: int, stop_evt: threading.Event) -> list[threading.Thread]:
    threads: list[threading.Thread] = []
    if kind == "numpy":
        def _busy() -> None:
            x = np.random.default_rng().standard_normal((192, 192)).astype(np.float32)
            while not stop_evt.is_set():
                x = (x @ x) * 1e-3 + 0.1
        for _ in range(busy):
            t = threading.Thread(target=_busy, daemon=True)
            t.start()
            threads.append(t)
    elif kind == "model":
        def _load() -> None:
            try:
                from faster_whisper import WhisperModel
                m = WhisperModel("base", device="cpu", compute_type="int8")
                list(m.transcribe(np.zeros(8000, dtype=np.float32), language="en")[0])
            except Exception:  # noqa: BLE001
                pass
        t = threading.Thread(target=_load, daemon=True)
        t.start()
        threads.append(t)
    return threads


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycles", type=int, default=5)
    ap.add_argument("--record-ms", type=int, default=1500)
    ap.add_argument("--load", choices=("model", "numpy", "none"), default="model")
    ap.add_argument("--busy", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--transcribe", action="store_true")
    args = ap.parse_args()
    faulthandler.enable()

    spike = MacAudioSpike()
    print(f"native input format: {spike.src_rate:.0f} Hz -> resampling to {SAMPLE_RATE} Hz",
          flush=True)

    last_audio = np.zeros(0, np.float32)
    for i in range(1, args.cycles + 1):
        stop_evt = threading.Event()
        spike.start()
        load = _start_load(args.load, args.busy, stop_evt)
        time.sleep(args.record_ms / 1000.0)

        done = threading.Event()
        result: dict[str, np.ndarray] = {}

        def _teardown() -> None:
            result["audio"] = spike.stop()
            done.set()

        def _watchdog() -> None:
            if not done.wait(args.timeout):
                sys.stderr.write(
                    f"\n!!! DEADLOCK: stop() cycle {i} exceeded {args.timeout:.0f}s "
                    f"(load={args.load}) — AVAudioEngine should NOT do this !!!\n"
                )
                sys.stderr.flush()
                faulthandler.dump_traceback(all_threads=True)
                os._exit(7)

        threading.Thread(target=_watchdog, name="watchdog", daemon=True).start()
        t0 = time.time()
        _teardown()
        stop_evt.set()
        dt_ms = (time.time() - t0) * 1000.0
        audio = result["audio"]
        last_audio = audio
        rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
        print(
            f"cycle {i}/{args.cycles}: stop={dt_ms:6.1f}ms  samples={audio.size:6d}  "
            f"~{audio.size / SAMPLE_RATE:4.1f}s  rms={rms:.4f}  "
            f"{'(SILENT? check mic grant)' if rms < 1e-4 else 'audio OK'}",
            flush=True,
        )
        for t in load:
            t.join(timeout=1.0)

    spike.close()

    if args.transcribe and last_audio.size:
        print("\ntranscribing last cycle to prove capture+resample are intelligible...",
              flush=True)
        try:
            from faster_whisper import WhisperModel
            m = WhisperModel("base", device="cpu", compute_type="int8")
            segs, _ = m.transcribe(last_audio, language="en")
            text = " ".join(s.text for s in segs).strip()
            print(f'  TRANSCRIPT: "{text}"', flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  (transcribe skipped: {exc!r})", flush=True)

    print(
        f"\nPASS: {args.cycles} cycles, no deadlock, mic released each stop().",
        flush=True,
    )
    os._exit(0)


if __name__ == "__main__":
    main()
```

## 3. Capture the environment

```bash
{ echo "=== date ==="; date;
  echo "=== macOS ==="; sw_vers;
  echo "=== chip ==="; sysctl -n machdep.cpu.brand_string; uname -m;
  echo "=== python ==="; uv run python -V 2>/dev/null || python3 -V;
  echo "=== pyobjc / deps ==="; uv run --with pyobjc-framework-AVFoundation python -c "import AVFoundation, objc; print('pyobjc', objc.__version__)" 2>&1;
} | tee env.txt
```

## 4. Run the tests (drive the human on the **manual** parts)

### Test b + c + d — deadlock-under-load, mic-off, TCC prompt

**Before running, tell the human:**
> "I'm about to run 5 recording cycles under CPU load. **Please speak a few words
> during each cycle.** Also **watch your menu-bar microphone indicator** (the
> orange dot / Control-Center 'microphone in use'): tell me afterwards whether it
> **turned off between cycles** and back on. And if a **'…would like to access
> the Microphone' prompt** appears, click **Allow** and tell me it appeared."

Then run (first run triggers the TCC prompt):

```bash
uv run --with pyobjc-framework-AVFoundation --with numpy --with faster-whisper \
    python mac_audio_spike.py --cycles 5 --record-ms 1500 --load model 2>&1 | tee test-bcd.log
```

**Interpret / record:**
- **b PASS** = 5 `cycle …: stop=…ms` lines, each stop time small (ms–tens of ms, never near 10000), **no** `DEADLOCK`, final `PASS`. If exit 7 + a stack dump → **b FAIL** (D does not clear the deadlock class) — keep the full dump.
- **c** = whatever the human reports about the mic indicator turning off/on.
- **d** = whether the human saw + granted the Microphone prompt. If `AVAudioEngine.start failed` mentions permission, have them grant Microphone (System Settings ▸ Privacy & Security ▸ Microphone; add the terminal/uv/python if needed), then re-run this command.

### Test a — capture + resample intelligible

**Tell the human:**
> "Now record one ~4-second clip. When I say go, **say clearly: 'the quick brown
> fox jumps over the lazy dog'** (or any sentence you'll remember), then stop."

Run:

```bash
uv run --with pyobjc-framework-AVFoundation --with numpy --with faster-whisper \
    python mac_audio_spike.py --cycles 1 --record-ms 4000 --load none --transcribe 2>&1 | tee test-a.log
```

**a PASS** = the `TRANSCRIPT:` line matches (roughly) what the human said, and the
cycle line shows `audio OK` (not `SILENT?`). Ask the human to confirm the
transcript matches what they spoke.

### If `_read_channel0` raises

The `floatChannelData()` read is the one likely-fiddly PyObjC line. If the
PRIMARY line raises, edit `mac_audio_spike.py`: comment the PRIMARY `return` and
uncomment FALLBACK A, re-run; if that also fails, try FALLBACK B. **Note which
fallback worked in the findings** — that's a real deliverable.

## 5. Write the findings

Create `FINDINGS.md` in the working directory and fill it in from what actually
happened (paste real log lines + the human's words — do not invent):

```markdown
# Dictatem #161 macOS AVAudioEngine spike — findings

- Date / device / macOS / chip: <from env.txt>
- pyobjc / python: <from env.txt>
- floatChannelData read used: PRIMARY / FALLBACK A / FALLBACK B

## (b) No deadlock under load — PASS / FAIL
<paste the 5 cycle lines; note max stop time; note any DEADLOCK dump>

## (c) Mic released between dictations — PASS / FAIL / UNSURE
<the human's exact words about the menu-bar mic indicator>

## (d) TCC Microphone prompt — PASS / FAIL / N/A
<did it appear? under what identity (uv/python/terminal)? granted?>

## (a) Capture + resample intelligible — PASS / FAIL
Spoken: "<what the human said>"
TRANSCRIPT: "<the transcript line>"
<match? any garbling?>

## Verdict
D looks viable / D is blocked because <...>. Notes for the production port: <...>
```

## 6. Package everything and hand back

```bash
cd ~/dictatem-161-spike
ZIP="dictatem-161-spike-$(date +%Y%m%d-%H%M).zip"
zip -r "$ZIP" FINDINGS.md env.txt test-bcd.log test-a.log mac_audio_spike.py
echo "Created: $(pwd)/$ZIP"
```

Then tell the human:
> "Done. I've packaged everything into **`~/dictatem-161-spike/<ZIP name>`**.
> Please send that zip back to the person who gave you this runbook."

**If any test could not be run or any manual step is unconfirmed, say so
explicitly in FINDINGS.md and to the human — an honest 'not verified' beats a
guessed PASS.**
