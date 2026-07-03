#!/usr/bin/env python3
"""THROWAWAY SPIKE — native macOS mic capture via AVAudioEngine (option D, #161).

Goal: retire the RESOLUTION.md §4 unknowns on a REAL Mac *before* writing the
production ``MacAudioCapture``. It answers four questions the Windows dev box
cannot:

  (a) does an AVAudioEngine tap capture intelligible audio, resampled to the
      16 kHz mono float32 the rest of Dictatem expects?  (--transcribe proves it)
  (b) does per-dictation start/stop stay deadlock-FREE under concurrent model
      load — the exact condition that wedges PortAudio's Pa_StopStream today?
      (--cycles N --load model; a watchdog force-exits 7 on any hang)
  (c) does the mic turn OFF between dictations (engine.stop() releases it)?
  (d) does the macOS Microphone TCC prompt fire under the running identity?
      (first run should prompt; see README-SPIKE.md for the launchd/.app note)

This is NOT production code. It deliberately mirrors the shape the real backend
will take behind the existing ``AudioCapture`` protocol (start / stop -> np, and
a close()), so a clean spike ports almost directly. It does its resample in
numpy (spike-grade linear interp — Whisper is robust to it); production should
use AVAudioConverter / a polyphase resampler for anti-aliasing quality.

Run:  uv run --with pyobjc-framework-AVFoundation --with numpy \
          [--with faster-whisper] python mac_audio_spike.py --cycles 5 --load model --transcribe
See README-SPIKE.md for the full command block + what to paste back.
"""
from __future__ import annotations

import argparse
import faulthandler
import os
import sys
import threading
import time

import numpy as np

try:
    # AVAudioEngine is the whole point of the spike; fail loudly + helpfully.
    from AVFoundation import AVAudioEngine
except Exception as exc:  # noqa: BLE001
    sys.stderr.write(
        f"Could not import AVFoundation ({exc!r}).\n"
        "Install PyObjC's AVFoundation binding, e.g.:\n"
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

    ⚠️ THE #1 THING TO VERIFY ON-DEVICE. floatChannelData() is a
    ``float * const *`` (one pointer per deinterleaved channel). PyObjC usually
    lets you slice the channel-0 pointer directly; if the PRIMARY line raises,
    comment it out and try FALLBACK A or B (one of these three works — which one
    is exactly the PyObjC detail this spike exists to pin down).
    """
    chan = mbuf.floatChannelData()[0]  # type: ignore[attr-defined]
    # PRIMARY: PyObjC slices a typed C pointer into a Python sequence of floats.
    return np.array(chan[:frames], dtype=np.float32)
    # FALLBACK A (ctypes view — zero-copy then copy):
    #   import ctypes
    #   arr = (ctypes.c_float * frames).from_address(int(chan))
    #   return np.frombuffer(arr, dtype=np.float32).copy()
    # FALLBACK B (PyObjC buffer protocol):
    #   return np.frombuffer(chan.as_buffer(frames * 4), dtype=np.float32).copy()


class MacAudioSpike:
    """Shaped like the real backend will be: start() / stop()->np / close().

    One persistent engine; start()/stop() per dictation install/remove the tap
    and start/stop the engine — so stop() releases the mic (question c) and
    a later start() re-arms cleanly (question b, reuse).
    """

    def __init__(self) -> None:
        self._engine = AVAudioEngine.alloc().init()
        self._input = self._engine.inputNode()
        self._native_fmt = self._input.outputFormatForBus_(0)
        self.src_rate = float(self._native_fmt.sampleRate())
        self._chunks: list[np.ndarray] = []
        self._tapped = False

    def start(self) -> None:
        self._chunks = []

        def tap(mbuf, when):  # noqa: ANN001, ARG001 — PyObjC block (AVAudioPCMBuffer, AVAudioTime)
            frames = int(mbuf.frameLength())
            if frames:
                self._chunks.append(_read_channel0(mbuf, frames))

        self._input.installTapOnBus_bufferSize_format_block_(0, 4096, self._native_fmt, tap)
        self._tapped = True
        ok, err = self._engine.startAndReturnError_(None)
        if not ok:
            raise RuntimeError(
                f"AVAudioEngine.start failed: {err!r} — if this is a permission "
                "denial, grant Microphone access (see README-SPIKE.md TCC note) "
                "and re-run."
            )

    def stop(self) -> np.ndarray:
        """End one dictation: remove the tap, stop the engine (mic OFF), return 16k audio."""
        if self._tapped:
            self._input.removeTapOnBus_(0)
            self._tapped = False
        self._engine.stop()
        native = (
            np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
        )
        self._chunks = []
        return resample_to_16k(native, self.src_rate)

    def close(self) -> None:
        if self._tapped:
            self._input.removeTapOnBus_(0)
            self._tapped = False
        self._engine.stop()


def _start_load(kind: str, busy: int, stop_evt: threading.Event) -> list[threading.Thread]:
    """Concurrent CPU during recording — the load-on-arm / warm-up proxy that
    makes PortAudio's stop deadlock fire (see audio-repro/audio_stop_repro.py)."""
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
            except Exception:  # noqa: BLE001 — best-effort load proxy
                pass
        t = threading.Thread(target=_load, daemon=True)
        t.start()
        threads.append(t)
    return threads


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycles", type=int, default=5, help="per-dictation start/stop cycles")
    ap.add_argument("--record-ms", type=int, default=1500, help="record duration per cycle")
    ap.add_argument("--load", choices=("model", "numpy", "none"), default="model",
                    help="concurrent CPU during recording (deadlock trigger; 'model' is closest)")
    ap.add_argument("--busy", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="a stop() that exceeds this IS a deadlock -> dump stacks, exit 7")
    ap.add_argument("--transcribe", action="store_true",
                    help="run faster-whisper on the last cycle's audio to prove intelligibility")
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
        time.sleep(args.record_ms / 1000.0)  # "talking"

        # Teardown under a watchdog — the exact spot PortAudio wedges. Expect it
        # to stay well under --timeout on AVAudioEngine (no HAL stop deadlock).
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
        _teardown()  # main thread, like the daemon does it
        stop_evt.set()
        dt_ms = (time.time() - t0) * 1000.0
        audio = result["audio"]
        last_audio = audio
        rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
        print(
            f"cycle {i}/{args.cycles}: stop={dt_ms:6.1f}ms  "
            f"samples={audio.size:6d}  ~{audio.size / SAMPLE_RATE:4.1f}s  rms={rms:.4f}  "
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
        f"\nPASS: {args.cycles} cycles, no deadlock, mic released each stop().\n"
        "-> D is viable: build MacAudioCapture(config, buffer) behind the "
        "AudioCapture protocol and wire it in _start_macos_daemon's "
        "make_audio_capture (see the audio-capture-seam refactor).",
        flush=True,
    )
    os._exit(0)  # avoid any atexit interaction with CoreAudio teardown


if __name__ == "__main__":
    main()
