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


def bundled_portaudio_dll_name(*, platform_tag: str, arch_bits: str, asio: bool) -> str:
    """The bundled PortAudio DLL ``sounddevice`` loads on Windows.

    Mirrors sounddevice's own choice (``libportaudio<64bit|32bit|arm64>[-asio].dll``
    under ``_sounddevice_data/portaudio-binaries``). If this ever drifts from
    sounddevice, the preload just loads the wrong file and saves nothing.
    """
    suffix = "arm64" if ("arm64" in platform_tag or "aarch64" in platform_tag) else arch_bits
    return f"libportaudio{suffix}{'-asio' if asio else ''}.dll"


def preload_portaudio_library() -> None:
    """Load the PortAudio DLL (and sounddevice's cffi module) ahead of first use.

    Pill-delay QA (work laptop, 2026-11-03): the first hotkey press of a session
    blocked the GUI thread ~0.3 s+ importing sounddevice before the mic opened
    and the pill could show (more when cold). This loads the library file only.
    It does **not** import ``sounddevice``, whose import runs ``Pa_Initialize``
    and freezes PortAudio's device list. Initialising at launch would hide a
    headset or dock plugged in between launch and the first dictation, so that
    stays at the first press, exactly as before. Never opens the microphone.
    Best-effort: any failure only forfeits the speed-up.
    """
    import os
    import platform
    import sysconfig

    try:
        import ctypes

        import _sounddevice  # type: ignore[import-not-found]  # noqa: F401  (cffi module)
        import _sounddevice_data  # type: ignore[import-not-found]

        name = bundled_portaudio_dll_name(
            platform_tag=sysconfig.get_platform(),
            arch_bits=platform.architecture()[0],
            asio="SD_ENABLE_ASIO" in os.environ,
        )
        path = os.path.join(
            next(iter(_sounddevice_data.__path__)), "portaudio-binaries", name
        )
        ctypes.WinDLL(path)  # type: ignore[attr-defined]
        logger.debug("Preloaded %s", name)
    except Exception as exc:
        logger.debug("PortAudio preload skipped: %s", exc)


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
