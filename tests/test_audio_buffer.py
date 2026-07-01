"""Tests for AudioBuffer — pure-core audio accumulation and level logic."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from dictatem.audio.buffer import AudioBuffer
from dictatem.types import SAMPLE_RATE


class TestAudioBufferAppendFlush:
    def test_append_single_chunk_flush_returns_same(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        chunk = np.ones(1600, dtype=np.float32)
        buf.append(chunk)
        result = buf.flush()
        assert result.dtype == np.float32
        assert result.shape == (1600,)
        np.testing.assert_array_equal(result, chunk)

    def test_multiple_appends_concatenate_in_order(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        c1 = np.full(800, 0.1, dtype=np.float32)
        c2 = np.full(800, 0.9, dtype=np.float32)
        buf.append(c1)
        buf.append(c2)
        result = buf.flush()
        assert result.shape == (1600,)
        np.testing.assert_array_almost_equal(result[:800], 0.1)
        np.testing.assert_array_almost_equal(result[800:], 0.9)

    def test_flush_clears_buffer(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        buf.append(np.ones(100, dtype=np.float32))
        buf.flush()
        result = buf.flush()
        assert result.shape == (0,)
        assert result.dtype == np.float32

    def test_flush_empty_buffer_returns_empty_array(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        result = buf.flush()
        assert result.shape == (0,)
        assert result.dtype == np.float32


class TestCurrentLevel:
    def test_zero_samples_give_zero_level(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        buf.append(np.zeros(1600, dtype=np.float32))
        assert buf.current_level() == 0.0

    def test_full_scale_samples_give_near_one(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        buf.append(np.ones(1600, dtype=np.float32))
        level = buf.current_level()
        assert 0.9 <= level <= 1.0

    def test_level_in_range_zero_one(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        buf.append(np.full(1600, 0.5, dtype=np.float32))
        level = buf.current_level()
        assert 0.0 <= level <= 1.0

    def test_level_empty_buffer_returns_zero(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        assert buf.current_level() == 0.0

    def test_zero_width_window_is_zero_not_whole_buffer(self) -> None:
        # A 0-sample level window must give 0.0, not RMS over the ENTIRE buffer:
        # _tail guards n_samples<=0 so it never does combined[-0:] (== [0:]).
        buf = AudioBuffer(sample_rate=SAMPLE_RATE, level_window_ms=0)
        buf.append(np.ones(1600, dtype=np.float32))
        assert buf.current_level() == 0.0

    def test_level_uses_recent_window(self) -> None:
        """Level should reflect recent audio, not the entire history."""
        buf = AudioBuffer(sample_rate=SAMPLE_RATE, level_window_ms=100)
        # Append 1 second of loud audio then 100ms of silence
        buf.append(np.ones(SAMPLE_RATE, dtype=np.float32))
        buf.append(np.zeros(SAMPLE_RATE // 10, dtype=np.float32))
        level = buf.current_level()
        assert level < 0.1


class TestDurationSeconds:
    def test_empty_buffer_is_zero(self) -> None:
        buf = AudioBuffer(sample_rate=16_000)
        assert buf.duration_seconds == 0.0

    def test_one_second_of_audio(self) -> None:
        buf = AudioBuffer(sample_rate=16_000)
        buf.append(np.zeros(16_000, dtype=np.float32))
        assert buf.duration_seconds == pytest.approx(1.0)

    def test_duration_after_flush_resets(self) -> None:
        buf = AudioBuffer(sample_rate=16_000)
        buf.append(np.zeros(16_000 * 5, dtype=np.float32))
        buf.flush()
        assert buf.duration_seconds == 0.0


class TestIsIdleForSeconds:
    def test_idle_when_silence(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        # 2 seconds of silence
        buf.append(np.zeros(SAMPLE_RATE * 2, dtype=np.float32))
        assert buf.is_idle_for_seconds(1.0) is True

    def test_not_idle_when_loud(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        # 2 seconds of full-scale audio
        buf.append(np.ones(SAMPLE_RATE * 2, dtype=np.float32))
        assert buf.is_idle_for_seconds(1.0) is False

    def test_not_idle_when_recent_audio_loud(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        # 2 seconds of silence then 0.5 seconds of loud
        buf.append(np.zeros(SAMPLE_RATE * 2, dtype=np.float32))
        buf.append(np.ones(SAMPLE_RATE // 2, dtype=np.float32))
        assert buf.is_idle_for_seconds(1.0) is False

    def test_idle_not_enough_data(self) -> None:
        """If buffer has less data than the threshold, cannot confirm idle."""
        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        buf.append(np.zeros(SAMPLE_RATE // 2, dtype=np.float32))
        assert buf.is_idle_for_seconds(1.0) is False

    def test_idle_empty_buffer(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        assert buf.is_idle_for_seconds(1.0) is False


class TestThreadSafety:
    """The capture callback appends on one thread while the Qt tick reads
    level/duration/idle on another. The lock must keep a read from ever
    concatenating the chunk list mid-append (RESOLUTION.md §3 residual):
    without it, ``np.concatenate(self._chunks)`` can race a concurrent
    ``list.append`` and raise or read torn data.
    """

    def test_concurrent_appends_and_reads_stay_consistent(self) -> None:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        chunk = np.ones(160, dtype=np.float32)
        writers = 4
        appends_per_writer = 250
        errors: list[BaseException] = []
        stop = threading.Event()

        def write() -> None:
            try:
                for _ in range(appends_per_writer):
                    buf.append(chunk)
            except BaseException as exc:  # noqa: BLE001 — surfaced via assert below
                errors.append(exc)

        def read() -> None:
            # Hammer the concat-based read paths while writers mutate the chunk
            # list; unserialised, this is where the race would surface.
            try:
                while not stop.is_set():
                    buf.current_level()
                    _ = buf.duration_seconds
                    buf.is_idle_for_seconds(0.5)
            except BaseException as exc:  # noqa: BLE001 — surfaced via assert below
                errors.append(exc)

        reader = threading.Thread(target=read)
        reader.start()
        write_threads = [threading.Thread(target=write) for _ in range(writers)]
        for t in write_threads:
            t.start()
        for t in write_threads:
            t.join()
        stop.set()
        reader.join()

        assert errors == []
        # Every appended sample survived exactly once — no loss, no double-count.
        result = buf.flush()
        assert result.shape == (writers * appends_per_writer * len(chunk),)
