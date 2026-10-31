"""Borderline Trigger Word outcome — say-again flash, nothing pasted (#248).

An utterance that sounds *close to* a Trigger Word but isn't sure enough to
fire (a weak fuzzy match, an unconfident strong match, or a cross-action tie)
pastes and types nothing, flashes the distinct "say again" pill, and leaves the
Most-recent dictation and Last Paste untouched — so an exact "paste" afterwards
still recovers the original dictation (ADR-0023 / ADR-0028).
"""

from __future__ import annotations

import logging

import pytest

from dictatem.daemon import DaemonCore
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
REWRITE_PROMPT = "SYSTEM: rewrite this text."
REWROTE_PROMPT = "SYSTEM: a different action."
ALIASES = {
    "summarize": SUMMARIZE_PROMPT,
    "summarise": SUMMARIZE_PROMPT,
    "rewrite": REWRITE_PROMPT,
    "rewrote": REWROTE_PROMPT,
}

UNSURE = SegmentConfidence(avg_logprob=-1.8, no_speech_prob=0.05)

# (heard transcript, why it is Borderline)
BORDERLINE_CASES = [
    pytest.param(Transcript("haste", confidence=UNSURE), id="unconfident-strong"),
    pytest.param(Transcript("some of us"), id="weak"),
    pytest.param(Transcript("rewrute"), id="cross-action-tie"),
]


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
def transform_backend() -> FakeTransformBackend:
    return FakeTransformBackend()


@pytest.fixture
def sm() -> StateMachine:
    return StateMachine(tap_threshold_ms=200)


@pytest.fixture
def core(
    sm: StateMachine,
    backend: FakeTranscriberBackend,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    overlay: FakeOverlayRenderer,
    transform_backend: FakeTransformBackend,
) -> DaemonCore:
    return DaemonCore(
        state_machine=sm,
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=overlay,
        tray=FakeTrayRenderer(),
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=FakeForegroundTracker(target_id=42),
        transform_lifecycle=TransformLifecycle(backend=transform_backend),
        trigger_recognizer=TriggerWordRecognizer(ALIASES),
        transform_enabled=True,
        last_paste_ttl_s=300.0,
    )


def _cycle(core: DaemonCore, *, start_ms: int, end_ms: int) -> None:
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=start_ms)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=start_ms + 200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=end_ms)
    core.drain_transcription_for_test(now_ms=end_ms)


def _set_texts(clipboard: FakeClipboardIO) -> list[str]:
    return [c[1] for c in clipboard.calls if c[0] == "set_text"]


@pytest.mark.parametrize("heard", BORDERLINE_CASES)
class TestBorderlinePastesNothing:
    def test_nothing_pasted_or_typed_and_say_again_flashes(
        self,
        core: DaemonCore,
        sm: StateMachine,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        transform_backend: FakeTransformBackend,
        heard: Transcript,
    ) -> None:
        _cycle(core, start_ms=0, end_ms=1_000)  # "hello world" → Last Paste
        assert keystroke.paste_count == 1

        backend._result = heard
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert _set_texts(clipboard) == ["hello world "]
        assert keystroke.paste_count == 1
        assert keystroke.typed_texts == []
        assert keystroke.total_backspaces == 0
        assert transform_backend.calls == []
        assert overlay.calls[-1] == ("show_say_again",)
        assert ("show_error",) not in overlay.calls
        assert sm.state is State.IDLE

    def test_buffers_untouched_and_exact_paste_recovers_the_original(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        heard: Transcript,
    ) -> None:
        _cycle(core, start_ms=0, end_ms=1_000)
        last_paste = core._last_paste
        assert last_paste is not None

        backend._result = heard
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert core._most_recent_dictation == "hello world "
        assert core._last_paste is last_paste

        # The next utterance is judged fresh: an exact "paste" re-pastes.
        backend._result = "paste"
        _cycle(core, start_ms=4_000, end_ms=5_000)
        assert _set_texts(clipboard) == ["hello world ", "hello world "]
        assert keystroke.paste_count == 2


class TestBorderlineLogging:
    def test_logs_kind_candidates_band_and_confidence_never_the_text(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = Transcript("haste", confidence=UNSURE)
        with caplog.at_level(logging.DEBUG, logger="dictatem"):
            _cycle(core, start_ms=2_000, end_ms=3_000)

        lines = [r.getMessage() for r in caplog.records if "Borderline" in r.getMessage()]
        assert len(lines) == 1
        line = lines[0]
        assert "paste" in line  # the candidate action name
        assert "strong" in line  # the score band
        assert "-1.80" in line and "0.05" in line  # the confidence
        for record in caplog.records:
            assert "haste" not in record.getMessage().lower()

    def test_tie_logs_every_candidate_action(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = "rewrute"
        with caplog.at_level(logging.INFO, logger="dictatem"):
            _cycle(core, start_ms=2_000, end_ms=3_000)

        line = next(r.getMessage() for r in caplog.records if "Borderline" in r.getMessage())
        assert "rewrite" in line and "rewrote" in line
        assert "confidence=unknown" in line
        assert "rewrute" not in line
