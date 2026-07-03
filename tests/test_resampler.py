"""Unit tests for the pure polyphase resampler (native rate -> 16 kHz).

Runs on every CI platform — this is the point of keeping resampling pure numpy
rather than an on-device AVAudioConverter (#161 §4b). Covers the rate pairs the
macOS backend sees (44.1/48 kHz native), the ``streaming == batch`` invariant
the backend relies on, and the anti-aliasing that separates a real resampler
from the spike's linear interp.
"""

from __future__ import annotations

import numpy as np
import pytest

from dictatem.audio.resampler import (
    PolyphaseResampler,
    resample,
    resample_to_16k,
)
from dictatem.types import SAMPLE_RATE


def _tone(freq: float, rate: int, seconds: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(rate * seconds), dtype=np.float64) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2))) if x.size else 0.0


def _dominant_freq(x: np.ndarray, rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return float(np.fft.rfftfreq(len(x), 1 / rate)[np.argmax(spectrum)])


class TestOutputContract:
    def test_dtype_is_float32(self) -> None:
        out = resample_to_16k(_tone(1000, 48000, 0.1), 48000)
        assert out.dtype == np.float32

    def test_empty_in_empty_out(self) -> None:
        out = resample_to_16k(np.zeros(0, dtype=np.float32), 48000)
        assert out.dtype == np.float32
        assert out.size == 0

    def test_passthrough_is_unfiltered_copy(self) -> None:
        # 16 kHz in -> 16 kHz out must be a faithful copy, not run through the
        # FIR (no rate change, so no filtering to do).
        src = _tone(1000, SAMPLE_RATE, 0.25)
        out = resample_to_16k(src, SAMPLE_RATE)
        assert np.array_equal(out, src)
        # ...and a genuine copy, so a later mutation of the input can't alias it.
        assert out is not src


class TestLength:
    @pytest.mark.parametrize(
        ("src_rate", "seconds"),
        [(48000, 1.0), (44100, 1.0), (48000, 0.5), (44100, 2.3), (32000, 1.0)],
    )
    def test_length_matches_rate_ratio(self, src_rate: int, seconds: float) -> None:
        src = _tone(440, src_rate, seconds)
        out = resample_to_16k(src, src_rate)
        expected = round(src.size * SAMPLE_RATE / src_rate)
        # Rational L/M resampling lands within a sample of the ideal count.
        assert abs(out.size - expected) <= 1


class TestSilence:
    @pytest.mark.parametrize("src_rate", [44100, 48000, 16000])
    def test_silence_stays_silence(self, src_rate: int) -> None:
        out = resample_to_16k(np.zeros(src_rate, dtype=np.float32), src_rate)
        assert np.max(np.abs(out)) == 0.0


class TestToneFidelity:
    @pytest.mark.parametrize("src_rate", [44100, 48000])
    def test_speech_band_tone_frequency_preserved(self, src_rate: int) -> None:
        # A 1 kHz tone (squarely in the speech band) keeps its pitch and roughly
        # its amplitude through the downsample.
        src = _tone(1000, src_rate, 1.0, amp=0.5)
        out = resample_to_16k(src, src_rate)
        # Ignore the filter's startup transient before measuring.
        steady = out[len(out) // 4 :]
        assert abs(_dominant_freq(steady, SAMPLE_RATE) - 1000) < 15
        assert _rms(steady) == pytest.approx(_rms(src), rel=0.15)

    def test_multitone_in_band_preserved(self) -> None:
        src = _tone(500, 48000, 1.0, 0.3) + _tone(3000, 48000, 1.0, 0.3)
        out = resample_to_16k(src, 48000)
        steady = out[len(out) // 4 :]
        spectrum = np.abs(np.fft.rfft(steady * np.hanning(len(steady))))
        freqs = np.fft.rfftfreq(len(steady), 1 / SAMPLE_RATE)
        # Both tones survive with comparable energy; neither is filtered out.
        e500 = spectrum[np.argmin(np.abs(freqs - 500))]
        e3000 = spectrum[np.argmin(np.abs(freqs - 3000))]
        assert e500 > 0.2 * spectrum.max()
        assert e3000 > 0.2 * spectrum.max()


class TestAntiAliasing:
    def test_above_nyquist_tone_is_rejected_not_aliased(self) -> None:
        # 12 kHz at 48 kHz is above the 8 kHz destination Nyquist. Naive
        # decimation would fold it to a full-amplitude 4 kHz alias; the
        # anti-alias filter must suppress it instead.
        src = _tone(12000, 48000, 1.0, amp=0.5)
        out = resample_to_16k(src, 48000)
        steady = out[len(out) // 4 :]
        # >20 dB of rejection — Hamming windowed-sinc gives ~40 dB here.
        assert _rms(steady) < 0.1 * _rms(src)

    def test_in_band_tone_survives_where_alias_would_be(self) -> None:
        # Control: a real 4 kHz tone (the alias frequency above) passes cleanly,
        # proving the previous test rejected the alias, not the whole band.
        src = _tone(4000, 48000, 1.0, amp=0.5)
        out = resample_to_16k(src, 48000)
        steady = out[len(out) // 4 :]
        assert _rms(steady) > 0.7 * _rms(src)
        assert abs(_dominant_freq(steady, SAMPLE_RATE) - 4000) < 20


class TestDCGain:
    @pytest.mark.parametrize("src_rate", [44100, 48000])
    def test_constant_signal_amplitude_preserved(self, src_rate: int) -> None:
        src = np.full(src_rate, 0.4, dtype=np.float32)
        out = resample_to_16k(src, src_rate)
        steady = out[len(out) // 4 : -len(out) // 4]
        assert np.allclose(steady, 0.4, atol=1e-3)


class TestStreamingEqualsBatch:
    @pytest.mark.parametrize("src_rate", [44100, 48000, 16000, 32000])
    def test_arbitrary_block_split_matches_single_call(self, src_rate: int) -> None:
        rng = np.random.default_rng(1234)
        src = rng.standard_normal(src_rate).astype(np.float32) * 0.3
        batch = resample(src, src_rate)

        streamer = PolyphaseResampler(src_rate)
        # Irregular block sizes — the tap delivers whatever CoreAudio hands it.
        pieces, pos = [], 0
        for size in [128, 4096, 1, 999, 4096, 512, 7000, 63]:
            pieces.append(streamer.process(src[pos : pos + size]))
            pos += size
        pieces.append(streamer.process(src[pos:]))  # remainder
        streamed = np.concatenate(pieces)

        assert streamed.size == batch.size
        # State carried across blocks -> identical samples, not merely close.
        assert np.array_equal(streamed, batch)

    def test_empty_blocks_are_harmless(self) -> None:
        src_rate = 48000
        src = _tone(1000, src_rate, 0.2)
        streamer = PolyphaseResampler(src_rate)
        out = [streamer.process(np.zeros(0, dtype=np.float32))]
        out.append(streamer.process(src[: src.size // 2]))
        out.append(streamer.process(np.zeros(0, dtype=np.float32)))
        out.append(streamer.process(src[src.size // 2 :]))
        assert np.array_equal(np.concatenate(out), resample(src, src_rate))


class TestFloatRateHandling:
    def test_float_native_rate_reduces_like_its_integer(self) -> None:
        # CoreAudio reports the rate as a float (48000.0); it must behave
        # identically to the integer form.
        src = _tone(1000, 48000, 0.3)
        assert np.array_equal(resample(src, 48000.0), resample(src, 48000))
