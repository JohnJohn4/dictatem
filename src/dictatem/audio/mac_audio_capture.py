"""MacAudioCapture — native macOS microphone capture via AVAudioEngine (PyObjC).

This is option D for the macOS first-dictation freeze (#161): it replaces the
sounddevice/PortAudio backend *on macOS only* with Apple's AVAudioEngine, which
has no ``Pa_StopStream`` and so **cannot** hit the PortAudio<->CoreAudio HAL stop
deadlock that wedges the first dictation under concurrent model load
(``docs/adr/0027-*`` / RESOLUTION.md §4D). Windows stays on sounddevice.

Like the other native adapters (``mac_hook``, ``mac_clipboard``, …) this module
binds PyObjC at import and only works on macOS — it is manual-QA / real-Mac-QA
only, never imported by pure-core code, and excluded from pyright (the
AVFoundation binding resolves only on macOS). The daemon lazy-imports it through
``_make_macaudio_capture`` so ``dictatem.daemon`` stays importable on any OS.
All CI-testable logic lives in the pure ``resampler`` module, which carries the
unit tests; this file is the thin AVAudioEngine glue the spike proved out.

Shape mirrors :class:`~dictatem.audio.sounddevice_capture.SoundDeviceCapture`:
constructed once with the loaded ``Config`` and the shared ``AudioBuffer``, then
``start()`` / ``stop()`` per dictation and ``close()`` at shutdown. The tap block
resamples each native-rate CoreAudio buffer to 16 kHz and appends it to the
shared buffer as it arrives, so the daemon's live level/duration/idle reads work
during recording exactly as they do for the sounddevice backend.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import numpy as np

from dictatem.audio.resampler import PolyphaseResampler
from dictatem.exceptions import AudioCaptureError

if TYPE_CHECKING:
    from dictatem.audio.buffer import AudioBuffer
    from dictatem.config import Config

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac_audio_capture requires macOS")

from AVFoundation import AVAudioEngine  # noqa: E402  (after the platform guard)

_TAP_BUFFER_FRAMES = 4096


def _read_channel0(mbuf: object, frames: int) -> np.ndarray:
    """Pull ``frames`` float samples of channel 0 out of an AVAudioPCMBuffer.

    ``floatChannelData()`` is a ``float * const *`` (one pointer per
    deinterleaved channel). The spike confirmed the PRIMARY slice-read works
    first-try on pyobjc 12.2.1 (#161 §2); if a future PyObjC ever rejects it,
    the two commented fallbacks are the known-good alternatives.
    """
    chan = mbuf.floatChannelData()[0]  # type: ignore[attr-defined]
    return np.array(chan[:frames], dtype=np.float32)
    # FALLBACK A (ctypes view, then copy):
    #   import ctypes
    #   arr = (ctypes.c_float * frames).from_address(int(chan))
    #   return np.frombuffer(arr, dtype=np.float32).copy()
    # FALLBACK B (PyObjC buffer protocol):
    #   return np.frombuffer(chan.as_buffer(frames * 4), dtype=np.float32).copy()


class MacAudioCapture:
    """Per-dictation mic capture on one persistent AVAudioEngine.

    One engine is created up front; each ``start()`` installs an input tap and
    starts the engine, each ``stop()``/``close()`` removes the tap and stops the
    engine — so the mic is released *between* dictations (the privacy win the
    sounddevice keep-open reserve would have lost), and a later ``start()``
    re-arms cleanly. AVAudioEngine ``stop()`` is bounded, not unbounded like
    ``Pa_StopStream`` under load, so it is safe on the Qt main thread.
    """

    def __init__(self, config: Config, buffer: AudioBuffer) -> None:
        # Target rate the rest of Dictatem expects; the native input rate is read
        # fresh at each start() (it varies run-to-run — #161 §2).
        self._target_rate = config.audio.sample_rate
        # Shared with the daemon: the tap appends resampled 16 kHz here and the
        # daemon reads level/idle/duration off it. Injected (required), never
        # self-made, so both sides provably share ONE buffer — see
        # SoundDeviceCapture for why a private buffer would silently break the
        # level pill / silence-timeout / max-duration reads.
        self._buffer = buffer
        self._engine = AVAudioEngine.alloc().init()
        self._input = self._engine.inputNode()
        self._tapped = False
        self._resampler: PolyphaseResampler | None = None
        # Hold a reference to the live tap block for its lifetime so PyObjC does
        # not GC the Python closure while CoreAudio still calls it.
        self._tap_block: object | None = None

    def start(self) -> None:
        # Read the CURRENT native input format — the hardware default rate can
        # differ between dictations (44.1 vs 48 kHz seen on one machine, #161 §2),
        # so both the tap format and the resampler are rebuilt each start().
        native_fmt = self._input.outputFormatForBus_(0)
        src_rate = float(native_fmt.sampleRate())
        self._resampler = PolyphaseResampler(src_rate, self._target_rate)
        resampler = self._resampler
        buffer = self._buffer

        def tap(mbuf, when):  # noqa: ANN001, ARG001 — PyObjC block (AVAudioPCMBuffer, AVAudioTime)
            # Runs on a CoreAudio realtime thread, not the Qt main thread. Only
            # this thread touches the resampler; the buffer is thread-safe.
            frames = int(mbuf.frameLength())
            if not frames:
                return
            resampled = resampler.process(_read_channel0(mbuf, frames))
            if resampled.size:
                buffer.append(resampled)

        self._tap_block = tap
        self._input.installTapOnBus_bufferSize_format_block_(
            0, _TAP_BUFFER_FRAMES, native_fmt, tap
        )
        self._tapped = True
        ok, err = self._engine.startAndReturnError_(None)
        if not ok:
            # Leave a clean state so the next start() can retry, then surface the
            # same error class the sounddevice backend does — the daemon shows the
            # mic-permission guidance and recovers to idle. On macOS a denied
            # Microphone (TCC) grant lands here.
            self._teardown_tap()
            self._engine.stop()
            raise AudioCaptureError(
                f"AVAudioEngine failed to start: {err!r} "
                "(grant Microphone access if this is a permission denial)"
            )

    def stop(self) -> np.ndarray:
        """End one dictation: release the mic and return the 16 kHz audio.

        Called on the Qt main thread. Unlike PortAudio's ``Pa_StopStream``,
        AVAudioEngine ``stop()`` is deadlock-free and bounded (≤ ~1.5 s under
        concurrent model load, usually ~10–40 ms — #161 §4e), so the brief block
        is at worst a UI hitch, never the old freeze.
        """
        self._teardown_tap()
        try:
            self._engine.stop()
        except Exception:
            logger.exception("Error stopping AVAudioEngine")
        return self._buffer.flush()

    def close(self) -> None:
        """Idempotent teardown for daemon shutdown — safe to call any number of
        times, and safe here because AVAudioEngine ``stop()`` cannot deadlock
        (the reason ``close()`` was deferred from the sounddevice de-leak, #161).
        """
        self._teardown_tap()
        try:
            self._engine.stop()
        except Exception:
            logger.exception("Error stopping AVAudioEngine on close")

    def _teardown_tap(self) -> None:
        if self._tapped:
            try:
                self._input.removeTapOnBus_(0)
            except Exception:
                logger.exception("Error removing AVAudioEngine tap")
            finally:
                self._tapped = False
                self._tap_block = None
