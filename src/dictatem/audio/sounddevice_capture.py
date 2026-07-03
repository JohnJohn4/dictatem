"""SoundDeviceCapture — Windows adapter that opens a sounddevice InputStream.

This module imports sounddevice at runtime and is intended for Windows manual QA
only. It must NOT be imported at module level by any pure-core code.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dictatem.exceptions import AudioCaptureError

if TYPE_CHECKING:
    import numpy as np

    from dictatem.audio.buffer import AudioBuffer
    from dictatem.config import Config

logger = logging.getLogger(__name__)


def _resolve_device(device_spec: str | None) -> int | None:
    import sounddevice as sd

    if device_spec is None or device_spec == "default":
        return None
    try:
        return int(device_spec)
    except ValueError:
        pass
    devices = sd.query_devices()
    if isinstance(devices, dict):
        devices = [devices]
    for i, dev in enumerate(devices):
        if device_spec.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
            return i
    raise AudioCaptureError(
        f"No input device matching {device_spec!r}. "
        f"Available: {[d['name'] for d in devices if d['max_input_channels'] > 0]}"
    )


class SoundDeviceCapture:
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

    def start(self) -> None:
        import sounddevice as sd

        device = _resolve_device(self._device_spec)
        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                device=device,
                callback=self._audio_callback,
            )
            self._stream.start()  # type: ignore[union-attr]
        except sd.PortAudioError as exc:
            raise AudioCaptureError(str(exc)) from exc

    def stop(self) -> np.ndarray:
        self._close_stream()
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
