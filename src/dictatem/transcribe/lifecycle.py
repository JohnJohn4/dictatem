"""TranscribeLifecycle — pure-core lifecycle wrapper around a TranscriberBackend."""

from __future__ import annotations

import logging
import string
import threading
import time
from typing import TYPE_CHECKING

from dictatem.exceptions import GPUOutOfMemoryError, TranscriptionFailedError
from dictatem.types import EmptyResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.interfaces import TranscriberBackend
    from dictatem.types import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)


def _is_empty_text(text: str, min_chars: int) -> bool:
    stripped = text.strip().strip(string.punctuation)
    return len(stripped) < min_chars


class TranscribeLifecycle:
    def __init__(
        self,
        backend: TranscriberBackend,
        *,
        clock: Callable[[], float] = time.monotonic,
        idle_timeout_s: float = 1800.0,
        min_transcription_chars: int = 3,
    ) -> None:
        self._backend = backend
        self._clock = clock
        self._idle_timeout_s = idle_timeout_s
        self._min_chars = min_transcription_chars
        self._last_activity: float | None = None
        self._load_lock = threading.Lock()
        self._is_loading = False

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        self._ensure_loaded()

        try:
            raw = self._backend.transcribe(audio)
        except GPUOutOfMemoryError:
            self._backend.empty_cache()
            try:
                raw = self._backend.transcribe(audio)
            except GPUOutOfMemoryError as exc:
                raise TranscriptionFailedError(
                    "GPU out of memory after retry"
                ) from exc

        self._last_activity = self._clock()

        if isinstance(raw, EmptyResult):
            return raw
        if isinstance(raw, str) and _is_empty_text(raw, self._min_chars):
            return EmptyResult()

        return raw

    @property
    def is_loaded(self) -> bool:
        return self._backend.is_loaded

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    def preload(self) -> None:
        if self._is_loading or self._backend.is_loaded:
            return
        self._is_loading = True
        thread = threading.Thread(target=self._background_load, daemon=True)
        thread.start()

    def unload(self) -> None:
        if not self._backend.is_loaded:
            return
        logger.info("Unloading model")
        self._last_activity = None
        self._backend.unload_model()
        logger.info("Model unloaded")

    def check_idle(self) -> None:
        if self._last_activity is None:
            return
        elapsed = self._clock() - self._last_activity
        if elapsed >= self._idle_timeout_s:
            logger.info(
                "Idle timeout: model unused for %.0fs, unloading", elapsed
            )
            self.unload()

    def on_download_progress(self, callback: Callable[[int, int], None]) -> None:
        self._backend.set_progress_callback(callback)

    def _background_load(self) -> None:
        try:
            self._ensure_loaded()
            # Mark the freshly-loaded model as "active" so the idle-timer
            # eventually unloads it even if no transcription has run yet.
            if self._last_activity is None:
                self._last_activity = self._clock()
        finally:
            self._is_loading = False

    def _ensure_loaded(self) -> None:
        if self._backend.is_loaded:
            return
        with self._load_lock:
            if not self._backend.is_loaded:
                start = self._clock()
                logger.info("Loading model...")
                self._backend.load_model()
                elapsed = self._clock() - start
                logger.info("Model loaded in %.1fs", elapsed)
