"""Tests for the pure startup phase timer."""

from __future__ import annotations

import sys

import pytest

from dictatem.startup_timing import StartupTimer, process_age_s


def _clock(*readings: float):
    it = iter(readings)
    return lambda: next(it)


def test_marks_record_the_time_since_the_previous_mark() -> None:
    timer = StartupTimer(clock=_clock(10.0, 10.5, 12.0, 12.25))
    timer.mark("imports")
    timer.mark("hw probe")
    timer.mark("tray")
    assert timer.summary() == (
        "Startup timing: imports 0.50s | hw probe 1.50s | tray 0.25s | total 2.25s"
    )


def test_interpreter_time_leads_the_summary_and_counts_toward_the_total() -> None:
    timer = StartupTimer(clock=_clock(0.0, 1.0))
    timer.mark("imports")
    assert timer.summary(interpreter_s=0.4) == (
        "Startup timing: interpreter 0.40s | imports 1.00s | total 1.40s"
    )


def test_no_marks_still_reports_a_total() -> None:
    assert StartupTimer(clock=_clock(5.0)).summary() == "Startup timing: total 0.00s"


@pytest.mark.skipif(sys.platform != "win32", reason="GetProcessTimes is Windows-only")
def test_process_age_is_a_small_positive_number_on_windows() -> None:
    age = process_age_s()
    assert age is not None and 0.0 <= age < 3600.0


@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows returns None")
def test_process_age_is_none_off_windows() -> None:
    assert process_age_s() is None
