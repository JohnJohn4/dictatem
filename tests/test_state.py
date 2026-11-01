"""Exhaustive tests for the hybrid hotkey state machine.

All tests use a fake clock (now_ms parameter) — no real sleeps.
"""

from __future__ import annotations

from dictatem.state import Command, Event, State, StateMachine


class TestInitialState:
    def test_starts_idle(self) -> None:
        sm = StateMachine()
        assert sm.state is State.IDLE


class TestIdleToPressed:
    def test_key_down_transitions_to_pressed(self) -> None:
        sm = StateMachine()
        cmds = sm.handle(Event.KEY_DOWN, now_ms=0)
        assert sm.state is State.PRESSED
        assert Command.RECORD_START in cmds
        assert Command.START_TAP_TIMER in cmds

    def test_key_up_in_idle_is_ignored(self) -> None:
        sm = StateMachine()
        cmds = sm.handle(Event.KEY_UP, now_ms=0)
        assert sm.state is State.IDLE
        assert cmds == []

    def test_esc_in_idle_is_ignored(self) -> None:
        sm = StateMachine()
        cmds = sm.handle(Event.ESC, now_ms=0)
        assert sm.state is State.IDLE
        assert cmds == []


class TestTapToToggle:
    """KeyUp before 200 ms threshold → TOGGLE_REC."""

    def test_quick_release_transitions_to_toggle_rec(self) -> None:
        sm = StateMachine(tap_threshold_ms=200)
        sm.handle(Event.KEY_DOWN, now_ms=0)
        cmds = sm.handle(Event.KEY_UP, now_ms=100)
        assert sm.state is State.TOGGLE_REC
        assert Command.CANCEL_TAP_TIMER in cmds
        assert Command.RECORD_STOP_AND_TRANSCRIBE not in cmds

    def test_release_at_exact_threshold_is_hold(self) -> None:
        sm = StateMachine(tap_threshold_ms=200)
        sm.handle(Event.KEY_DOWN, now_ms=0)
        cmds = sm.handle(Event.KEY_UP, now_ms=200)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds

    def test_release_after_threshold_is_hold(self) -> None:
        sm = StateMachine(tap_threshold_ms=200)
        sm.handle(Event.KEY_DOWN, now_ms=0)
        cmds = sm.handle(Event.KEY_UP, now_ms=300)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds


class TestHoldToPTT:
    """200 ms timer fires while held → PTT_REC."""

    def test_timer_expired_transitions_to_ptt_rec(self) -> None:
        sm = StateMachine(tap_threshold_ms=200)
        sm.handle(Event.KEY_DOWN, now_ms=0)
        cmds = sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC
        assert cmds == []


class TestToggleRecExits:
    def test_key_down_stops_and_transcribes(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        assert sm.state is State.TOGGLE_REC

        cmds = sm.handle(Event.KEY_DOWN, now_ms=1000)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds

    def test_esc_cancels_to_idle(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        assert sm.state is State.TOGGLE_REC

        cmds = sm.handle(Event.ESC, now_ms=500)
        assert sm.state is State.IDLE
        assert Command.CANCEL in cmds
        assert Command.PASTE not in cmds

    def test_silence_timeout_stops_and_transcribes(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        assert sm.state is State.TOGGLE_REC

        # Silence stops-and-transcribes like MAX_DURATION — never discards (#191).
        cmds = sm.handle(Event.SILENCE_TIMEOUT, now_ms=60_000)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds
        assert Command.CANCEL not in cmds


class TestPTTRecExits:
    def test_key_up_stops_and_transcribes(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        cmds = sm.handle(Event.KEY_UP, now_ms=1500)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds

    def test_esc_cancels_to_idle(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        cmds = sm.handle(Event.ESC, now_ms=500)
        assert sm.state is State.IDLE
        assert Command.CANCEL in cmds
        assert Command.PASTE not in cmds

    def test_silence_timeout_stops_and_transcribes(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        # Silence stops-and-transcribes like MAX_DURATION — never discards (#191).
        cmds = sm.handle(Event.SILENCE_TIMEOUT, now_ms=60_200)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds
        assert Command.CANCEL not in cmds


class TestTranscribing:
    def _enter_transcribing_via_toggle(self, sm: StateMachine) -> None:
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        sm.handle(Event.KEY_DOWN, now_ms=1000)
        assert sm.state is State.TRANSCRIBING

    def _enter_transcribing_via_ptt(self, sm: StateMachine) -> None:
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        sm.handle(Event.KEY_UP, now_ms=1500)
        assert sm.state is State.TRANSCRIBING

    def test_done_pastes_and_returns_to_idle(self) -> None:
        sm = StateMachine()
        self._enter_transcribing_via_toggle(sm)
        cmds = sm.handle(Event.TRANSCRIPTION_DONE, now_ms=2000)
        assert sm.state is State.IDLE
        assert Command.PASTE in cmds

    def test_done_from_ptt_pastes_and_returns_to_idle(self) -> None:
        sm = StateMachine()
        self._enter_transcribing_via_ptt(sm)
        cmds = sm.handle(Event.TRANSCRIPTION_DONE, now_ms=2000)
        assert sm.state is State.IDLE
        assert Command.PASTE in cmds

    def test_esc_cancels_without_paste(self) -> None:
        sm = StateMachine()
        self._enter_transcribing_via_toggle(sm)
        cmds = sm.handle(Event.ESC, now_ms=1500)
        assert sm.state is State.IDLE
        assert Command.CANCEL in cmds
        assert Command.PASTE not in cmds

    def test_borderline_flashes_say_again_no_paste(self) -> None:
        sm = StateMachine()
        self._enter_transcribing_via_toggle(sm)
        cmds = sm.handle(Event.BORDERLINE, now_ms=2000)
        assert sm.state is State.IDLE
        assert cmds == [Command.FLASH_SAY_AGAIN]

    def test_empty_result_flashes_error_no_paste(self) -> None:
        sm = StateMachine()
        self._enter_transcribing_via_toggle(sm)
        cmds = sm.handle(Event.EMPTY_RESULT, now_ms=2000)
        assert sm.state is State.IDLE
        assert Command.FLASH_ERROR in cmds
        assert Command.PASTE not in cmds


class TestAutoRepeatSuppression:
    def test_key_down_while_pressed_is_ignored(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        assert sm.state is State.PRESSED

        cmds = sm.handle(Event.KEY_DOWN, now_ms=30)
        assert sm.state is State.PRESSED
        assert cmds == []

    def test_key_down_while_ptt_rec_is_ignored(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        cmds = sm.handle(Event.KEY_DOWN, now_ms=300)
        assert sm.state is State.PTT_REC
        assert cmds == []


class TestBusyNudge:
    """A hotkey press while working nudges the user and changes nothing (#240)."""

    def _enter_transcribing(self, sm: StateMachine) -> None:
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        sm.handle(Event.KEY_DOWN, now_ms=1000)
        assert sm.state is State.TRANSCRIBING

    def test_key_down_while_transcribing_emits_only_the_busy_nudge(self) -> None:
        sm = StateMachine()
        self._enter_transcribing(sm)

        cmds = sm.handle(Event.KEY_DOWN, now_ms=1500)
        assert sm.state is State.TRANSCRIBING
        assert cmds == [Command.BUSY_NUDGE]

    def test_repeated_presses_each_nudge_and_stay_transcribing(self) -> None:
        sm = StateMachine()
        self._enter_transcribing(sm)

        for t in (1500, 1600, 1700):
            assert sm.handle(Event.KEY_DOWN, now_ms=t) == [Command.BUSY_NUDGE]
            assert sm.handle(Event.KEY_UP, now_ms=t + 50) == []
        assert sm.state is State.TRANSCRIBING

    def test_result_after_a_nudge_still_pastes(self) -> None:
        sm = StateMachine()
        self._enter_transcribing(sm)
        sm.handle(Event.KEY_DOWN, now_ms=1500)
        sm.handle(Event.KEY_UP, now_ms=1550)

        cmds = sm.handle(Event.TRANSCRIPTION_DONE, now_ms=2000)
        assert sm.state is State.IDLE
        assert cmds == [Command.PASTE]

    def test_esc_after_a_nudge_still_cancels(self) -> None:
        sm = StateMachine()
        self._enter_transcribing(sm)
        sm.handle(Event.KEY_DOWN, now_ms=1500)

        assert sm.handle(Event.ESC, now_ms=1600) == [Command.CANCEL]
        assert sm.state is State.IDLE


class TestEscFromAnyActiveState:
    def test_esc_from_pressed(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        cmds = sm.handle(Event.ESC, now_ms=50)
        assert sm.state is State.IDLE
        assert Command.CANCEL in cmds
        assert Command.PASTE not in cmds

    def test_esc_from_toggle_rec(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        cmds = sm.handle(Event.ESC, now_ms=500)
        assert sm.state is State.IDLE
        assert Command.CANCEL in cmds
        assert Command.PASTE not in cmds

    def test_esc_from_ptt_rec(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        cmds = sm.handle(Event.ESC, now_ms=500)
        assert sm.state is State.IDLE
        assert Command.CANCEL in cmds
        assert Command.PASTE not in cmds

    def test_esc_from_transcribing(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        sm.handle(Event.KEY_DOWN, now_ms=1000)
        cmds = sm.handle(Event.ESC, now_ms=1500)
        assert sm.state is State.IDLE
        assert Command.CANCEL in cmds
        assert Command.PASTE not in cmds


class TestSilenceTimeoutFromActiveStates:
    """Silence timeout mirrors MAX_DURATION: stop-and-transcribe, never discard
    (#191). A user who dictates then pauses must not lose the recording."""

    def test_silence_from_toggle_rec(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        cmds = sm.handle(Event.SILENCE_TIMEOUT, now_ms=60_050)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds
        assert Command.CANCEL not in cmds

    def test_silence_from_ptt_rec(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        cmds = sm.handle(Event.SILENCE_TIMEOUT, now_ms=60_200)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds
        assert Command.CANCEL not in cmds


class TestMaxDurationFromActiveStates:
    def test_max_duration_from_toggle_rec_transcribes(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        assert sm.state is State.TOGGLE_REC

        cmds = sm.handle(Event.MAX_DURATION, now_ms=300_050)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds
        assert Command.CANCEL not in cmds

    def test_max_duration_from_ptt_rec_transcribes(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        cmds = sm.handle(Event.MAX_DURATION, now_ms=300_200)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds
        assert Command.CANCEL not in cmds


class TestFullCycleRoundTrips:
    def test_toggle_happy_path(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        sm.handle(Event.KEY_DOWN, now_ms=5000)
        sm.handle(Event.TRANSCRIPTION_DONE, now_ms=6000)
        assert sm.state is State.IDLE

    def test_ptt_happy_path(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.TIMER_EXPIRED, now_ms=200)
        sm.handle(Event.KEY_UP, now_ms=3000)
        sm.handle(Event.TRANSCRIPTION_DONE, now_ms=4000)
        assert sm.state is State.IDLE

    def test_multiple_cycles(self) -> None:
        sm = StateMachine()
        for cycle in range(3):
            base = cycle * 10_000
            sm.handle(Event.KEY_DOWN, now_ms=base)
            sm.handle(Event.KEY_UP, now_ms=base + 50)
            sm.handle(Event.KEY_DOWN, now_ms=base + 1000)
            sm.handle(Event.TRANSCRIPTION_DONE, now_ms=base + 2000)
            assert sm.state is State.IDLE

    def test_cancel_then_restart(self) -> None:
        sm = StateMachine()
        sm.handle(Event.KEY_DOWN, now_ms=0)
        sm.handle(Event.KEY_UP, now_ms=50)
        sm.handle(Event.ESC, now_ms=500)
        assert sm.state is State.IDLE

        sm.handle(Event.KEY_DOWN, now_ms=1000)
        sm.handle(Event.TIMER_EXPIRED, now_ms=1200)
        sm.handle(Event.KEY_UP, now_ms=3000)
        sm.handle(Event.TRANSCRIPTION_DONE, now_ms=4000)
        assert sm.state is State.IDLE


class TestReset:
    """``reset()`` is the public recovery path back to IDLE (#234)."""

    def test_reset_from_every_state_returns_to_idle(self) -> None:
        reach: dict[State, list[tuple[Event, int]]] = {
            State.IDLE: [],
            State.PRESSED: [(Event.KEY_DOWN, 0)],
            State.TOGGLE_REC: [(Event.KEY_DOWN, 0), (Event.KEY_UP, 50)],
            State.PTT_REC: [(Event.KEY_DOWN, 0), (Event.TIMER_EXPIRED, 200)],
            State.TRANSCRIBING: [
                (Event.KEY_DOWN, 0),
                (Event.TIMER_EXPIRED, 200),
                (Event.KEY_UP, 3000),
            ],
        }
        for target, events in reach.items():
            sm = StateMachine(tap_threshold_ms=200)
            for ev, at in events:
                sm.handle(ev, now_ms=at)
            assert sm.state is target
            sm.reset()
            assert sm.state is State.IDLE

    def test_reset_emits_no_commands_and_next_press_starts_fresh(self) -> None:
        sm = StateMachine(tap_threshold_ms=200)
        sm.handle(Event.KEY_DOWN, now_ms=0)
        assert sm.reset() is None
        # A stray KEY_UP after reset is ignored (the press was forgotten).
        assert sm.handle(Event.KEY_UP, now_ms=10_000) == []
        assert sm.state is State.IDLE
        # A new press is timed from its own KEY_DOWN, not the forgotten one.
        sm.handle(Event.KEY_DOWN, now_ms=20_000)
        sm.handle(Event.KEY_UP, now_ms=20_050)
        assert sm.state is State.TOGGLE_REC


class TestConfigurableThresholds:
    def test_custom_tap_threshold(self) -> None:
        sm = StateMachine(tap_threshold_ms=500)
        sm.handle(Event.KEY_DOWN, now_ms=0)
        cmds = sm.handle(Event.KEY_UP, now_ms=400)
        assert sm.state is State.TOGGLE_REC
        assert Command.CANCEL_TAP_TIMER in cmds

    def test_custom_tap_threshold_hold(self) -> None:
        sm = StateMachine(tap_threshold_ms=500)
        sm.handle(Event.KEY_DOWN, now_ms=0)
        cmds = sm.handle(Event.KEY_UP, now_ms=500)
        assert sm.state is State.TRANSCRIBING
        assert Command.RECORD_STOP_AND_TRANSCRIBE in cmds


class TestEnumCompleteness:
    def test_all_states_defined(self) -> None:
        expected = {"IDLE", "PRESSED", "PTT_REC", "TOGGLE_REC", "TRANSCRIBING"}
        assert set(State.__members__) == expected

    def test_all_events_defined(self) -> None:
        expected = {
            "KEY_DOWN", "KEY_UP", "ESC", "TIMER_EXPIRED",
            "SILENCE_TIMEOUT", "MAX_DURATION", "TRANSCRIPTION_DONE",
            "EMPTY_RESULT", "BORDERLINE",
        }
        assert set(Event.__members__) == expected

    def test_all_commands_defined(self) -> None:
        expected = {
            "RECORD_START", "RECORD_STOP_AND_TRANSCRIBE", "CANCEL", "PASTE",
            "FLASH_ERROR", "FLASH_SAY_AGAIN", "START_TAP_TIMER", "CANCEL_TAP_TIMER",
            "BUSY_NUDGE",
        }
        assert set(Command.__members__) == expected


class TestImportPurity:
    """state.py must not pull in any I/O libraries."""

    def test_no_io_imports(self) -> None:
        import importlib
        import sys

        before = set(sys.modules.keys())
        importlib.reload(importlib.import_module("dictatem.state"))
        after = set(sys.modules.keys())
        new = after - before

        forbidden = [
            "numpy", "sounddevice", "PySide6", "faster_whisper",
            "ctranslate2", "pywin32", "win32api", "win32con",
            "win32clipboard", "win32gui", "pywintypes",
        ]
        for lib in forbidden:
            violations = [m for m in new if m == lib or m.startswith(lib + ".")]
            assert violations == [], f"state.py pulled in forbidden module: {violations}"
