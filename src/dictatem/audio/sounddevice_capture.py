"""SoundDeviceCapture — Windows adapter that opens a sounddevice InputStream.

This module imports sounddevice at runtime and is intended for Windows manual QA
only. It must NOT be imported at module level by any pure-core code.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dictatem.audio.input_devices import choose_input_device, input_device_names
from dictatem.exceptions import AudioCaptureError

if TYPE_CHECKING:
    import numpy as np

    from dictatem.audio.buffer import AudioBuffer
    from dictatem.config import Config

logger = logging.getLogger(__name__)


def _device_list(sd: Any) -> list[Any]:
    devices = sd.query_devices()
    return [devices] if isinstance(devices, dict) else list(devices)


def _default_hostapi(sd: Any) -> int:
    try:
        return int(sd.default.hostapi)
    except Exception:
        return 0


class SoundDeviceCapture:
    """PortAudio (sounddevice) microphone capture.

    PortAudio snapshots the device list when it initialises. So that a
    microphone plugged in mid-session is picked up by the *next* dictation, and
    so the first hotkey press doesn't pay for initialisation:

    - :meth:`initialize` runs shortly after launch (GUI thread);
    - :meth:`stop` marks a re-scan as due, and :meth:`refresh_if_due` (called
      from the daemon's idle tick) re-initialises PortAudio while no stream is
      open;
    - :meth:`refresh_devices` runs when the tray's Microphone menu opens.

    All PortAudio calls run on the GUI thread, so a re-scan can never race a
    stream opening. Re-initialising never opens the microphone.
    """

    def __init__(self, config: Config, buffer: AudioBuffer) -> None:
        self._sample_rate = config.audio.sample_rate
        self._device_spec = config.audio.device
        # The buffer is the shared seam between capture and the daemon: the
        # callback appends to it, the daemon reads level/idle off it. Injected
        # (required, not defaulted) so both sides provably share ONE buffer — a
        # backend that quietly made its own would leave the daemon's level pill,
        # silence-timeout and max-duration reads dead against an empty buffer.
        self._buffer = buffer
        self._stream: object | None = None
        self._refresh_due = False
        self._warned_fallback_for: str | None = None

    # -- device management -------------------------------------------------

    def set_device(self, spec: str | None) -> None:
        """Use *spec* (name substring, index, or None for default) from the next start."""
        self._device_spec = spec
        self._warned_fallback_for = None

    @property
    def device_spec(self) -> str | None:
        return self._device_spec

    def initialize(self) -> None:
        """Import sounddevice (which initialises PortAudio) ahead of first use."""
        try:
            import sounddevice  # noqa: F401
        except Exception:
            logger.warning("Audio backend could not initialise", exc_info=True)

    def refresh_devices(self) -> bool:
        """Re-scan audio devices now. No-op (False) while a stream is open."""
        if self._stream is not None:
            return False
        try:
            import sounddevice as sd

            sd._terminate()  # type: ignore[attr-defined]
            sd._initialize()  # type: ignore[attr-defined]
        except Exception:
            logger.warning("Audio device re-scan failed", exc_info=True)
            return False
        self._refresh_due = False
        return True

    def refresh_if_due(self) -> None:
        """Re-scan once after a dictation, when idle (called from the daemon tick)."""
        if self._refresh_due and self._stream is None:
            self.refresh_devices()

    def input_device_names(self) -> list[str]:
        """Names for the tray's Microphone menu (default host API inputs)."""
        import sounddevice as sd

        return input_device_names(_device_list(sd), _default_hostapi(sd))

    # -- capture -------------------------------------------------------------

    def start(self) -> None:
        import sounddevice as sd

        choice = choose_input_device(_device_list(sd), self._device_spec, _default_hostapi(sd))
        if choice.fell_back and self._warned_fallback_for != self._device_spec:
            self._warned_fallback_for = self._device_spec
            logger.warning(
                "Microphone %r is not connected; using the system default",
                self._device_spec,
            )
        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                device=choice.index,
                callback=self._audio_callback,
            )
            self._stream.start()  # type: ignore[union-attr]
        except sd.PortAudioError as exc:
            self._stream = None
            raise AudioCaptureError(str(exc)) from exc

    def stop(self) -> np.ndarray:
        self._close_stream()
        # Re-scan devices once we're idle again, so a mic plugged in now is
        # used by the next dictation (see refresh_if_due).
        self._refresh_due = True
        return self._buffer.flush()

    def close(self) -> None:
        """Final teardown at daemon shutdown (idempotent).

        Re-added with the macOS AVAudioEngine backend (#161): on Windows MME
        the stream stop never deadlocked, so closing it on shutdown is safe.
        A no-op if the stream is already closed (the common case, since ``stop``
        closes it after every dictation).
        """
        self._close_stream()

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()  # type: ignore[union-attr]
                self._stream.close()  # type: ignore[union-attr]
            except Exception:
                logger.exception("Error stopping audio stream")
            finally:
                self._stream = None

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,  # noqa: ARG002
        time_info: object,  # noqa: ARG002
        status: object,
    ) -> None:
        if status:
            logger.warning("Audio callback status: %s", status)
        self._buffer.append(indata[:, 0].copy())
