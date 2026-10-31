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
        # readers snapshot just the tail chunks they need under it (cheap —
        # O(tail chunks)) then run the numpy work lock-FREE, so the realtime
        # append() never blocks on a copy. Flush still concatenates it all.
        # Safe because a chunk is never mutated once appended, so a snapshot's
        # arrays stay valid after the lock is dropped.
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
        chunks, _total = self._snapshot_tail(self._level_window_samples)
        return self._rms_normalized(self._tail(chunks, self._level_window_samples))

    def is_idle_for_seconds(self, threshold: float) -> bool:
        required_samples = int(self._sample_rate * threshold)
        chunks, total = self._snapshot_tail(required_samples)
        if total < required_samples:
            return False
        tail = self._tail(chunks, required_samples)
        return self._rms_normalized(tail) < self._silence_floor

    def _snapshot_tail(self, n_samples: int) -> tuple[list[AudioChunk], int]:
        # Copy, under the lock, only the refs of the newest chunks that cover
        # the last n_samples (plus the total count) — O(tail chunks), not
        # O(recording), so a 50 ms tick costs the same at 5 s or 5 min (F-9).
        # The concatenate in _tail then runs lock-free (see __init__).
        with self._lock:
            total = self._total_samples
            if n_samples <= 0:
                return [], total
            picked: list[AudioChunk] = []
            covered = 0
            for chunk in reversed(self._chunks):
                if covered >= n_samples:
                    break
                picked.append(chunk)
                covered += len(chunk)
        picked.reverse()
        return picked, total

    @staticmethod
    def _tail(chunks: list[AudioChunk], n_samples: int) -> AudioChunk:
        # n_samples <= 0 must return empty — combined[-0:] is combined[0:], i.e.
        # the WHOLE buffer, which would compute RMS over the entire recording.
        if not chunks or n_samples <= 0:
            return np.array([], dtype=np.float32)
        combined = np.concatenate(chunks)
        return combined[-min(n_samples, len(combined)):]

    @staticmethod
    def _rms_normalized(samples: AudioChunk) -> float:
        if len(samples) == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(samples ** 2)))
        return min(rms, 1.0)
