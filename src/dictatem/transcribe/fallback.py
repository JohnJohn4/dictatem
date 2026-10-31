"""FallbackTranscriber — the runtime session fallback for the MLX engine (#232).

A pure, protocol-level composite (spec #224, "Fallback-composing transcriber").
It wraps a *primary* backend (the Apple-GPU MLX backend in production) and a
*fallback factory* (the ``Apple-Silicon``-row faster-whisper backend), and is
itself a :class:`~dictatem.interfaces.TranscriberBackend`.

If the primary fails to load (a Metal or import error, corrupt weights, missing
weights while offline, an unknown model name), or fails while transcribing, the
composite:

- logs one warning naming the cause,
- latches "fell back" for the rest of the session, BEFORE building anything,
  so the primary is never retried, even if building the fallback raises (the
  next launch tries it again, because the latch lives in memory and the config
  is never rewritten),
- fires ``on_fallback`` once with the reason (``"mlx-load-failed"`` or
  ``"mlx-transcribe-failed"``; the daemon turns it into one tray notification),
- builds the fallback lazily, the first time it is needed, and
- re-runs the same audio on the fallback, so the dictation is never lost
  (ADR-0023).

A fallback (or fallback factory) that fails too raises as any backend does, so
the daemon shows today's transcription-failure notification. There is
deliberately no OOM retry
here (#208 removed it).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.hardware.resolver import RuntimeFallbackReason
    from dictatem.interfaces import TranscriberBackend
    from dictatem.types import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)


class FallbackTranscriber:
    """Use *primary* until it fails, then *fallback_factory()* for the session.

    *on_fallback* receives the :data:`RuntimeFallbackReason` naming which
    failure happened (``"mlx-load-failed"`` or ``"mlx-transcribe-failed"``).
    """

    def __init__(
        self,
        *,
        primary: TranscriberBackend,
        fallback_factory: Callable[[], TranscriberBackend],
        on_fallback: Callable[[RuntimeFallbackReason], None] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback_factory = fallback_factory
        self._on_fallback = on_fallback
        self._fell_back = False
        self._fallback: TranscriberBackend | None = None
        self._progress_callback: Callable[[int, int], None] | None = None
        self._switch_lock = threading.Lock()

    @property
    def fell_back(self) -> bool:
        """Whether this session has switched to the fallback backend."""
        return self._fell_back

    def load_model(self) -> None:
        if not self._fell_back:
            try:
                self._primary.load_model()
                return
            except Exception as exc:
                self._latch(exc, "mlx-load-failed")
        self._fallback_backend().load_model()

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        if not self._fell_back:
            try:
                return self._primary.transcribe(audio)
            except Exception as exc:
                self._latch(exc, "mlx-transcribe-failed")
                # Re-run the same audio on the fallback: the dictation the user
                # just spoke is never lost to an engine failure.
                self._fallback_backend().load_model()
        return self._fallback_backend().transcribe(audio)

    def unload_model(self) -> None:
        backend = self._built_backend()
        if backend is not None:
            backend.unload_model()

    def download_to_disk(self) -> None:
        if self._fell_back:
            self._fallback_backend().download_to_disk()
        else:
            self._primary.download_to_disk()

    def empty_cache(self) -> None:
        backend = self._built_backend()
        if backend is not None:
            backend.empty_cache()

    def set_progress_callback(self, callback: Callable[[int, int], None] | None) -> None:
        self._progress_callback = callback
        backend = self._built_backend()
        if backend is not None:
            backend.set_progress_callback(callback)

    @property
    def is_loaded(self) -> bool:
        backend = self._built_backend()
        return backend is not None and backend.is_loaded

    def _built_backend(self) -> TranscriberBackend | None:
        """The active backend, or ``None`` if fell back but none is built yet."""
        return self._fallback if self._fell_back else self._primary

    def _latch(self, cause: Exception, reason: RuntimeFallbackReason) -> None:
        """Latch "fell back" for the session, BEFORE any fallback is built.

        Latching first means a raising fallback factory never sends the next
        call back to the primary; it surfaces as an ordinary failure instead.
        """
        with self._switch_lock:
            if self._fell_back:
                return  # another thread already switched
            self._fell_back = True
            logger.warning(
                "Transcription engine failed (%s: %s: %s); switching to the CPU "
                "fallback for the rest of this session. The config file is "
                "unchanged; the next launch tries the GPU again.",
                reason,
                type(cause).__name__,
                cause,
            )
            if self._primary.is_loaded:
                try:
                    self._primary.unload_model()
                except Exception:
                    logger.debug("Unloading the failed primary failed", exc_info=True)
        if self._on_fallback is not None:
            try:
                self._on_fallback(reason)
            except Exception:
                # A notification hiccup must never cost the user the dictation.
                logger.error("Error in the engine-fallback callback", exc_info=True)

    def _fallback_backend(self) -> TranscriberBackend:
        """Build the fallback once (lazily); a raising factory is retried next call."""
        with self._switch_lock:
            if self._fallback is None:
                fallback = self._fallback_factory()
                if self._progress_callback is not None:
                    fallback.set_progress_callback(self._progress_callback)
                self._fallback = fallback
            return self._fallback
