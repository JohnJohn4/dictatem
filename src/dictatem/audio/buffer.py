"""Pure-core audio buffer — accumulates chunks, computes levels, detects idle.

No sounddevice import; depends only on numpy + stdlib.
"""

from __future__ import annotations

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

    def append(self, chunk: AudioChunk) -> None:
        self._chunks.append(chunk)
        self._total_samples += len(chunk)

    def flush(self) -> AudioChunk:
        if not self._chunks:
            return np.array([], dtype=np.float32)
        result = np.concatenate(self._chunks)
        self._chunks.clear()
        self._total_samples = 0
        return result

    def current_level(self) -> float:
        if self._total_samples == 0:
            return 0.0
        tail = self._get_tail(self._level_window_samples)
        return self._rms_normalized(tail)

    def is_idle_for_seconds(self, threshold: float) -> bool:
        required_samples = int(self._sample_rate * threshold)
        if self._total_samples < required_samples:
            return False
        tail = self._get_tail(required_samples)
        rms = float(np.sqrt(np.mean(tail ** 2)))
        return rms < self._silence_floor

    def _get_tail(self, n_samples: int) -> AudioChunk:
        if self._total_samples == 0:
            return np.array([], dtype=np.float32)
        n_samples = min(n_samples, self._total_samples)
        combined = np.concatenate(self._chunks)
        return combined[-n_samples:]

    @staticmethod
    def _rms_normalized(samples: AudioChunk) -> float:
        if len(samples) == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(samples ** 2)))
        return min(rms, 1.0)
