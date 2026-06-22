"""Fake transcriber backend for testing lifecycle and transcription logic."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from dictatem.types import AudioChunk, EmptyResult, TranscriptionResult

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeTranscriberBackend:
    def __init__(self, result: TranscriptionResult = "fake transcription") -> None:
        self._result = result
        self._loaded: bool = False
        # A gate so a test can hold load_model() open (load-on-arm, #161): it
        # lets the test assert the "still loading" pill at transcribe-time, then
        # release the load and watch the pill flip to transcribing. Pre-set, so
        # by default load_model() returns immediately and behaviour is unchanged.
        self._load_gate = threading.Event()
        self._load_gate.set()
        # A persistent (every-call) load failure, e.g. "CUDA missing" — unlike
        # the one-shot queue_load_error, so a test stays deterministic under
        # load-on-arm, where both the preload and the transcribe paths attempt
        # the load (#161).
        self._fail_load_always: Exception | None = None
        self.load_count: int = 0
        self.unload_count: int = 0
        self.empty_cache_count: int = 0
        self.transcribe_calls: list[AudioChunk] = []
        self._errors_to_raise: list[Exception] = []
        self._load_errors: list[Exception] = []
        self._progress_callback: Callable[[int, int], None] | None = None

    def load_model(self) -> None:
        self.load_count += 1
        # Park here while a test holds the gate (block_load), so the model stays
        # unloaded until release_load() — see __init__.
        self._load_gate.wait()
        # A persistent failure takes precedence over the one-shot queue; a test
        # uses one mechanism or the other, never both.
        if self._fail_load_always is not None:
            raise self._fail_load_always
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

    def block_load(self) -> None:
        """Make subsequent load_model() calls block until release_load() (#161).

        load_count is still incremented on entry, so a test can confirm the
        load was kicked while it is parked, then release it.
        """
        self._load_gate.clear()

    def release_load(self) -> None:
        """Release a load_model() call parked by block_load()."""
        self._load_gate.set()

    def fail_load_always(self, error: Exception) -> None:
        """Make every load_model() call raise *error* (a persistent failure)."""
        self._fail_load_always = error
