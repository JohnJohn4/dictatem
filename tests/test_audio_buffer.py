"""Tests for AudioBuffer — pure-core audio accumulation and level logic."""

from __future__ import annotations

import sys

import numpy as np

from dictatem.types import SAMPLE_RATE


class TestAudioBufferAppendFlush:
    def test_append_single_chunk_flush_returns_same(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        chunk = np.ones(1600, dtype=np.float32)
        buf.append(chunk)
        result = buf.flush()
        assert result.dtype == np.float32
        assert result.shape == (1600,)
        np.testing.assert_array_equal(result, chunk)

    def test_multiple_appends_concatenate_in_order(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

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
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        buf.append(np.ones(100, dtype=np.float32))
        buf.flush()
        result = buf.flush()
        assert result.shape == (0,)
        assert result.dtype == np.float32

    def test_flush_empty_buffer_returns_empty_array(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        result = buf.flush()
        assert result.shape == (0,)
        assert result.dtype == np.float32


class TestCurrentLevel:
    def test_zero_samples_give_zero_level(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        buf.append(np.zeros(1600, dtype=np.float32))
        assert buf.current_level() == 0.0

    def test_full_scale_samples_give_near_one(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        buf.append(np.ones(1600, dtype=np.float32))
        level = buf.current_level()
        assert 0.9 <= level <= 1.0

    def test_level_in_range_zero_one(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        buf.append(np.full(1600, 0.5, dtype=np.float32))
        level = buf.current_level()
        assert 0.0 <= level <= 1.0

    def test_level_empty_buffer_returns_zero(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE)
        assert buf.current_level() == 0.0

    def test_level_uses_recent_window(self) -> None:
        """Level should reflect recent audio, not the entire history."""
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE, level_window_ms=100)
        # Append 1 second of loud audio then 100ms of silence
        buf.append(np.ones(SAMPLE_RATE, dtype=np.float32))
        buf.append(np.zeros(SAMPLE_RATE // 10, dtype=np.float32))
        level = buf.current_level()
        assert level < 0.1


class TestIsIdleForSeconds:
    def test_idle_when_silence(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        # 2 seconds of silence
        buf.append(np.zeros(SAMPLE_RATE * 2, dtype=np.float32))
        assert buf.is_idle_for_seconds(1.0) is True

    def test_not_idle_when_loud(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        # 2 seconds of full-scale audio
        buf.append(np.ones(SAMPLE_RATE * 2, dtype=np.float32))
        assert buf.is_idle_for_seconds(1.0) is False

    def test_not_idle_when_recent_audio_loud(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        # 2 seconds of silence then 0.5 seconds of loud
        buf.append(np.zeros(SAMPLE_RATE * 2, dtype=np.float32))
        buf.append(np.ones(SAMPLE_RATE // 2, dtype=np.float32))
        assert buf.is_idle_for_seconds(1.0) is False

    def test_idle_not_enough_data(self) -> None:
        """If buffer has less data than the threshold, cannot confirm idle."""
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        buf.append(np.zeros(SAMPLE_RATE // 2, dtype=np.float32))
        assert buf.is_idle_for_seconds(1.0) is False

    def test_idle_empty_buffer(self) -> None:
        from dictatem.audio.buffer import AudioBuffer

        buf = AudioBuffer(sample_rate=SAMPLE_RATE, silence_floor=0.01)
        assert buf.is_idle_for_seconds(1.0) is False


class TestImportSafety:
    def test_no_sounddevice_import(self) -> None:
        """audio.buffer import graph must not contain sounddevice."""
        mods_before = set(sys.modules.keys())
        import dictatem.audio.buffer  # noqa: F401

        new_mods = set(sys.modules.keys()) - mods_before
        sd_imports = [m for m in new_mods if m == "sounddevice" or m.startswith("sounddevice.")]
        assert sd_imports == [], f"sounddevice imported transitively: {sd_imports}"
