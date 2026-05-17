"""Hybrid hotkey state machine — pure logic, no I/O dependencies.

Receives events (KeyDown, KeyUp, Esc, timer/silence signals, transcription
results) and emits high-level commands.  Depends only on stdlib; the
tap-vs-hold threshold is configurable and time is caller-supplied so tests
run in milliseconds.
"""

from __future__ import annotations

import enum
from collections.abc import Callable


class State(enum.Enum):
    IDLE = "idle"
    PRESSED = "pressed"
    PTT_REC = "ptt_rec"
    TOGGLE_REC = "toggle_rec"
    TRANSCRIBING = "transcribing"


class Event(enum.Enum):
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"
    ESC = "esc"
    TIMER_EXPIRED = "timer_expired"
    SILENCE_TIMEOUT = "silence_timeout"
    MAX_DURATION = "max_duration"
    TRANSCRIPTION_DONE = "transcription_done"
    EMPTY_RESULT = "empty_result"
    OOM = "oom"


class Command(enum.Enum):
    RECORD_START = "record_start"
    RECORD_STOP_AND_TRANSCRIBE = "record_stop_and_transcribe"
    CANCEL = "cancel"
    PASTE = "paste"
    FLASH_ERROR = "flash_error"
    START_TAP_TIMER = "start_tap_timer"
    CANCEL_TAP_TIMER = "cancel_tap_timer"
    RETRY_TRANSCRIPTION = "retry_transcription"
    NOTIFY_ERROR = "notify_error"


class StateMachine:
    def __init__(self, *, tap_threshold_ms: int = 200) -> None:
        self._state = State.IDLE
        self._tap_threshold_ms = tap_threshold_ms
        self._key_down_at: int | None = None
        self._oom_retried: bool = False

    @property
    def state(self) -> State:
        return self._state

    def handle(self, event: Event, *, now_ms: int = 0) -> list[Command]:
        handler = _HANDLERS.get((self._state, event))
        if handler is None:
            return []
        return handler(self, now_ms)

    # -- IDLE handlers --

    def _idle_key_down(self, now_ms: int) -> list[Command]:
        self._key_down_at = now_ms
        self._state = State.PRESSED
        return [Command.RECORD_START, Command.START_TAP_TIMER]

    # -- PRESSED handlers --

    def _pressed_key_up(self, now_ms: int) -> list[Command]:
        assert self._key_down_at is not None
        if now_ms - self._key_down_at < self._tap_threshold_ms:
            self._state = State.TOGGLE_REC
            return [Command.CANCEL_TAP_TIMER]
        self._state = State.TRANSCRIBING
        self._oom_retried = False
        return [Command.RECORD_STOP_AND_TRANSCRIBE]

    def _pressed_timer_expired(self, _now_ms: int) -> list[Command]:
        self._state = State.PTT_REC
        return []

    def _pressed_esc(self, _now_ms: int) -> list[Command]:
        self._state = State.IDLE
        self._key_down_at = None
        return [Command.CANCEL_TAP_TIMER, Command.CANCEL]

    # -- shared cancel handler (used by TOGGLE_REC, PTT_REC, TRANSCRIBING) --

    def _cancel_to_idle(self, _now_ms: int) -> list[Command]:
        self._state = State.IDLE
        return [Command.CANCEL]

    # -- TOGGLE_REC handlers --

    def _toggle_key_down(self, _now_ms: int) -> list[Command]:
        self._state = State.TRANSCRIBING
        self._oom_retried = False
        return [Command.RECORD_STOP_AND_TRANSCRIBE]

    # -- PTT_REC handlers --

    def _ptt_key_up(self, _now_ms: int) -> list[Command]:
        self._state = State.TRANSCRIBING
        self._oom_retried = False
        return [Command.RECORD_STOP_AND_TRANSCRIBE]

    # -- TRANSCRIBING handlers --

    def _transcribing_done(self, _now_ms: int) -> list[Command]:
        self._state = State.IDLE
        return [Command.PASTE]

    def _transcribing_empty(self, _now_ms: int) -> list[Command]:
        self._state = State.IDLE
        return [Command.FLASH_ERROR]

    def _transcribing_oom(self, _now_ms: int) -> list[Command]:
        if not self._oom_retried:
            self._oom_retried = True
            return [Command.RETRY_TRANSCRIPTION]
        self._state = State.IDLE
        self._oom_retried = False
        return [Command.NOTIFY_ERROR]


_Handler = Callable[["StateMachine", int], list[Command]]

_HANDLERS: dict[tuple[State, Event], _Handler] = {
    (State.IDLE, Event.KEY_DOWN): StateMachine._idle_key_down,
    (State.PRESSED, Event.KEY_UP): StateMachine._pressed_key_up,
    (State.PRESSED, Event.TIMER_EXPIRED): StateMachine._pressed_timer_expired,
    (State.PRESSED, Event.ESC): StateMachine._pressed_esc,
    (State.TOGGLE_REC, Event.KEY_DOWN): StateMachine._toggle_key_down,
    (State.TOGGLE_REC, Event.ESC): StateMachine._cancel_to_idle,
    (State.TOGGLE_REC, Event.SILENCE_TIMEOUT): StateMachine._cancel_to_idle,
    (State.TOGGLE_REC, Event.MAX_DURATION): StateMachine._toggle_key_down,
    (State.PTT_REC, Event.KEY_UP): StateMachine._ptt_key_up,
    (State.PTT_REC, Event.ESC): StateMachine._cancel_to_idle,
    (State.PTT_REC, Event.SILENCE_TIMEOUT): StateMachine._cancel_to_idle,
    (State.PTT_REC, Event.MAX_DURATION): StateMachine._ptt_key_up,
    (State.TRANSCRIBING, Event.TRANSCRIPTION_DONE): StateMachine._transcribing_done,
    (State.TRANSCRIBING, Event.ESC): StateMachine._cancel_to_idle,
    (State.TRANSCRIBING, Event.EMPTY_RESULT): StateMachine._transcribing_empty,
    (State.TRANSCRIBING, Event.OOM): StateMachine._transcribing_oom,
}
