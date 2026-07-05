"""Tests verifying that every fake satisfies its Protocol contract."""

from __future__ import annotations

import numpy as np
import pytest

from dictatem.hotkey.classifier import Key, KeyAction
from dictatem.interfaces import (
    AudioCapture,
    AutostartRegistrar,
    ClipboardIO,
    DaemonStopper,
    ForegroundTracker,
    KeyboardHook,
    KeystrokeSender,
    OverlayRenderer,
    TranscriberBackend,
    TrayRenderer,
)
from dictatem.types import EmptyResult, RecordingMode
from tests.fakes import (
    FakeAudioCapture,
    FakeAutostartRegistrar,
    FakeClipboardIO,
    FakeDaemonStopper,
    FakeForegroundTracker,
    FakeKeyboardHook,
    FakeKeystrokeSender,
    FakeOverlayRenderer,
    FakeTranscriberBackend,
    FakeTrayRenderer,
)


class TestFakeClipboardIO:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeClipboardIO(), ClipboardIO)

    def test_save_restore_roundtrip(self) -> None:
        clip = FakeClipboardIO()
        clip.set_text("hello")
        saved = clip.save()
        clip.set_text("overwritten")
        clip.restore(saved)
        assert clip.save() == "hello"

    def test_records_calls(self) -> None:
        clip = FakeClipboardIO()
        clip.save()
        clip.set_text("x")
        assert len(clip.calls) == 2


class TestFakeKeystrokeSender:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeKeystrokeSender(), KeystrokeSender)

    def test_counts_pastes(self) -> None:
        ks = FakeKeystrokeSender()
        ks.send_paste()
        ks.send_paste()
        assert ks.paste_count == 2

    def test_captures_typed_text(self) -> None:
        ks = FakeKeystrokeSender()
        ks.send_text("hello ")
        ks.send_text("world")
        assert ks.typed_texts == ["hello ", "world"]


class TestFakeForegroundTracker:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeForegroundTracker(), ForegroundTracker)

    def test_capture_returns_target_id(self) -> None:
        ft = FakeForegroundTracker(target_id=42)
        assert ft.capture() == 42

    def test_records_restores(self) -> None:
        ft = FakeForegroundTracker()
        ft.restore(99)
        assert ft.restored == [99]


class TestFakeKeyboardHook:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeKeyboardHook(lambda key, action, ts: None), KeyboardHook)

    def test_install_uninstall(self) -> None:
        hook = FakeKeyboardHook(lambda key, action, ts: None)
        hook.install()
        assert hook.installed is True
        hook.uninstall()
        assert hook.installed is False

    def test_simulate_event_delivers_to_constructor_handler(self) -> None:
        events: list[tuple[Key, KeyAction, int]] = []
        hook = FakeKeyboardHook(lambda key, action, ts: events.append((key, action, ts)))
        # Nothing is delivered before install — a real OS hook isn't live yet.
        hook.simulate_event(Key.LEFT_META, KeyAction.KEY_DOWN, 100)
        assert events == []
        hook.install()
        hook.simulate_event(Key.LEFT_META, KeyAction.KEY_DOWN, 100)
        assert events == [(Key.LEFT_META, KeyAction.KEY_DOWN, 100)]


class TestFakeAudioCapture:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeAudioCapture(), AudioCapture)

    def test_start_stop_returns_audio(self) -> None:
        ac = FakeAudioCapture(duration_s=0.5)
        ac.start()
        chunk = ac.stop()
        assert chunk.dtype == np.float32
        assert len(chunk) == 8000  # 0.5s * 16000

    def test_close_is_tracked_and_idempotent(self) -> None:
        ac = FakeAudioCapture()
        assert ac.closed is False
        ac.close()
        ac.close()
        assert ac.closed is True
        assert ac.close_count == 2


class TestFakeTranscriberBackend:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeTranscriberBackend(), TranscriberBackend)

    def test_lifecycle(self) -> None:
        tb = FakeTranscriberBackend(result="hello world")
        assert tb.is_loaded is False
        tb.load_model()
        assert tb.is_loaded is True
        audio = np.zeros(16000, dtype=np.float32)
        result = tb.transcribe(audio)
        assert result == "hello world"
        tb.unload_model()
        assert tb.is_loaded is False

    def test_transcribe_when_unloaded_returns_empty(self) -> None:
        tb = FakeTranscriberBackend()
        audio = np.zeros(16000, dtype=np.float32)
        assert tb.transcribe(audio) == EmptyResult()

    def test_empty_cache_tracks_calls(self) -> None:
        tb = FakeTranscriberBackend()
        tb.empty_cache()
        tb.empty_cache()
        assert tb.empty_cache_count == 2

    def test_progress_callback(self) -> None:
        tb = FakeTranscriberBackend()
        events: list[tuple[int, int]] = []
        tb.set_progress_callback(lambda d, t: events.append((d, t)))
        tb.simulate_progress(50, 100)
        assert events == [(50, 100)]

    def test_queued_error_raised_on_transcribe(self) -> None:
        from dictatem.exceptions import GPUOutOfMemoryError

        tb = FakeTranscriberBackend()
        tb.load_model()
        audio = np.zeros(16000, dtype=np.float32)
        tb.queue_error(GPUOutOfMemoryError("test"))
        with pytest.raises(GPUOutOfMemoryError):
            tb.transcribe(audio)


class TestFakeAutostartRegistrar:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeAutostartRegistrar(), AutostartRegistrar)

    def test_enable_disable_toggles_state(self) -> None:
        reg = FakeAutostartRegistrar(enabled=False)
        assert reg.is_enabled() is False
        reg.enable()
        assert reg.is_enabled() is True
        reg.disable()
        assert reg.is_enabled() is False

    def test_records_call_counts(self) -> None:
        reg = FakeAutostartRegistrar()
        reg.enable()
        reg.disable()
        reg.disable()
        assert reg.enable_calls == 1
        assert reg.disable_calls == 2


class TestFakeDaemonStopper:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeDaemonStopper(), DaemonStopper)

    def test_returns_configured_stopped_pids(self) -> None:
        stopper = FakeDaemonStopper(stopped=[101, 202])
        assert stopper.stop_running_daemons() == [101, 202]

    def test_records_call_count(self) -> None:
        stopper = FakeDaemonStopper()
        stopper.stop_running_daemons()
        stopper.stop_running_daemons()
        assert stopper.call_count == 2


class TestFakeOverlayRenderer:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeOverlayRenderer(), OverlayRenderer)

    def test_show_hide_cycle(self) -> None:
        ov = FakeOverlayRenderer()
        ov.show(RecordingMode.PTT)
        assert ov.visible is True
        assert ov.state == "recording"
        ov.show_transcribing()
        assert ov.state == "transcribing"
        ov.hide()
        assert ov.visible is False
        assert ov.state == "hidden"

    def test_records_calls(self) -> None:
        ov = FakeOverlayRenderer()
        ov.show(RecordingMode.TOGGLE)
        ov.update_level(0.5)
        ov.show_error()
        assert len(ov.calls) == 3


class TestFakeTrayRenderer:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeTrayRenderer(), TrayRenderer)

    def test_state_transitions(self) -> None:
        tray = FakeTrayRenderer()
        assert tray.state == "idle"
        tray.set_recording()
        assert tray.state == "recording"
        tray.set_error()
        assert tray.state == "error"
        tray.set_idle()
        assert tray.state == "idle"

    def test_notifications(self) -> None:
        tray = FakeTrayRenderer()
        tray.show_notification("Test", "Hello")
        assert tray.notifications == [("Test", "Hello")]
