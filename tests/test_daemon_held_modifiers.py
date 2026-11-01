"""Daemon handling of a modifier still held past the paste wait (#269).

When Alt/Win/Shift/Ctrl stays down past the bounded wait, the pipeline raises
``ModifiersHeldError`` with nothing injected; the daemon must hold a regular
dictation for recovery (the quiet Held signal, like focus drift), not inject
key-ups under the user's fingers and not flash an error.
"""

from __future__ import annotations

import functools

import pytest

import dictatem.paste.pipeline as pipeline
from dictatem.daemon import DaemonCore
from dictatem.paste.modifier_wait import wait_for_modifiers_released
from dictatem.state import Event, State, StateMachine
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


@pytest.fixture(autouse=True)
def _short_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the real-clock wait in these daemon-level tests to a few ms.
    monkeypatch.setattr(
        pipeline,
        "wait_for_modifiers_released",
        functools.partial(wait_for_modifiers_released, cap_s=0.02, poll_s=0.005),
    )


def _core(keystroke: FakeKeystrokeSender) -> tuple[
    DaemonCore, FakeClipboardIO, FakeOverlayRenderer, FakeTrayRenderer
]:
    clipboard = FakeClipboardIO()
    overlay = FakeOverlayRenderer()
    tray = FakeTrayRenderer()
    core = DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(
            backend=FakeTranscriberBackend(result="hello world"), clock=lambda: 0.0
        ),
        overlay=overlay,
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=FakeForegroundTracker(target_id=42),
    )
    return core, clipboard, overlay, tray


def _dictate(core: DaemonCore, start_ms: int) -> None:
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=start_ms)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=start_ms + 200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=start_ms + 1_000)
    core.drain_transcription_for_test(now_ms=start_ms + 1_000)


def test_released_in_time_pastes_normally() -> None:
    ks = FakeKeystrokeSender()
    ks.held_script = [frozenset({"alt"}), frozenset()]
    core, _clip, overlay, _tray = _core(ks)
    _dictate(core, 0)
    assert ks.paste_count == 1
    assert ("show_held",) not in overlay.calls
    assert core._last_paste is not None


def test_still_held_dictation_is_held_for_recovery() -> None:
    ks = FakeKeystrokeSender()
    ks.held_script = [frozenset({"win", "alt"})]
    core, clipboard, overlay, tray = _core(ks)
    _dictate(core, 0)
    assert ks.events == []  # nothing injected
    assert clipboard.calls == []
    assert core._most_recent_dictation == "hello world "
    assert tray.has_last_dictation is True
    assert ("show_held",) in overlay.calls
    assert ("show_error",) not in overlay.calls
    assert core._sm.state == State.IDLE


def test_still_held_keeps_the_previous_last_paste_armed() -> None:
    # Nothing was typed, so the previous Last Paste is still what's on screen.
    ks = FakeKeystrokeSender()
    core, _clip, _overlay, _tray = _core(ks)
    _dictate(core, 0)
    first = core._last_paste
    assert first is not None
    ks.held_script = [frozenset({"alt"})]
    _dictate(core, 5_000)
    assert core._last_paste is first
