"""FallbackTranscriber — the runtime session fallback for the MLX engine (#232).

A pure, protocol-level composite (spec #224, "Fallback-composing transcriber").
It wraps a *primary* backend (the Apple-GPU MLX backend in production) and a
*fallback factory* (the ``Apple-Silicon``-row faster-whisper backend), and is
itself a :class:`~dictatem.interfaces.TranscriberBackend`.

If the primary fails to load (a Metal or import error, corrupt weights, missing
weights while offline, an unknown model name), or fails while transcribing, the
composite:

- logs one warning naming the cause,
- latches "fell back" for the rest of the session, so the primary is never
  retried (the next launch tries it again, because the latch lives in memory
  and the config is never rewritten),
- builds the fallback lazily, the first time it is needed,
- re-runs the same audio on the fallback, so the dictation is never lost
  (ADR-0023), and
- fires ``on_fallback`` once (the daemon turns it into one tray notification).

A fallback that fails too raises as any backend does, so the daemon shows
today's transcription-failure notification. There is deliberately no OOM retry
here (#208 removed it).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.interfaces import TranscriberBackend
    from dictatem.types import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)


class FallbackTranscriber:
    """Use *primary* until it fails, then *fallback_factory()* for the session."""

    def __init__(
        self,
        *,
        primary: TranscriberBackend,
        fallback_factory: Callable[[], TranscriberBackend],
        on_fallback: Callable[[], None] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback_factory = fallback_factory
        self._on_fallback = on_fallback
        self._fallback: TranscriberBackend | None = None
        self._progress_callback: Callable[[int, int], None] | None = None
        self._switch_lock = threading.Lock()

    @property
    def fell_back(self) -> bool:
        """Whether this session has switched to the fallback backend."""
        return self._fallback is not None

    @property
    def _active(self) -> TranscriberBackend:
        return self._fallback if self._fallback is not None else self._primary

    def load_model(self) -> None:
        if self._fallback is None:
            try:
                self._primary.load_model()
                return
            except Exception as exc:
                self._switch_to_fallback(exc, during="load")
        self._active.load_model()

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        if self._fallback is None:
            try:
                return self._primary.transcribe(audio)
            except Exception as exc:
                self._switch_to_fallback(exc, during="transcription")
                # Re-run the same audio on the fallback: the dictation the user
                # just spoke is never lost to an engine failure.
                self._active.load_model()
        return self._active.transcribe(audio)

    def unload_model(self) -> None:
        self._active.unload_model()

    def download_to_disk(self) -> None:
        self._active.download_to_disk()

    def empty_cache(self) -> None:
        self._active.empty_cache()

    def set_progress_callback(self, callback: Callable[[int, int], None] | None) -> None:
        self._progress_callback = callback
        self._active.set_progress_callback(callback)

    @property
    def is_loaded(self) -> bool:
        return self._active.is_loaded

    def _switch_to_fallback(self, cause: Exception, *, during: str) -> None:
        with self._switch_lock:
            if self._fallback is not None:
                return  # another thread already switched
            logger.warning(
                "Transcription engine failed during %s (%s: %s); switching to "
                "the CPU fallback for the rest of this session. The config file "
                "is unchanged; the next launch tries the GPU again.",
                during,
                type(cause).__name__,
                cause,
            )
            if self._primary.is_loaded:
                try:
                    self._primary.unload_model()
                except Exception:
                    logger.debug("Unloading the failed primary failed", exc_info=True)
            fallback = self._fallback_factory()
            if self._progress_callback is not None:
                fallback.set_progress_callback(self._progress_callback)
            self._fallback = fallback
        if self._on_fallback is not None:
            try:
                self._on_fallback()
            except Exception:
                # A notification hiccup must never cost the user the dictation.
                logger.error("Error in the engine-fallback callback", exc_info=True)
