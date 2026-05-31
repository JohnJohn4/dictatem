"""Integration tests for DaemonCore wiring — overlay, tray state, and menu actions.

These tests verify that DaemonCore properly wires the state machine to
overlay display, tray icon state updates, and tray menu action handling.
"""

from __future__ import annotations

import pytest

from dictatem.daemon import DaemonCore
from dictatem.state import Event, State, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.types import EmptyResult, RecordingMode
from tests.fakes import (
    FakeAudioCapture,
    FakeAutostartRegistrar,
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
    """Drive a full PTT cycle: key down → timer → key up → drain transcription."""
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=1500)
    core.drain_transcription_for_test(now_ms=1500)


# ── Overlay recording display ────────────────────────────────────────


class TestOverlayRecordingDisplay:
    """Overlay must be shown during recording with correct mode."""

    def test_record_start_shows_overlay(
        self, core: DaemonCore, overlay: FakeOverlayRenderer
    ) -> None:
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        assert overlay.visible
        assert any(c[0] == "show" for c in overlay.calls)

    def test_ptt_recording_shows_ptt_mode(
        self, core: DaemonCore, overlay: FakeOverlayRenderer
    ) -> None:
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=200)
        assert overlay.mode is RecordingMode.PTT

    def test_toggle_recording_updates_to_toggle_mode(
        self, core: DaemonCore, overlay: FakeOverlayRenderer
    ) -> None:
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        core.on_hotkey_event(Event.KEY_UP, now_ms=100)
        assert overlay.mode is RecordingMode.TOGGLE

    def test_transcribing_shows_transcribing_overlay(
        self, core: DaemonCore, overlay: FakeOverlayRenderer
    ) -> None:
        _do_ptt_cycle(core)
        assert any(c[0] == "show_transcribing" for c in overlay.calls)

    def test_paste_hides_overlay(
        self, core: DaemonCore, overlay: FakeOverlayRenderer
    ) -> None:
        _do_ptt_cycle(core)
        assert overlay.state == "hidden"

    def test_cancel_hides_overlay(
        self, core: DaemonCore, overlay: FakeOverlayRenderer
    ) -> None:
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        core.on_hotkey_event(Event.ESC, now_ms=100)
        assert overlay.state == "hidden"


class TestModelLoadingOverlay:
    """First-tap cold load shows the "Model Loading" pill, then flips to the
    transcribing dot once the model is resident; a warm model skips it (#74)."""

    def test_cold_first_tap_shows_loading_then_transcribing(
        self, core: DaemonCore, overlay: FakeOverlayRenderer
    ) -> None:
        # backend starts unloaded, so the first transcription is a cold load.
        _do_ptt_cycle(core)
        names = [c[0] for c in overlay.calls]
        assert "show_loading" in names
        assert "show_transcribing" in names
        assert names.index("show_loading") < names.index("show_transcribing")
        loading = [c for c in overlay.calls if c[0] == "show_loading"]
        assert loading[0][1] == "Loading Dict. Model"

    def test_warm_model_skips_loading_pill(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        overlay: FakeOverlayRenderer,
    ) -> None:
        backend._loaded = True  # already resident → no cold load
        _do_ptt_cycle(core)
        names = [c[0] for c in overlay.calls]
        assert "show_loading" not in names
        assert "show_transcribing" in names


# ── Tray icon state updates ──────────────────────────────────────────


class TestTrayIconStateUpdates:
    """Tray icon must reflect daemon state: idle, recording, error."""

    def test_record_start_sets_tray_recording(
        self, core: DaemonCore, tray: FakeTrayRenderer
    ) -> None:
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        assert tray.state == "recording"

    def test_idle_after_paste_sets_tray_idle(
        self, core: DaemonCore, tray: FakeTrayRenderer
    ) -> None:
        _do_ptt_cycle(core)
        assert tray.state == "idle"

    def test_idle_after_cancel_sets_tray_idle(
        self, core: DaemonCore, tray: FakeTrayRenderer
    ) -> None:
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        core.on_hotkey_event(Event.ESC, now_ms=100)
        assert tray.state == "idle"

    def test_esc_stops_audio_capture_to_discard_buffered_audio(
        self, core: DaemonCore, audio: FakeAudioCapture
    ) -> None:
        """Cancelling must stop the mic stream; otherwise the buffered
        audio from the cancelled session bleeds into the next recording."""
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        assert audio.started
        core.on_hotkey_event(Event.ESC, now_ms=100)
        assert audio.stopped

    def test_idle_after_empty_result_sets_tray_idle(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
    ) -> None:
        backend._result = EmptyResult()
        _do_ptt_cycle(core)
        assert tray.state == "idle"


# ── Tray menu action handling ────────────────────────────────────────


class TestTrayMenuActions:
    """Tray menu items must trigger the correct daemon behaviour."""

    def test_preload_model_loads_backend(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
    ) -> None:
        core.on_tray_preload()
        assert backend.load_count >= 1

    def test_unload_model_unloads_backend(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
    ) -> None:
        backend._loaded = True
        core.on_tray_unload()
        assert not backend.is_loaded

    def test_preload_then_sync_marks_tray_model_loaded(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
    ) -> None:
        """After preload completes, the tray must know the model is loaded."""
        # FakeTranscriberBackend.load_model is synchronous, so preload's
        # background thread is effectively a no-op for ordering here.
        core.on_tray_preload()
        # on_tray_preload calls sync_model_loaded() at the end
        assert tray.model_loaded is True

    def test_unload_marks_tray_model_unloaded(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
    ) -> None:
        backend._loaded = True
        core.sync_model_loaded()
        assert tray.model_loaded is True
        core.on_tray_unload()
        assert tray.model_loaded is False

    def test_quit_unloads_loaded_model_before_calling_quit_callback(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
    ) -> None:
        backend._loaded = True
        call_order: list[str] = []

        def fake_quit() -> None:
            call_order.append("quit")

        original_unload = backend.unload_model

        def tracking_unload() -> None:
            call_order.append("unload")
            original_unload()

        backend.unload_model = tracking_unload  # type: ignore[method-assign]

        core.on_tray_quit(fake_quit)

        assert call_order == ["unload", "quit"]
        assert not backend.is_loaded

    def test_quit_when_model_not_loaded_still_calls_quit_callback(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
    ) -> None:
        assert not backend.is_loaded
        quit_called = False

        def fake_quit() -> None:
            nonlocal quit_called
            quit_called = True

        core.on_tray_quit(fake_quit)

        assert quit_called

    def test_sync_model_loaded_reflects_backend_state(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
    ) -> None:
        """Polling sync_model_loaded() must mirror backend.is_loaded."""
        assert tray.model_loaded is False
        backend._loaded = True
        core.sync_model_loaded()
        assert tray.model_loaded is True
        backend._loaded = False
        core.sync_model_loaded()
        assert tray.model_loaded is False

    def test_start_recording_begins_capture(
        self,
        core: DaemonCore,
        audio: FakeAudioCapture,
        sm: StateMachine,
        overlay: FakeOverlayRenderer,
    ) -> None:
        core.on_tray_start_recording()
        assert audio.started
        assert overlay.visible
        assert sm.state in (State.PRESSED, State.TOGGLE_REC)

    def test_stop_recording_transcribes(
        self,
        core: DaemonCore,
        audio: FakeAudioCapture,
        keystroke: FakeKeystrokeSender,
        sm: StateMachine,
    ) -> None:
        core.on_tray_start_recording()
        core.on_tray_stop_recording()
        core.drain_transcription_for_test(now_ms=0)
        assert sm.state is State.IDLE
        assert keystroke.paste_count == 1

    def test_stop_recording_is_noop_when_idle(
        self,
        core: DaemonCore,
        sm: StateMachine,
    ) -> None:
        core.on_tray_stop_recording()
        assert sm.state is State.IDLE


# ── "Start at login" tray toggle (#55 / ADR-0012) ────────────────────


class TestTrayAutostartToggle:
    """The tray toggle flips config.startup.autostart and applies it.

    The daemon owns autostart: flipping the toggle persists the flag (so it
    survives a restart) and reconciles the OS entry via the registrar in the
    same step, keeping the flag the single source of truth.
    """

    def _core_with_autostart(
        self,
        *,
        enabled: bool,
    ) -> tuple[DaemonCore, FakeAutostartRegistrar, list[bool]]:
        registrar = FakeAutostartRegistrar(enabled=enabled)
        persisted: list[bool] = []
        core = DaemonCore(
            state_machine=StateMachine(tap_threshold_ms=200),
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hi"), clock=lambda: 0.0
            ),
            overlay=FakeOverlayRenderer(),
            tray=FakeTrayRenderer(),
            autostart_registrar=registrar,
            persist_autostart=persisted.append,
        )
        return core, registrar, persisted

    def test_toggle_off_disables_and_persists(self) -> None:
        core, registrar, persisted = self._core_with_autostart(enabled=True)
        core.on_tray_set_autostart(False)
        assert registrar.is_enabled() is False
        assert registrar.disable_calls == 1
        assert persisted == [False]

    def test_toggle_on_enables_and_persists(self) -> None:
        core, registrar, persisted = self._core_with_autostart(enabled=False)
        core.on_tray_set_autostart(True)
        assert registrar.is_enabled() is True
        assert registrar.enable_calls == 1
        assert persisted == [True]

    def test_toggle_on_when_already_enabled_is_idempotent(self) -> None:
        core, registrar, persisted = self._core_with_autostart(enabled=True)
        core.on_tray_set_autostart(True)
        assert registrar.is_enabled() is True
        assert registrar.enable_calls == 0
        # Still persisted so the config flag matches the toggle.
        assert persisted == [True]

    def test_toggle_without_registrar_is_safe(self) -> None:
        # A DaemonCore built without an autostart registrar (e.g. older wiring)
        # must not crash when the toggle fires.
        core = DaemonCore(
            state_machine=StateMachine(tap_threshold_ms=200),
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hi"), clock=lambda: 0.0
            ),
            overlay=FakeOverlayRenderer(),
            tray=FakeTrayRenderer(),
        )
        core.on_tray_set_autostart(True)  # no raise
