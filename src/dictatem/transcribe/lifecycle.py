"""TranscribeLifecycle — pure-core lifecycle wrapper around a TranscriberBackend."""

from __future__ import annotations

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

    def preload(self) -> None:
        thread = threading.Thread(target=self._ensure_loaded, daemon=True)
        thread.start()

    def unload(self) -> None:
        self._last_activity = None
        if self._backend.is_loaded:
            self._backend.unload_model()

    def check_idle(self) -> None:
        if self._last_activity is None:
            return
        elapsed = self._clock() - self._last_activity
        if elapsed >= self._idle_timeout_s:
            self.unload()

    def on_download_progress(self, callback: Callable[[int, int], None]) -> None:
        self._backend.set_progress_callback(callback)

    def _ensure_loaded(self) -> None:
        if self._backend.is_loaded:
            return
        with self._load_lock:
            if not self._backend.is_loaded:
                self._backend.load_model()
