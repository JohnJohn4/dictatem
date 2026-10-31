"""Tests for AudioBuffer — pure-core audio accumulation and level logic."""

from __future__ import annotations

import threading
import time

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


def _reference_tail_rms(audio: np.ndarray, n_samples: int) -> float:
    """The pre-F-9 behaviour, spelled out over the whole flat recording:
    RMS of the last ``n_samples`` (clamped to the recording), capped at 1.0;
    zero or negative requests (and an empty recording) give 0.0."""
    if len(audio) == 0 or n_samples <= 0:
        return 0.0
    tail = audio[-min(n_samples, len(audio)):]
    return min(float(np.sqrt(np.mean(tail ** 2))), 1.0)


class TestTailReadEquivalence:
    """Level/silence read only the recent tail (F-9, #237) — results must be
    identical to RMS over the tail of the whole flat recording, whatever the
    chunk sizes and wherever the window boundary falls relative to them."""

    @pytest.mark.parametrize("seed", range(12))
    def test_level_and_idle_match_whole_recording_reference(self, seed: int) -> None:
        rng = np.random.default_rng(seed)
        sample_rate = 1_000  # small rate keeps windows near chunk sizes
        window_ms = int(rng.integers(0, 400))
        floor = float(rng.uniform(0.05, 0.5))
        buf = AudioBuffer(
            sample_rate=sample_rate, level_window_ms=window_ms, silence_floor=floor
        )
        window = int(sample_rate * window_ms / 1000)
        parts: list[np.ndarray] = []
        for _ in range(int(rng.integers(1, 40))):
            size = int(rng.integers(0, 120))  # includes empty chunks
            amp = float(rng.choice([0.0, 0.02, 0.3, 1.5]))
            chunk = (rng.uniform(-1, 1, size) * amp).astype(np.float32)
            buf.append(chunk)
            parts.append(chunk)
            audio = np.concatenate(parts)
            assert buf.current_level() == _reference_tail_rms(audio, window)
            for threshold in (0.0, 0.05, 0.1, 0.25, 1.0):
                required = int(sample_rate * threshold)
                expected = len(audio) >= required and (
                    _reference_tail_rms(audio, required) < floor
                )
                assert buf.is_idle_for_seconds(threshold) is expected

    def test_window_ending_exactly_on_chunk_boundary(self) -> None:
        buf = AudioBuffer(sample_rate=1_000, level_window_ms=100)
        buf.append(np.ones(500, dtype=np.float32))
        buf.append(np.full(100, 0.5, dtype=np.float32))  # exactly the window
        assert buf.current_level() == pytest.approx(0.5)

    def test_window_straddling_chunks(self) -> None:
        buf = AudioBuffer(sample_rate=1_000, level_window_ms=100)
        buf.append(np.zeros(500, dtype=np.float32))
        buf.append(np.ones(50, dtype=np.float32))
        buf.append(np.zeros(50, dtype=np.float32))
        # 50 ones + 50 zeros in the 100-sample window -> sqrt(0.5)
        assert buf.current_level() == pytest.approx(np.sqrt(0.5))

    def test_negative_threshold_is_empty_tail_not_whole_buffer(self) -> None:
        buf = AudioBuffer(sample_rate=1_000, silence_floor=0.01)
        buf.append(np.ones(500, dtype=np.float32))
        # required <= 0 -> empty tail -> RMS 0.0 < floor (unchanged rule)
        assert buf.is_idle_for_seconds(-1.0) is True

    def test_flush_after_tail_reads_returns_full_recording(self) -> None:
        buf = AudioBuffer(sample_rate=1_000, level_window_ms=100)
        parts = [np.full(37, i / 10, dtype=np.float32) for i in range(10)]
        for p in parts:
            buf.append(p)
            buf.current_level()
            buf.is_idle_for_seconds(0.2)
        np.testing.assert_array_equal(buf.flush(), np.concatenate(parts))


class TestTailReadCostDoesNotScale:
    """Regression guard for F-9: a tick on a max-length (300 s) recording must
    cost about the same as on a 5 s one. The bound is deliberately generous —
    the old whole-recording concatenate is tens of times slower at 300 s."""

    @staticmethod
    def _filled(seconds: int) -> AudioBuffer:
        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        chunk = np.full(512, 0.1, dtype=np.float32)  # typical capture block
        for _ in range(seconds * SAMPLE_RATE // 512):
            buf.append(chunk)
        return buf

    @staticmethod
    def _time_ticks(buf: AudioBuffer, ticks: int = 50) -> float:
        start = time.perf_counter()
        for _ in range(ticks):
            buf.current_level()
            buf.is_idle_for_seconds(2.0)
        return time.perf_counter() - start

    def test_max_length_tick_is_not_much_slower_than_short(self) -> None:
        short = self._filled(5)
        long = self._filled(300)
        self._time_ticks(short, 5)  # warm up
        self._time_ticks(long, 5)
        short_t = min(self._time_ticks(short) for _ in range(3))
        long_t = min(self._time_ticks(long) for _ in range(3))
        assert long_t < 10 * short_t + 0.05, (short_t, long_t)
