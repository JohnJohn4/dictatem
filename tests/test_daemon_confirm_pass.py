"""Borderline confirm pass — one command-biased re-listen before say-again (#249).

On a first-pass Borderline the daemon re-transcribes the same audio once,
biased toward the lexicon's Trigger Words with VAD off. If that confirm pass is
an exact or strong-confident match for one of the Borderline's candidate
actions, the normal Trigger Fire runs (rails included); otherwise the
say-again flash, as before (ADR-0028). The pill stays "transcribing"
throughout, and Esc discards the confirm pass like any in-flight transcription.
"""

from __future__ import annotations

import logging

import pytest

from dictatem.daemon import DaemonCore
from dictatem.exceptions import GPUOutOfMemoryError
from dictatem.state import Event, State, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.transform.lifecycle import TransformLifecycle
from dictatem.transform.recognizer import TriggerWordRecognizer
from dictatem.types import SegmentConfidence, Transcript
from tests.fakes import (
    FakeAudioCapture,
    FakeClipboardIO,
    FakeForegroundTracker,
    FakeKeystrokeSender,
    FakeOverlayRenderer,
    FakeTranscriberBackend,
    FakeTransformBackend,
    FakeTrayRenderer,
)

SUMMARIZE_PROMPT = "SYSTEM: summarize this text."
POLISH_PROMPT = "SYSTEM: polish this text."
ALIASES = {
    "summarize": SUMMARIZE_PROMPT,
    "summarise": SUMMARIZE_PROMPT,
    "polish": POLISH_PROMPT,
}
CONFIDENT = SegmentConfidence(avg_logprob=-0.3, no_speech_prob=0.05)
UNSURE = SegmentConfidence(avg_logprob=-1.8, no_speech_prob=0.05)
SOME_OF_US = Transcript("some of us", confidence=CONFIDENT, speech_duration_s=0.7)


@pytest.fixture
def backend() -> FakeTranscriberBackend:
    return FakeTranscriberBackend(result="hello world")


@pytest.fixture
def clipboard() -> FakeClipboardIO:
    return FakeClipboardIO()


@pytest.fixture
def keystroke() -> FakeKeystrokeSender:
    return FakeKeystrokeSender()


@pytest.fixture
def overlay() -> FakeOverlayRenderer:
    return FakeOverlayRenderer()


@pytest.fixture
def foreground() -> FakeForegroundTracker:
    return FakeForegroundTracker(target_id=42)


@pytest.fixture
def transform_backend() -> FakeTransformBackend:
    return FakeTransformBackend(result="A summary.")


@pytest.fixture
def tray() -> FakeTrayRenderer:
    return FakeTrayRenderer()


@pytest.fixture
def sm() -> StateMachine:
    return StateMachine(tap_threshold_ms=200)


@pytest.fixture
def recognizer() -> TriggerWordRecognizer:
    return TriggerWordRecognizer(ALIASES)


@pytest.fixture
def core(
    sm: StateMachine,
    backend: FakeTranscriberBackend,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    overlay: FakeOverlayRenderer,
    foreground: FakeForegroundTracker,
    transform_backend: FakeTransformBackend,
    recognizer: TriggerWordRecognizer,
    tray: FakeTrayRenderer,
) -> DaemonCore:
    return DaemonCore(
        state_machine=sm,
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=overlay,
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=foreground,
        transform_lifecycle=TransformLifecycle(backend=transform_backend),
        trigger_recognizer=recognizer,
        transform_enabled=True,
        last_paste_ttl_s=300.0,
    )


def _record(core: DaemonCore, *, start_ms: int, end_ms: int) -> None:
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=start_ms)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=start_ms + 200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=end_ms)


def _cycle(core: DaemonCore, *, start_ms: int, end_ms: int) -> None:
    _record(core, start_ms=start_ms, end_ms=end_ms)
    core.drain_transcription_for_test(now_ms=end_ms)


def _dictate_hello(core: DaemonCore, keystroke: FakeKeystrokeSender) -> None:
    """A regular dictation first, so Transforms are armed (a Last Paste)."""
    _cycle(core, start_ms=0, end_ms=1_000)
    assert keystroke.paste_count == 1


class TestConfirmPassRuns:
    def test_borderline_triggers_one_command_biased_confirm_of_the_same_audio(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        recognizer: TriggerWordRecognizer,
    ) -> None:
        _dictate_hello(core, keystroke)
        backend._result = SOME_OF_US
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert len(backend.command_calls) == 1
        audio, words = backend.command_calls[0]
        assert audio is backend.transcribe_calls[-1]
        assert words == tuple(recognizer.trigger_words(transforms_armed=True))
        assert "summarise" in words and "paste" in words

    def test_successful_confirm_runs_the_trigger_fire(
        self,
        core: DaemonCore,
        sm: StateMachine,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        transform_backend: FakeTransformBackend,
    ) -> None:
        _dictate_hello(core, keystroke)
        backend._result = SOME_OF_US
        backend.command_result = Transcript("Summarise.", confidence=CONFIDENT)
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert transform_backend.calls == [("hello world ", SUMMARIZE_PROMPT)]
        assert keystroke.total_backspaces == len("hello world ")
        assert any("A summary." in t for t in keystroke.typed_texts)
        assert ("show_say_again",) not in overlay.calls
        assert sm.state is State.IDLE


class TestConfirmPassOutcomes:
    def test_a_confirmed_paste_candidate_runs_the_builtin_paste(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
    ) -> None:
        _dictate_hello(core, keystroke)
        backend._result = Transcript("haste", confidence=UNSURE, speech_duration_s=0.5)
        backend.command_result = Transcript("Paste.", confidence=CONFIDENT)
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert keystroke.paste_count == 2  # the Most-recent dictation re-pasted
        assert [c[1] for c in clipboard.calls if c[0] == "set_text"][-1] == "hello world "

    def test_confirmed_trigger_fire_still_checks_the_rails(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        foreground: FakeForegroundTracker,
        transform_backend: FakeTransformBackend,
    ) -> None:
        _dictate_hello(core, keystroke)
        foreground.set_target(77)  # focus moved off the Last Paste's window
        backend._result = SOME_OF_US
        backend.command_result = Transcript("Summarise.", confidence=CONFIDENT)
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert transform_backend.calls == []
        assert keystroke.total_backspaces == 0
        assert ("show_error",) in overlay.calls

    @pytest.mark.parametrize(
        "heard_again",
        [
            pytest.param(Transcript("some of us", confidence=CONFIDENT), id="same"),
            pytest.param(Transcript("Polish.", confidence=CONFIDENT), id="other-action"),
            pytest.param(Transcript("Summerise.", confidence=UNSURE), id="unsure-strong"),
            pytest.param(" . ", id="empty"),
        ],
    )
    def test_unconfirmed_flashes_say_again_with_nothing_pasted(
        self,
        core: DaemonCore,
        sm: StateMachine,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        transform_backend: FakeTransformBackend,
        heard_again: Transcript | str,
    ) -> None:
        _dictate_hello(core, keystroke)
        backend._result = SOME_OF_US
        backend.command_result = heard_again
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert keystroke.paste_count == 1
        assert keystroke.typed_texts == []
        assert transform_backend.calls == []
        assert overlay.calls[-1] == ("show_say_again",)
        assert sm.state is State.IDLE

    def _first_pass_then(self, core: DaemonCore, backend: FakeTranscriberBackend) -> None:
        """Record a Borderline and let the first pass finish, confirm pass not yet run."""
        backend._result = SOME_OF_US
        _record(core, start_ms=2_000, end_ms=3_000)
        assert core._transcription_thread is not None
        core._transcription_thread.join(timeout=5.0)

    def test_unexpected_confirm_pass_error_flashes_say_again(
        self,
        core: DaemonCore,
        sm: StateMachine,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
    ) -> None:
        _dictate_hello(core, keystroke)
        self._first_pass_then(core, backend)
        backend.queue_error(RuntimeError("decoder hiccup"))
        core.drain_transcription_for_test(now_ms=3_000)

        assert len(backend.command_calls) == 1
        assert keystroke.paste_count == 1
        assert overlay.calls[-1] == ("show_say_again",)
        assert tray.notifications == []
        assert sm.state is State.IDLE

    def test_gpu_out_of_memory_after_retry_is_surfaced_like_the_first_pass(
        self,
        core: DaemonCore,
        sm: StateMachine,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
    ) -> None:
        _dictate_hello(core, keystroke)
        self._first_pass_then(core, backend)
        backend.queue_error(GPUOutOfMemoryError("first"))
        backend.queue_error(GPUOutOfMemoryError("retry"))
        core.drain_transcription_for_test(now_ms=3_000)

        assert len(backend.command_calls) == 2  # the lifecycle retried once
        assert keystroke.paste_count == 1
        assert ("show_say_again",) not in overlay.calls
        assert tray.notifications == [
            ("Transcription Failed", "GPU memory exhausted; transcription failed.")
        ]
        assert sm.state is State.IDLE

    def test_model_load_failure_is_surfaced_like_the_first_pass(
        self,
        core: DaemonCore,
        sm: StateMachine,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
    ) -> None:
        _dictate_hello(core, keystroke)
        self._first_pass_then(core, backend)
        # The model goes away between passes and can no longer be loaded.
        backend.unload_model()
        backend.fail_load_always(RuntimeError("CUDA driver missing"))
        core.drain_transcription_for_test(now_ms=3_000)

        assert keystroke.paste_count == 1
        assert ("show_say_again",) not in overlay.calls
        assert len(tray.notifications) == 1
        assert sm.state is State.IDLE


class TestConfirmPassInFlight:
    def _start_held_confirm(
        self, core: DaemonCore, backend: FakeTranscriberBackend
    ) -> None:
        backend._result = SOME_OF_US
        backend.command_result = Transcript("Summarise.", confidence=CONFIDENT)
        backend.block_command()
        _record(core, start_ms=2_000, end_ms=3_000)
        assert core._transcription_thread is not None
        core._transcription_thread.join(timeout=5.0)
        core.check_transcription_result(now_ms=3_000)  # first pass: Borderline
        assert len(backend.command_calls) == 1  # confirm pass parked in flight

    def test_pill_stays_transcribing_during_the_confirm_pass(
        self,
        core: DaemonCore,
        sm: StateMachine,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
    ) -> None:
        _dictate_hello(core, keystroke)
        self._start_held_confirm(core, backend)

        assert overlay.state == "transcribing"
        assert sm.state is State.TRANSCRIBING
        backend.release_command()
        core.drain_transcription_for_test(now_ms=3_100)

    def test_esc_during_the_confirm_pass_discards_it(
        self,
        core: DaemonCore,
        sm: StateMachine,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        transform_backend: FakeTransformBackend,
    ) -> None:
        _dictate_hello(core, keystroke)
        self._start_held_confirm(core, backend)

        core.on_hotkey_event(Event.ESC, now_ms=3_050)
        backend.release_command()
        core.drain_transcription_for_test(now_ms=3_100)

        assert transform_backend.calls == []
        assert keystroke.paste_count == 1
        assert keystroke.typed_texts == []
        assert ("show_say_again",) not in overlay.calls
        assert sm.state is State.IDLE


class TestNoConfirmPass:
    @pytest.mark.parametrize(
        "heard",
        [
            pytest.param("hello there, how are you", id="dictation"),
            pytest.param("paste", id="exact-builtin"),
            pytest.param("Summarise.", id="exact-transform"),
            pytest.param(Transcript("haste", confidence=CONFIDENT), id="strong-confident"),
        ],
    )
    def test_regular_dictation_and_sure_matches_never_confirm(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        heard: Transcript | str,
    ) -> None:
        _dictate_hello(core, keystroke)
        backend._result = heard
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert backend.command_calls == []


class TestConfirmPassLogging:
    def test_outcome_logged_by_kind_and_action_never_the_text(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _dictate_hello(core, keystroke)
        backend._result = SOME_OF_US
        backend.command_result = Transcript("Summarise.", confidence=CONFIDENT)
        with caplog.at_level(logging.DEBUG, logger="dictatem"):
            _cycle(core, start_ms=2_000, end_ms=3_000)

        messages = [r.getMessage() for r in caplog.records]
        confirm = [m for m in messages if "confirm pass" in m]
        assert confirm == ["Trigger Word confirm pass: confirmed summarise"]
        for message in messages:
            assert "some of us" not in message.lower()
            assert "summarise." not in message.lower()
            assert "hello world" not in message.lower()

    def test_unconfirmed_outcome_is_logged_without_text(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _dictate_hello(core, keystroke)
        backend._result = SOME_OF_US
        backend.command_result = Transcript("some of them", confidence=CONFIDENT)
        with caplog.at_level(logging.DEBUG, logger="dictatem"):
            _cycle(core, start_ms=2_000, end_ms=3_000)

        messages = [r.getMessage() for r in caplog.records]
        assert [m for m in messages if "confirm pass" in m] == [
            "Trigger Word confirm pass: not confirmed; say again"
        ]
        assert not any("some of" in m.lower() for m in messages)