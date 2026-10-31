"""A cancelled dictation's late result can never land (review F-6 / #235).

Every transcription and Transform worker result is tagged with the Dictation
Session epoch it was started under. Esc leaves the worker running to completion
in the background (ADR-0016), so its result still arrives — possibly after the
user has already started (and stopped) the next dictation. The daemon must drop
such a stale result with no side effects: no paste, no notification, no
state-machine event, no latency-tip sample.

The scenarios park the fake backend mid-flight, cancel, start the next
dictation, then let the stale worker finish *before* the fresh one, so the
stale result sits at the head of the queue when the daemon drains it.
"""

from __future__ import annotations

import logging

import pytest

from dictatem.daemon import DaemonCore
from dictatem.state import Event, State, StateMachine
from dictatem.transcribe.latency_monitor import LatencyMonitor
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.transform.detector import TriggerDetector
from dictatem.transform.lifecycle import TransformLifecycle
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
from tests.support import wait_until

SUMMARIZE_PROMPT = "SYSTEM: summarize this text."
ALIASES = {"summarize": SUMMARIZE_PROMPT}
SECRET = "stale secret: my pin is 8472 and I live at 9 Elm Street"


class _Clock:
    """A settable monotonic clock for the LatencyMonitor."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def sm() -> StateMachine:
    return StateMachine(tap_threshold_ms=200)


@pytest.fixture
def backend() -> FakeTranscriberBackend:
    b = FakeTranscriberBackend(result="unused")
    b._loaded = True  # warm model: keep the load path out of these scenarios
    return b


@pytest.fixture
def transform_backend() -> FakeTransformBackend:
    return FakeTransformBackend()


@pytest.fixture
def tray() -> FakeTrayRenderer:
    return FakeTrayRenderer()


@pytest.fixture
def clipboard() -> FakeClipboardIO:
    return FakeClipboardIO()


@pytest.fixture
def keystroke() -> FakeKeystrokeSender:
    return FakeKeystrokeSender()


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def core(
    sm: StateMachine,
    backend: FakeTranscriberBackend,
    transform_backend: FakeTransformBackend,
    tray: FakeTrayRenderer,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    clock: _Clock,
) -> DaemonCore:
    return DaemonCore(
        state_machine=sm,
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=FakeOverlayRenderer(),
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=FakeForegroundTracker(target_id=42),
        transform_lifecycle=TransformLifecycle(backend=transform_backend),
        trigger_detector=TriggerDetector(ALIASES),
        transform_enabled=True,
        last_paste_ttl_s=300.0,
        latency_monitor=LatencyMonitor(clock=clock, rtf_threshold=1.5, window=3),
    )


def _start(core: DaemonCore, at: int) -> None:
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=at)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=at + 200)


def _stop(core: DaemonCore, at: int) -> None:
    core.on_hotkey_event(Event.KEY_UP, now_ms=at)


def _join_transcription(core: DaemonCore) -> None:
    assert core._transcription_thread is not None
    core._transcription_thread.join(timeout=5.0)
    assert not core._transcription_thread.is_alive()


def _join_transform(core: DaemonCore) -> None:
    assert core._transform_thread is not None
    core._transform_thread.join(timeout=5.0)
    assert not core._transform_thread.is_alive()


def _tick(core: DaemonCore, at: int, times: int = 4) -> None:
    """Run a few production-style ticks (each drains one queue item)."""
    for _ in range(times):
        core.check_transcription_result(now_ms=at)
        core.check_transform_result(now_ms=at)


def _set_texts(clipboard: FakeClipboardIO) -> list[str]:
    # The paste pipeline normalizes (e.g. appends a trailing space); compare
    # the dictated words only.
    return [c[1].strip() for c in clipboard.calls if c[0] == "set_text"]


def _cancelled_then_fresh(
    core: DaemonCore,
    backend: FakeTranscriberBackend,
    *,
    stale_outcome: object,
    fresh_text: str = "fresh text",
) -> None:
    """Dictation A is cancelled mid-transcription; dictation B follows.

    A's worker finishes (with *stale_outcome*: a text result or an exception)
    after B has stopped recording but before B's worker, so A's late result is
    the first thing the daemon drains.
    """
    backend.block_transcribe()
    _start(core, 0)
    _stop(core, 1_000)  # worker A parked inside transcribe()
    stale_worker = core._transcription_thread
    core.on_hotkey_event(Event.ESC, now_ms=1_100)

    _start(core, 2_000)  # dictation B recording
    if isinstance(stale_outcome, Exception):
        backend.queue_error(stale_outcome)
    else:
        backend._result = stale_outcome  # type: ignore[assignment]
    backend.release_transcribe()
    assert stale_worker is not None
    stale_worker.join(timeout=5.0)
    # Esc posture (ADR-0016): the cancelled work ran to completion.
    assert not stale_worker.is_alive()

    backend._result = fresh_text
    _stop(core, 3_000)  # worker B
    _join_transcription(core)


class TestStaleTranscription:
    def test_stale_ok_result_never_pastes_and_fresh_one_does(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        sm: StateMachine,
    ) -> None:
        _cancelled_then_fresh(core, backend, stale_outcome="stale text")
        _tick(core, 3_000)

        assert _set_texts(clipboard) == ["fresh text"]
        assert keystroke.paste_count == 1
        assert sm.state is State.IDLE
        # Both workers really ran (cancelled work is not killed, ADR-0016).
        assert len(backend.transcribe_calls) == 2

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(RuntimeError("kaboom"), id="unexpected_error"),
        ],
    )
    def test_stale_failure_raises_no_notification(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        tray: FakeTrayRenderer,
        sm: StateMachine,
        error: Exception,
    ) -> None:
        _cancelled_then_fresh(core, backend, stale_outcome=error)
        _tick(core, 3_000)

        assert tray.notifications == []
        # The stale failure did not recover-to-idle over B: B still pasted.
        assert _set_texts(clipboard) == ["fresh text"]
        assert sm.state is State.IDLE

    def test_stale_gpu_failure_raises_no_notification(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        tray: FakeTrayRenderer,
    ) -> None:
        from dictatem.exceptions import GPUOutOfMemoryError

        # Two OOMs → the lifecycle raises TranscriptionFailedError.
        backend.block_transcribe()
        _start(core, 0)
        _stop(core, 1_000)
        stale_worker = core._transcription_thread
        core.on_hotkey_event(Event.ESC, now_ms=1_100)
        _start(core, 2_000)
        backend.queue_error(GPUOutOfMemoryError("first"))
        backend.queue_error(GPUOutOfMemoryError("second"))
        backend.release_transcribe()
        assert stale_worker is not None
        stale_worker.join(timeout=5.0)
        backend._result = "fresh text"
        _stop(core, 3_000)
        _join_transcription(core)
        _tick(core, 3_000)

        assert tray.notifications == []
        assert _set_texts(clipboard) == ["fresh text"]


class TestStaleTransform:
    def _prime_last_paste(
        self, core: DaemonCore, backend: FakeTranscriberBackend
    ) -> None:
        backend._result = "the verbose text"
        _start(core, 0)
        _stop(core, 1_000)
        core.drain_transcription_for_test(now_ms=1_000)

    def _cancel_trigger_fire_mid_transform(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        transform_backend.block_transform()
        backend._result = "summarize"
        _start(core, 2_000)
        _stop(core, 3_000)
        _join_transcription(core)
        core.check_transcription_result(now_ms=3_000)  # starts the Transform
        assert len(transform_backend.calls) == 1
        core.on_hotkey_event(Event.ESC, now_ms=3_100)

    def test_stale_transform_types_nothing_after_next_trigger_fire(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        sm: StateMachine,
    ) -> None:
        self._prime_last_paste(core, backend)
        self._cancel_trigger_fire_mid_transform(core, backend, transform_backend)
        stale_transform = core._transform_thread

        # A regular dictation re-arms a Last Paste...
        backend._result = "second paste"
        _start(core, 4_000)
        _stop(core, 5_000)
        _join_transcription(core)
        _tick(core, 5_000)
        assert _set_texts(clipboard) == ["the verbose text", "second paste"]

        # ...the stale Transform finishes late (its output is queued)...
        transform_backend.queue_result("STALE OUTPUT")
        transform_backend.release_transform()
        assert stale_transform is not None
        stale_transform.join(timeout=5.0)
        assert not stale_transform.is_alive()  # ran to completion (ADR-0016)

        # ...and a fresh Trigger Fire is mid-Transform when it is drained.
        transform_backend.block_transform()
        backend._result = "summarize"
        _start(core, 6_000)
        _stop(core, 7_000)
        _join_transcription(core)
        core.check_transcription_result(now_ms=7_000)  # starts Transform B
        typed_before = list(keystroke.typed_texts)
        core.check_transform_result(now_ms=7_000)  # drains the STALE result
        assert keystroke.typed_texts == typed_before
        assert keystroke.total_backspaces == 0
        assert sm.state is State.TRANSCRIBING  # B still awaited

        transform_backend.queue_result("FRESH OUTPUT")
        transform_backend.release_transform()
        _join_transform(core)
        _tick(core, 7_000)
        assert [t.strip() for t in keystroke.typed_texts] == ["FRESH OUTPUT"]
        # The normalizer appends a trailing space, so the Last Paste is 13 chars.
        assert keystroke.total_backspaces == len("second paste ")

    def test_stale_transform_after_regular_dictation_is_ignored(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        tray: FakeTrayRenderer,
    ) -> None:
        self._prime_last_paste(core, backend)
        self._cancel_trigger_fire_mid_transform(core, backend, transform_backend)
        stale_transform = core._transform_thread

        # Regular dictation B is transcribing when the stale Transform lands.
        backend.block_transcribe()
        backend._result = "regular text"
        _start(core, 4_000)
        _stop(core, 5_000)
        transform_backend.queue_error(RuntimeError("late failure"))
        transform_backend.release_transform()
        assert stale_transform is not None
        stale_transform.join(timeout=5.0)
        _tick(core, 5_000)
        assert tray.notifications == []

        backend.release_transcribe()
        _join_transcription(core)
        _tick(core, 5_000)
        assert _set_texts(clipboard) == ["the verbose text", "regular text"]
        assert keystroke.total_backspaces == 0
        assert keystroke.typed_texts == []


class TestStaleRunAndLatencyTip:
    def _slow_run(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clock: _Clock,
        at: int,
    ) -> None:
        """A live run whose transcription takes 2 s of clock for 1 s of audio."""
        calls = len(backend.transcribe_calls)
        backend.block_transcribe()
        clock.t = 0.0
        _start(core, at)
        _stop(core, at + 1_000)  # 1 s of audio
        wait_until(lambda: len(backend.transcribe_calls) == calls + 1)
        clock.t = 2.0  # RTF 2.0 >= threshold
        backend.release_transcribe()
        _join_transcription(core)
        _tick(core, at + 1_000)

    def _stale_slow_run(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clock: _Clock,
        at: int,
    ) -> None:
        calls = len(backend.transcribe_calls)
        backend.block_transcribe()
        clock.t = 0.0
        _start(core, at)
        _stop(core, at + 1_000)
        # Wait until the worker is inside transcribe() (past any timing start)
        # before advancing the clock, so the run really is "slow".
        wait_until(lambda: len(backend.transcribe_calls) == calls + 1)
        core.on_hotkey_event(Event.ESC, now_ms=at + 1_100)
        clock.t = 2.0
        backend.release_transcribe()
        _join_transcription(core)
        _tick(core, at + 1_100)

    def test_stale_run_never_triggers_or_skews_the_tip(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clock: _Clock,
        tray: FakeTrayRenderer,
    ) -> None:
        backend._result = "words"
        self._slow_run(core, backend, clock, 0)
        self._slow_run(core, backend, clock, 10_000)
        # A third slow run — but cancelled — must not fill the window.
        self._stale_slow_run(core, backend, clock, 20_000)
        assert tray.notifications == []
        # Positive control: a third *live* slow run does fire the one-shot tip.
        self._slow_run(core, backend, clock, 30_000)
        assert [t for t, m in tray.notifications if "slow" in m] == ["Dictatem"]


def test_dropped_result_log_names_kind_not_content(
    core: DaemonCore,
    backend: FakeTranscriberBackend,
    caplog: pytest.LogCaptureFixture,
) -> None:
    formatter = logging.Formatter()
    with caplog.at_level(logging.DEBUG, logger="dictatem"):
        _cancelled_then_fresh(core, backend, stale_outcome=SECRET)
        _tick(core, 3_000)
    dropped = [r for r in caplog.records if "stale" in r.getMessage().lower()]
    assert dropped, "expected a dropped-stale-result log line"
    assert any("ok" in r.getMessage() for r in dropped)
    for record in caplog.records:
        rendered = formatter.format(record)
        assert SECRET not in rendered, (
            f"dictated text leaked into a {record.levelname} log: {rendered!r}"
        )
