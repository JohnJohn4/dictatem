"""Privacy guarantee: dictated text never reaches the logs (S-2 / #188).

Dictatem's core claim is that nothing leaves the machine. The daemon log is
retained on disk (~7 days via the rotating handler), so dictated/transcribed
text must never be written to it — only character counts. These tests drive a
real dictation (and a Trigger Fire) through the fakes with a distinctive secret
phrase and assert it appears in **no** captured log record at any level.
"""

from __future__ import annotations

import logging

import pytest

from dictatem.daemon import DaemonCore
from dictatem.state import Event, StateMachine
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

SECRET = "my bank password is hunter2 and my address is 42 Wallaby Way Sydney"
SUMMARIZE_PROMPT = "SYSTEM: summarize this text."
ALIASES = {"summarize": SUMMARIZE_PROMPT}


@pytest.fixture
def backend() -> FakeTranscriberBackend:
    return FakeTranscriberBackend(result=SECRET)


@pytest.fixture
def transform_backend() -> FakeTransformBackend:
    return FakeTransformBackend()


@pytest.fixture
def core(
    backend: FakeTranscriberBackend, transform_backend: FakeTransformBackend
) -> DaemonCore:
    return DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=FakeOverlayRenderer(),
        tray=FakeTrayRenderer(),
        clipboard=FakeClipboardIO(),
        keystroke=FakeKeystrokeSender(),
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


# Format each record exactly as the file handler would — including any
# exception traceback attached via ``exc_info`` — so a leak through
# ``logger.error(..., exc_info=exc)`` (the daemon has such paths) is caught too,
# not just leaks in the static message string.
_FORMATTER = logging.Formatter()


def _assert_secret_absent(caplog: pytest.LogCaptureFixture) -> None:
    for record in caplog.records:
        rendered = _FORMATTER.format(record)
        assert SECRET not in rendered, (
            f"dictated text leaked into a {record.levelname} log: {rendered!r}"
        )


def test_regular_dictation_text_not_logged(
    core: DaemonCore, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="dictatem"):
        _cycle(core, start_ms=0, end_ms=1_000)
    # The completion line still reports the count.
    assert any("Transcription complete" in r.getMessage() for r in caplog.records)
    _assert_secret_absent(caplog)


def test_trigger_fire_operand_not_logged(
    core: DaemonCore,
    backend: FakeTranscriberBackend,
    transform_backend: FakeTransformBackend,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="dictatem"):
        # Regular dictation seeds the Last Paste with the secret...
        _cycle(core, start_ms=0, end_ms=1_000)
        # ...then a Trigger Fire runs a Transform over that secret operand.
        backend._result = "summarize"
        transform_backend.queue_result("CONDENSED")
        _cycle(core, start_ms=2_000, end_ms=3_000)
    _assert_secret_absent(caplog)


def test_fuzzy_fires_do_not_log_the_heard_text(
    core: DaemonCore,
    backend: FakeTranscriberBackend,
    transform_backend: FakeTransformBackend,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # #247: a fuzzy match neither logs the secret operand nor what was heard.
    with caplog.at_level(logging.DEBUG, logger="dictatem"):
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = "Summerize."
        transform_backend.queue_result("CONDENSED")
        _cycle(core, start_ms=2_000, end_ms=3_000)
        backend._result = "Haste."
        _cycle(core, start_ms=4_000, end_ms=5_000)
    assert transform_backend.calls  # the fuzzy Trigger Fire did run
    _assert_secret_absent(caplog)
    for record in caplog.records:
        rendered = _FORMATTER.format(record).lower()
        assert "summerize" not in rendered
        assert "haste" not in rendered


def test_short_utterance_diagnostics_logged_without_text(
    core: DaemonCore,
    backend: FakeTranscriberBackend,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A 1.0 s recording whose post-VAD speech is 0.6 s, with known confidence:
    # the §6.3 diagnostics line records both durations and the confidence.
    backend._result = Transcript(
        SECRET,
        confidence=SegmentConfidence(avg_logprob=-0.42, no_speech_prob=0.17),
        speech_duration_s=0.6,
    )
    with caplog.at_level(logging.DEBUG, logger="dictatem"):
        _cycle(core, start_ms=0, end_ms=1_000)
    lines = [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.DEBUG and "Short utterance" in r.getMessage()
    ]
    assert len(lines) == 1
    line = lines[0]
    assert "recording=1.00s" in line
    assert "speech=0.60s" in line
    assert "avg_logprob=-0.42" in line
    assert "no_speech_prob=0.17" in line
    _assert_secret_absent(caplog)


def test_short_utterance_diagnostics_with_unknown_confidence(
    core: DaemonCore, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="dictatem"):
        _cycle(core, start_ms=0, end_ms=1_000)
    lines = [r.getMessage() for r in caplog.records if "Short utterance" in r.getMessage()]
    assert len(lines) == 1
    assert "speech=unknown" in lines[0]
    assert "confidence=unknown" in lines[0]
    _assert_secret_absent(caplog)


def test_long_utterance_has_no_short_diagnostics(
    backend: FakeTranscriberBackend,
    transform_backend: FakeTransformBackend,
    caplog: pytest.LogCaptureFixture,
) -> None:
    core = DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=6.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=FakeOverlayRenderer(),
        tray=FakeTrayRenderer(),
        clipboard=FakeClipboardIO(),
        keystroke=FakeKeystrokeSender(),
        foreground=FakeForegroundTracker(target_id=42),
        transform_lifecycle=TransformLifecycle(backend=transform_backend),
        trigger_recognizer=TriggerWordRecognizer(ALIASES),
        transform_enabled=True,
    )
    with caplog.at_level(logging.DEBUG, logger="dictatem"):
        _cycle(core, start_ms=0, end_ms=6_000)
    assert not any("Short utterance" in r.getMessage() for r in caplog.records)