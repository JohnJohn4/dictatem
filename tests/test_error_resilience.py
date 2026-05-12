"""Integration tests for error resilience (Slice 9).

Each test wires the state machine to all fakes through DaemonCore and
verifies error paths produce the correct tray notifications, overlay
transitions, logging, and recovery.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from dictatem.audio.buffer import AudioBuffer
from dictatem.daemon import DaemonCore
from dictatem.exceptions import (
    AudioCaptureError,
    GPUOutOfMemoryError,
    ModelLoadError,
)
from dictatem.state import Event, State, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.types import EmptyResult
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
def sm() -> StateMachine:
    return StateMachine(tap_threshold_ms=200)


@pytest.fixture
def backend() -> FakeTranscriberBackend:
    return FakeTranscriberBackend(result="hello world")


@pytest.fixture
def audio() -> FakeAudioCapture:
    return FakeAudioCapture(duration_s=1.0)


@pytest.fixture
def overlay() -> FakeOverlayRenderer:
    return FakeOverlayRenderer()


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
def foreground() -> FakeForegroundTracker:
    return FakeForegroundTracker()


@pytest.fixture
def lifecycle(backend: FakeTranscriberBackend) -> TranscribeLifecycle:
    return TranscribeLifecycle(backend=backend, clock=lambda: 0.0)


@pytest.fixture
def core(
    sm: StateMachine,
    audio: FakeAudioCapture,
    lifecycle: TranscribeLifecycle,
    overlay: FakeOverlayRenderer,
    tray: FakeTrayRenderer,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    foreground: FakeForegroundTracker,
) -> DaemonCore:
    return DaemonCore(
        state_machine=sm,
        audio_capture=audio,
        lifecycle=lifecycle,
        overlay=overlay,
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=foreground,
    )


def _do_ptt_cycle(core: DaemonCore) -> None:
    """Drive a PTT cycle: key down → timer → key up → drain transcription."""
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=1500)
    core.drain_transcription_for_test(now_ms=1500)


class TestEmptyResultSuppression:
    """AC: EmptyResult → flash_error on overlay, no paste."""

    def test_empty_result_fires_flash_error_not_paste(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        overlay: FakeOverlayRenderer,
        keystroke: FakeKeystrokeSender,
        sm: StateMachine,
    ) -> None:
        backend._result = EmptyResult()
        _do_ptt_cycle(core)

        assert any(c[0] == "show_error" for c in overlay.calls)
        assert keystroke.paste_count == 0
        assert sm.state is State.IDLE


class TestGPUOOMDoubleFail:
    """AC: Double OOM → daemon catches TranscriptionFailedError, tray notify, ERROR log, continue."""

    def test_double_oom_notifies_and_logs(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
        sm: StateMachine,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        backend.queue_error(GPUOutOfMemoryError("first"))
        backend.queue_error(GPUOutOfMemoryError("second"))

        with caplog.at_level(logging.ERROR, logger="dictatem.daemon"):
            _do_ptt_cycle(core)

        assert len(tray.notifications) >= 1
        assert any("GPU" in msg or "memory" in msg for _, msg in tray.notifications)
        assert any("GPU" in r.message or "memory" in r.message for r in caplog.records)
        assert any(r.levelno == logging.ERROR for r in caplog.records)
        assert sm.state is State.IDLE

    def test_daemon_continues_after_double_oom(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
        keystroke: FakeKeystrokeSender,
        sm: StateMachine,
    ) -> None:
        backend.queue_error(GPUOutOfMemoryError("first"))
        backend.queue_error(GPUOutOfMemoryError("second"))
        _do_ptt_cycle(core)
        assert sm.state is State.IDLE

        backend._result = "recovered text"
        _do_ptt_cycle(core)
        assert sm.state is State.IDLE
        assert keystroke.paste_count == 1


class TestSilenceTimeout:
    """AC: is_idle_for_seconds(60) True while PTT_REC → IDLE + cancel, INFO log."""

    def test_silence_timeout_cancels_recording(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        buf = AudioBuffer(sample_rate=16_000, silence_floor=0.01)
        buf.append(np.zeros(16_000 * 61, dtype=np.float32))

        core = DaemonCore(
            state_machine=sm,
            audio_capture=audio,
            audio_buffer=buf,
            lifecycle=lifecycle,
            overlay=overlay,
            tray=tray,
            clipboard=clipboard,
            keystroke=keystroke,
            foreground=foreground,
        )

        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        with caplog.at_level(logging.INFO, logger="dictatem.daemon"):
            core.check_silence(now_ms=60_200)

        assert sm.state is State.IDLE
        assert any(r.levelno == logging.INFO for r in caplog.records)
        assert any("timeout" in r.message.lower() or "idle" in r.message.lower() for r in caplog.records)


class TestMaxRecordingDuration:
    """AC: duration >= max_recording_seconds → IDLE + tray notify, INFO log."""

    def test_max_duration_cancels_recording(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        buf = AudioBuffer(sample_rate=16_000)
        # 10 seconds of audio; cap set to 5 seconds
        buf.append(np.zeros(16_000 * 10, dtype=np.float32))

        core = DaemonCore(
            state_machine=sm,
            audio_capture=audio,
            audio_buffer=buf,
            lifecycle=lifecycle,
            overlay=overlay,
            tray=tray,
            clipboard=clipboard,
            keystroke=keystroke,
            foreground=foreground,
            max_recording_s=5.0,
        )

        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        with caplog.at_level(logging.INFO, logger="dictatem.daemon"):
            core.check_silence(now_ms=10_200)

        assert sm.state is State.IDLE
        assert any("max" in r.message.lower() or "duration" in r.message.lower() for r in caplog.records)
        assert any("max duration" in msg.lower() for _, msg in tray.notifications)

    def test_max_duration_not_triggered_below_cap(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
    ) -> None:
        buf = AudioBuffer(sample_rate=16_000)
        # 3 seconds of audio; cap is 5 seconds — should not trigger
        buf.append(np.ones(16_000 * 3, dtype=np.float32))

        core = DaemonCore(
            state_machine=sm,
            audio_capture=audio,
            audio_buffer=buf,
            lifecycle=lifecycle,
            overlay=overlay,
            tray=tray,
            clipboard=clipboard,
            keystroke=keystroke,
            foreground=foreground,
            max_recording_s=5.0,
        )

        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        core.check_silence(now_ms=3_200)

        assert sm.state is State.PTT_REC  # still recording


class TestAudioCaptureError:
    """AC: AudioCaptureError → tray notify with documented text, WARNING log, subsequent hotkeys work."""

    def test_audio_capture_error_notifies_and_logs(
        self,
        core: DaemonCore,
        audio: FakeAudioCapture,
        tray: FakeTrayRenderer,
        sm: StateMachine,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        audio.queue_start_error(AudioCaptureError("mic gone"))

        with caplog.at_level(logging.WARNING, logger="dictatem.daemon"):
            core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)

        assert len(tray.notifications) >= 1
        assert any("Microphone" in msg or "mic" in msg.lower() for _, msg in tray.notifications)
        assert any(r.levelno == logging.WARNING for r in caplog.records)
        assert sm.state is State.IDLE

    def test_subsequent_hotkey_works_after_audio_error(
        self,
        core: DaemonCore,
        audio: FakeAudioCapture,
        keystroke: FakeKeystrokeSender,
        sm: StateMachine,
    ) -> None:
        audio.queue_start_error(AudioCaptureError("mic gone"))
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        assert sm.state is State.IDLE

        _do_ptt_cycle(core)
        assert sm.state is State.IDLE
        assert keystroke.paste_count == 1


class TestModelLoadError:
    """AC: ModelLoadError → tray notify, ERROR log with traceback, daemon survives, retries."""

    def test_model_load_error_notifies_and_logs(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
        sm: StateMachine,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        backend.queue_load_error(ModelLoadError("CUDA missing"))

        with caplog.at_level(logging.ERROR, logger="dictatem.daemon"):
            _do_ptt_cycle(core)

        assert len(tray.notifications) >= 1
        assert any("Model" in title or "model" in msg.lower() for title, msg in tray.notifications)
        assert any(r.levelno == logging.ERROR for r in caplog.records)
        assert any(r.exc_info is not None and r.exc_info[0] is not None for r in caplog.records)
        assert sm.state is State.IDLE

    def test_retries_load_on_next_transcription(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        keystroke: FakeKeystrokeSender,
        sm: StateMachine,
    ) -> None:
        backend.queue_load_error(ModelLoadError("CUDA missing"))
        _do_ptt_cycle(core)
        assert sm.state is State.IDLE

        _do_ptt_cycle(core)
        assert sm.state is State.IDLE
        assert keystroke.paste_count == 1
        assert backend.load_count == 2


class TestTopLevelErrorHandlers:
    """AC: All daemon entry points have try/except top-level handlers."""

    def test_unexpected_error_in_transcription_does_not_crash(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
        sm: StateMachine,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        backend.queue_error(RuntimeError("unexpected kaboom"))

        with caplog.at_level(logging.ERROR, logger="dictatem.daemon"):
            _do_ptt_cycle(core)

        assert sm.state is State.IDLE
        assert len(tray.notifications) >= 1

    def test_unexpected_error_in_silence_check_does_not_crash(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        class BrokenBuffer:
            def is_idle_for_seconds(self, _: float) -> bool:
                raise RuntimeError("buffer exploded")

        core = DaemonCore(
            state_machine=sm,
            audio_capture=audio,
            audio_buffer=BrokenBuffer(),  # type: ignore[arg-type]
            lifecycle=lifecycle,
            overlay=overlay,
            tray=tray,
            clipboard=clipboard,
            keystroke=keystroke,
            foreground=foreground,
        )

        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=200)
        assert sm.state is State.PTT_REC

        with caplog.at_level(logging.ERROR, logger="dictatem.daemon"):
            core.check_silence(now_ms=60_200)

        assert any(r.levelno == logging.ERROR for r in caplog.records)
