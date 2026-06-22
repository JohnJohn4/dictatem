"""Focus-drift detect-and-hold on the regular-dictation paste rail (ADR-0026 / #97).

Drives the full PTT → transcription → paste pipeline through fakes and asserts
that when the foreground changes between record-start and paste, a regular
dictation is HELD in the Most-recent buffer (with a quiet flash, no sound, no
refocus) rather than mispasted into the wrong window — and that the existing
"paste"/tray recovery then lands it in the right place. The comparison is pure
(``focus_drift``); the foreground capture is the thin adapter.
"""

from __future__ import annotations

from dataclasses import dataclass

from dictatem.daemon import DaemonCore
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


@dataclass
class _Rig:
    core: DaemonCore
    backend: FakeTranscriberBackend
    clipboard: FakeClipboardIO
    keystroke: FakeKeystrokeSender
    foreground: FakeForegroundTracker
    overlay: FakeOverlayRenderer
    tray: FakeTrayRenderer


def _make_rig(*, anchor_target: int = 42) -> _Rig:
    backend = FakeTranscriberBackend(result="hello world")
    clipboard = FakeClipboardIO()
    keystroke = FakeKeystrokeSender()
    foreground = FakeForegroundTracker(target_id=anchor_target)
    overlay = FakeOverlayRenderer()
    tray = FakeTrayRenderer()
    core = DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=overlay,
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=foreground,
    )
    return _Rig(
        core=core,
        backend=backend,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=foreground,
        overlay=overlay,
        tray=tray,
    )


def _hold_cycle(
    rig: _Rig, *, start_ms: int, end_ms: int, drift_to: int | None = None
) -> None:
    """A Hold dictation. If *drift_to* is given, the foreground changes to it
    after record-start (modelling the user clicking into another window during
    the load wait), so paste sees a different target than the anchor."""
    rig.core.on_hotkey_event(Event.KEY_DOWN, now_ms=start_ms)  # record-start: anchor
    if drift_to is not None:
        rig.foreground.set_target(drift_to)
    rig.core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=start_ms + 200)
    rig.core.on_hotkey_event(Event.KEY_UP, now_ms=end_ms)
    rig.core.drain_transcription_for_test(now_ms=end_ms)


def _set_texts(clipboard: FakeClipboardIO) -> list[str]:
    return [c[1] for c in clipboard.calls if c[0] == "set_text"]


class TestDriftHold:
    def test_drifted_dictation_is_not_pasted(self) -> None:
        rig = _make_rig()
        _hold_cycle(rig, start_ms=0, end_ms=1_000, drift_to=99)
        # Nothing typed/pasted: no Ctrl+V, no clipboard write.
        assert rig.keystroke.paste_count == 0
        assert _set_texts(rig.clipboard) == []

    def test_drifted_dictation_is_held_in_buffer(self) -> None:
        rig = _make_rig()
        _hold_cycle(rig, start_ms=0, end_ms=1_000, drift_to=99)
        # The text is retained for recovery, normalised like a real paste.
        assert rig.core._most_recent_dictation == "hello world "
        assert rig.tray.has_last_dictation is True

    def test_drift_hold_shows_quiet_flash(self) -> None:
        rig = _make_rig()
        _hold_cycle(rig, start_ms=0, end_ms=1_000, drift_to=99)
        # The "saved — say paste" flash reuses the overlay error flash, which
        # carries NO sound (there is no sound surface in Dictatem).
        assert ("show_error",) in rig.overlay.calls

    def test_drift_hold_never_restores_focus(self) -> None:
        rig = _make_rig()
        _hold_cycle(rig, start_ms=0, end_ms=1_000, drift_to=99)
        # Detect-and-hold NEVER moves the user's windows around (ADR-0026).
        assert rig.foreground.restored == []

    def test_drift_hold_arms_no_trigger_words(self) -> None:
        rig = _make_rig()
        _hold_cycle(rig, start_ms=0, end_ms=1_000, drift_to=99)
        # No successful paste → no Last Paste, so a Trigger Word can't fire at the
        # wrong window either.
        assert rig.core._last_paste is None

    def test_returns_to_idle_after_hold(self) -> None:
        rig = _make_rig()
        _hold_cycle(rig, start_ms=0, end_ms=1_000, drift_to=99)
        assert rig.core._sm.state == State.IDLE


class TestNoDrift:
    def test_unchanged_target_pastes_normally(self) -> None:
        rig = _make_rig()
        _hold_cycle(rig, start_ms=0, end_ms=1_000)  # no drift
        assert rig.keystroke.paste_count == 1
        assert _set_texts(rig.clipboard) == ["hello world "]
        assert rig.core._most_recent_dictation == "hello world "
        assert rig.core._last_paste is not None
        assert rig.core._last_paste.target_id == 42


class TestRecoveryAfterHold:
    def test_paste_action_recovers_held_dictation_at_new_window(self) -> None:
        # A dictation drifts and is held...
        rig = _make_rig()
        _hold_cycle(rig, start_ms=0, end_ms=1_000, drift_to=99)
        assert rig.keystroke.paste_count == 0
        assert rig.core._most_recent_dictation == "hello world "

        # ...the user focuses the right window (target 77) and says "paste". Its
        # record-start anchors 77 and paste sees 77 → no drift → the buffer lands.
        rig.foreground.set_target(77)
        rig.backend._result = "paste"
        _hold_cycle(rig, start_ms=5_000, end_ms=6_000)

        assert rig.keystroke.paste_count == 1
        assert _set_texts(rig.clipboard) == ["hello world "]
