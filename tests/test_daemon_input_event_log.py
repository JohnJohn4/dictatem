"""Hotkey input events are logged so a press that "did nothing" leaves a trace.

On the managed work laptop a hotkey press after a restart produced no log line
at all, so it was impossible to tell whether it never reached the daemon or was
dropped. Each KEY_DOWN / KEY_UP / ESC now logs the state transition, the
commands it produced, and its timings — event and state names only.
"""

from __future__ import annotations

import logging

import pytest

from dictatem.daemon import DaemonCore
from dictatem.state import Event, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from tests.fakes import (
    FakeAudioCapture,
    FakeClipboardIO,
    FakeForegroundTracker,
    FakeKeystrokeSender,
    FakeOverlayRenderer,
    FakeTranscriberBackend,
    FakeTrayRenderer,
)


@pytest.fixture
def core() -> DaemonCore:
    return DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(
            backend=FakeTranscriberBackend(result="hello"), clock=lambda: 0.0
        ),
        overlay=FakeOverlayRenderer(),
        tray=FakeTrayRenderer(),
        clipboard=FakeClipboardIO(),
        keystroke=FakeKeystrokeSender(),
        foreground=FakeForegroundTracker(target_id=42),
        last_paste_ttl_s=300.0,
    )


def _hotkey_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("Hotkey ")]


def test_key_down_from_idle_logs_record_start(
    core: DaemonCore, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="dictatem"):
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=1000)

    lines = _hotkey_lines(caplog)
    assert len(lines) == 1
    assert lines[0].startswith("Hotkey KEY_DOWN: IDLE -> ")
    assert "RECORD_START" in lines[0]
    assert "handled in" in lines[0]


def test_esc_while_idle_logs_a_no_op(
    core: DaemonCore, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="dictatem"):
        core.on_hotkey_event(Event.ESC, now_ms=1000)

    lines = _hotkey_lines(caplog)
    assert len(lines) == 1
    assert lines[0].startswith("Hotkey ESC: IDLE -> IDLE [no-op]")


def test_synthetic_tray_events_omit_the_lag(
    core: DaemonCore, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="dictatem"):
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)

    assert "lag n/a" in _hotkey_lines(caplog)[0]


def test_internal_events_are_not_logged_as_hotkey_input(
    core: DaemonCore, caplog: pytest.LogCaptureFixture
) -> None:
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=1000)
    with caplog.at_level(logging.INFO, logger="dictatem"):
        core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=1200)

    assert _hotkey_lines(caplog) == []
