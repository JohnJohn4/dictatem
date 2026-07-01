"""Pure-core audio buffer — accumulates chunks, computes levels, detects idle.

No sounddevice import; depends only on numpy + stdlib.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from dictatem.types import AudioChunk


class AudioBuffer:
    def __init__(
        self,
        sample_rate: int = 16_000,
        level_window_ms: int = 100,
        silence_floor: float = 0.01,
    ) -> None:
        self._sample_rate = sample_rate
        self._level_window_samples = int(sample_rate * level_window_ms / 1000)
        self._silence_floor = silence_floor
        self._chunks: list[AudioChunk] = []
        self._total_samples: int = 0
        # The capture backend's callback thread appends while the Qt tick thread
        # reads level/idle. The lock guards only the list + counter mutations;
        # readers snapshot under it (cheap — O(#chunks)) then run the O(total)
        # numpy work lock-FREE, so the realtime append() never blocks on a copy
        # of the whole recording. Safe because a chunk is never mutated once
        # appended, so a snapshot's arrays stay valid after the lock is dropped.
        self._lock = threading.Lock()

    def append(self, chunk: AudioChunk) -> None:
        with self._lock:
            self._chunks.append(chunk)
            self._total_samples += len(chunk)

    def flush(self) -> AudioChunk:
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            result = np.concatenate(self._chunks)
            self._chunks.clear()
            self._total_samples = 0
            return result

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return self._total_samples / self._sample_rate

    def current_level(self) -> float:
        chunks, total = self._snapshot()
        if total == 0:
            return 0.0
        tail = self._tail(chunks, total, self._level_window_samples)
        return self._rms_normalized(tail)

    def is_idle_for_seconds(self, threshold: float) -> bool:
        chunks, total = self._snapshot()
        required_samples = int(self._sample_rate * threshold)
        if total < required_samples:
            return False
        tail = self._tail(chunks, total, required_samples)
        return self._rms_normalized(tail) < self._silence_floor

    def _snapshot(self) -> tuple[list[AudioChunk], int]:
        # Copy the chunk refs + sample count under the lock so the O(total)
        # concatenate in _tail can run lock-free (see __init__).
        with self._lock:
            return list(self._chunks), self._total_samples

    @staticmethod
    def _tail(chunks: list[AudioChunk], total: int, n_samples: int) -> AudioChunk:
        # n_samples <= 0 must return empty — combined[-0:] is combined[0:], i.e.
        # the WHOLE buffer, which would compute RMS over the entire recording.
        if total == 0 or n_samples <= 0:
            return np.array([], dtype=np.float32)
        n_samples = min(n_samples, total)
        combined = np.concatenate(chunks)
        return combined[-n_samples:]

    @staticmethod
    def _rms_normalized(samples: AudioChunk) -> float:
        if len(samples) == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(samples ** 2)))
        return min(rms, 1.0)
