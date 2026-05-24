"""Tests for the pure LatencyMonitor (clock-injected, no real timing).

LatencyMonitor watches a rolling window of real-time factors
(wall_time / audio_duration) and fires a one-shot "transcriptions are slow"
tip exactly once per session when the window is consistently poor. See
ADR-0007: rare, earned advice rather than repeated warnings.
"""

from __future__ import annotations

from dictatem.transcribe.latency_monitor import LatencyMonitor


class FakeClock:
    """Deterministic clock so begin()/end() produce known wall times."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _record(monitor: LatencyMonitor, clock: FakeClock, *, wall: float, audio: float) -> bool:
    """Drive one transcription: begin, advance the clock by *wall*, end."""
    monitor.begin()
    clock.advance(wall)
    return monitor.end(audio)


class TestFiresOnce:
    def test_fires_after_full_window_of_poor_samples(self) -> None:
        clock = FakeClock()
        monitor = LatencyMonitor(clock=clock, rtf_threshold=1.5, window=3)
        # rtf = 2.0 (wall 2.0 over 1.0s audio): poor.
        assert _record(monitor, clock, wall=2.0, audio=1.0) is False
        assert _record(monitor, clock, wall=2.0, audio=1.0) is False
        assert _record(monitor, clock, wall=2.0, audio=1.0) is True

    def test_never_fires_more_than_once_per_session(self) -> None:
        clock = FakeClock()
        monitor = LatencyMonitor(clock=clock, rtf_threshold=1.5, window=3)
        # Reach a full poor window so the tip fires.
        _record(monitor, clock, wall=2.0, audio=1.0)
        _record(monitor, clock, wall=2.0, audio=1.0)
        assert _record(monitor, clock, wall=2.0, audio=1.0) is True
        # Many more poor samples must never fire again — the latch holds.
        for _ in range(10):
            assert _record(monitor, clock, wall=2.0, audio=1.0) is False


class TestFastPathNeverFires:
    def test_fast_transcriptions_never_fire(self) -> None:
        clock = FakeClock()
        monitor = LatencyMonitor(clock=clock, rtf_threshold=1.5, window=3)
        # rtf = 0.5 (wall 0.5 over 1.0s audio): comfortably faster than realtime.
        for _ in range(10):
            assert _record(monitor, clock, wall=0.5, audio=1.0) is False

    def test_mixed_window_with_one_fast_sample_does_not_fire(self) -> None:
        clock = FakeClock()
        monitor = LatencyMonitor(clock=clock, rtf_threshold=1.5, window=3)
        # Two poor samples then one fast one keeps the window from being
        # uniformly poor — must not fire.
        assert _record(monitor, clock, wall=2.0, audio=1.0) is False
        assert _record(monitor, clock, wall=2.0, audio=1.0) is False
        assert _record(monitor, clock, wall=0.5, audio=1.0) is False
        # The fast sample is still in the window, so the next poor one also
        # must not fire.
        assert _record(monitor, clock, wall=2.0, audio=1.0) is False


class TestZeroDurationGuard:
    def test_zero_audio_duration_is_ignored_without_error(self) -> None:
        clock = FakeClock()
        monitor = LatencyMonitor(clock=clock, rtf_threshold=1.5, window=3)
        assert _record(monitor, clock, wall=2.0, audio=0.0) is False

    def test_negative_audio_duration_is_ignored_without_error(self) -> None:
        clock = FakeClock()
        monitor = LatencyMonitor(clock=clock, rtf_threshold=1.5, window=3)
        assert _record(monitor, clock, wall=2.0, audio=-1.0) is False

    def test_zero_duration_samples_do_not_count_toward_the_window(self) -> None:
        clock = FakeClock()
        monitor = LatencyMonitor(clock=clock, rtf_threshold=1.5, window=3)
        # Two zero-duration samples are ignored, so two real poor samples are
        # still not enough to fill the window.
        assert _record(monitor, clock, wall=2.0, audio=0.0) is False
        assert _record(monitor, clock, wall=2.0, audio=1.0) is False
        assert _record(monitor, clock, wall=2.0, audio=0.0) is False
        assert _record(monitor, clock, wall=2.0, audio=1.0) is False
        # Now the third real poor sample fills the window and fires.
        assert _record(monitor, clock, wall=2.0, audio=1.0) is True
