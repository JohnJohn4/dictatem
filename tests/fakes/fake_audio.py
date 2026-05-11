"""Fake audio capture for testing audio buffer logic."""

from __future__ import annotations

import numpy as np

from dictatem.types import SAMPLE_RATE, AudioChunk


class FakeAudioCapture:
    def __init__(self, duration_s: float = 1.0) -> None:
        self._duration_s = duration_s
        self.started: bool = False
        self.stopped: bool = False
        self.start_count: int = 0
        self._start_errors: list[Exception] = []

    def start(self) -> None:
        self.start_count += 1
        if self._start_errors:
            raise self._start_errors.pop(0)
        self.started = True
        self.stopped = False

    def stop(self) -> AudioChunk:
        self.stopped = True
        num_samples = int(SAMPLE_RATE * self._duration_s)
        return np.zeros(num_samples, dtype=np.float32)

    def queue_start_error(self, error: Exception) -> None:
        self._start_errors.append(error)
