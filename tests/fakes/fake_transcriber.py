"""Fake transcriber backend for testing lifecycle and transcription logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dictatem.types import AudioChunk, EmptyResult, TranscriptionResult

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeTranscriberBackend:
    def __init__(self, result: TranscriptionResult = "fake transcription") -> None:
        self._result = result
        self._loaded: bool = False
        self.load_count: int = 0
        self.unload_count: int = 0
        self.empty_cache_count: int = 0
        self.transcribe_calls: list[AudioChunk] = []
        self._errors_to_raise: list[Exception] = []
        self._load_errors: list[Exception] = []
        self._progress_callback: Callable[[int, int], None] | None = None

    def load_model(self) -> None:
        self.load_count += 1
        if self._load_errors:
            raise self._load_errors.pop(0)
        self._loaded = True

    def unload_model(self) -> None:
        self._loaded = False
        self.unload_count += 1

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        self.transcribe_calls.append(audio)
        if self._errors_to_raise:
            raise self._errors_to_raise.pop(0)
        if not self._loaded:
            return EmptyResult()
        return self._result

    def empty_cache(self) -> None:
        self.empty_cache_count += 1

    def set_progress_callback(
        self, callback: Callable[[int, int], None] | None
    ) -> None:
        self._progress_callback = callback

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # --- Test helpers ---

    def queue_error(self, error: Exception) -> None:
        """Queue an exception to be raised on the next transcribe() call."""
        self._errors_to_raise.append(error)

    def queue_load_error(self, error: Exception) -> None:
        """Queue an exception to be raised on the next load_model() call."""
        self._load_errors.append(error)

    def simulate_progress(self, downloaded: int, total: int) -> None:
        """Invoke the registered progress callback."""
        if self._progress_callback is not None:
            self._progress_callback(downloaded, total)
