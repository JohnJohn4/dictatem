"""Tests for _start_windows_daemon adapter classes and wiring logic.

These tests verify the adapter and bridge classes that _start_windows_daemon
uses to connect Qt widgets to DaemonCore's protocol contracts.
"""

from __future__ import annotations

import dictatem.hotkey.classifier as _clf
from dictatem.daemon import DaemonCore, _HotkeyBridge, _OverlayAdapter, _TrayAdapter
from dictatem.interfaces import OverlayRenderer, TrayRenderer
from dictatem.overlay.state import OverlayPhase, OverlayState
from dictatem.state import Event, State, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.tray.state import IconVariant, TrayState
from dictatem.types import RecordingMode
from tests.fakes import (
    FakeAudioCapture,
    FakeClipboardIO,
    FakeForegroundTracker,
    FakeKeystrokeSender,
    FakeOverlayRenderer,
    FakeTranscriberBackend,
    FakeTrayRenderer,
)


class _FakeWidget:
    def __init__(self) -> None:
        self.shown = False
        self.hidden = False

    def show_pill(self) -> None:
        self.shown = True
        self.hidden = False

    def hide_pill(self) -> None:
        self.hidden = True
        self.shown = False


class _FakeTrayIcon:
    def __init__(self) -> None:
        self.last_state: TrayState | None = None
        self.notifications: list[tuple[str, str]] = []
        self.on_start = None
        self.on_stop = None
        self.on_preload = None
        self.on_unload = None
        self.on_quit = None

    def update_state(self, state: TrayState) -> None:
        self.last_state = state

    def show_notification(self, title: str, message: str) -> None:
        self.notifications.append((title, message))


class _Clock:
    def __init__(self, t: float = 0.0) -> None:
        self._t = t

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt


# ── OverlayAdapter ──────────────────────────────────────────────────────


class TestOverlayAdapter:
    def test_show_delegates_to_state_and_widget(self) -> None:
        state = OverlayState(clock=_Clock())
        widget = _FakeWidget()
        adapter = _OverlayAdapter(state=state, widget=widget)

        adapter.show(RecordingMode.PTT)

        assert state.phase == OverlayPhase.FADING_IN
        assert widget.shown

    def test_show_transcribing_sets_phase(self) -> None:
        state = OverlayState(clock=_Clock())
        widget = _FakeWidget()
        adapter = _OverlayAdapter(state=state, widget=widget)

        adapter.show(RecordingMode.PTT)
        adapter.show_transcribing()

        assert state.phase == OverlayPhase.TRANSCRIBING

    def test_show_error_sets_error_flash(self) -> None:
        state = OverlayState(clock=_Clock())
        widget = _FakeWidget()
        adapter = _OverlayAdapter(state=state, widget=widget)

        adapter.show_error()

        assert state.phase == OverlayPhase.ERROR_FLASH

    def test_hide_sets_fading_out(self) -> None:
        state = OverlayState(clock=_Clock())
        widget = _FakeWidget()
        adapter = _OverlayAdapter(state=state, widget=widget)

        adapter.show(RecordingMode.TOGGLE)
        adapter.hide()

        assert state.phase == OverlayPhase.FADING_OUT

    def test_satisfies_overlay_renderer_protocol(self) -> None:
        state = OverlayState(clock=_Clock())
        widget = _FakeWidget()
        adapter = _OverlayAdapter(state=state, widget=widget)

        assert isinstance(adapter, OverlayRenderer)


# ── TrayAdapter ─────────────────────────────────────────────────────────


class TestTrayAdapter:
    def test_set_idle_updates_icon_to_idle(self) -> None:
        icon = _FakeTrayIcon()
        adapter = _TrayAdapter(icon=icon)

        adapter.set_idle()

        assert icon.last_state is not None
        assert icon.last_state.current_icon_variant() == IconVariant.Idle

    def test_set_recording_updates_icon_to_recording(self) -> None:
        icon = _FakeTrayIcon()
        adapter = _TrayAdapter(icon=icon)

        adapter.set_recording()

        assert icon.last_state is not None
        assert icon.last_state.current_icon_variant() == IconVariant.Recording

    def test_set_error_updates_icon_to_error(self) -> None:
        icon = _FakeTrayIcon()
        adapter = _TrayAdapter(icon=icon)

        adapter.set_error()

        assert icon.last_state is not None
        assert icon.last_state.current_icon_variant() == IconVariant.Error

    def test_set_idle_after_recording_resets(self) -> None:
        icon = _FakeTrayIcon()
        adapter = _TrayAdapter(icon=icon)

        adapter.set_recording()
        adapter.set_idle()

        assert icon.last_state is not None
        assert icon.last_state.current_icon_variant() == IconVariant.Idle

    def test_show_notification_delegates(self) -> None:
        icon = _FakeTrayIcon()
        adapter = _TrayAdapter(icon=icon)

        adapter.show_notification("Title", "Message")

        assert icon.notifications == [("Title", "Message")]

    def test_satisfies_tray_renderer_protocol(self) -> None:
        icon = _FakeTrayIcon()
        adapter = _TrayAdapter(icon=icon)

        assert isinstance(adapter, TrayRenderer)


# ── HotkeyBridge ────────────────────────────────────────────────────────


class _EventCollector:
    def __init__(self) -> None:
        self.events: list[tuple[Event, int]] = []

    def on_hotkey_event(self, event: Event, *, now_ms: int = 0) -> None:
        self.events.append((event, now_ms))


def _combo_down(bridge: _HotkeyBridge, ts: int = 0) -> None:
    bridge.on_key_event(_clf.VK_LCONTROL, _clf.KeyAction.KEY_DOWN, ts)
    bridge.on_key_event(_clf.VK_LWIN, _clf.KeyAction.KEY_DOWN, ts)


def _combo_up(bridge: _HotkeyBridge, ts: int = 0) -> None:
    bridge.on_key_event(_clf.VK_LWIN, _clf.KeyAction.KEY_UP, ts)
    bridge.on_key_event(_clf.VK_LCONTROL, _clf.KeyAction.KEY_UP, ts)


class TestHotkeyBridge:
    def test_tap_sends_key_down_then_key_up(self) -> None:
        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        collector = _EventCollector()
        bridge = _HotkeyBridge(classifier=classifier, callback=collector.on_hotkey_event)

        _combo_down(bridge, ts=0)
        _combo_up(bridge, ts=100)

        event_types = [e for e, _ in collector.events]
        assert Event.KEY_DOWN in event_types
        assert Event.KEY_UP in event_types

    def test_hold_sends_key_down_then_timer_expired(self) -> None:
        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        collector = _EventCollector()
        bridge = _HotkeyBridge(classifier=classifier, callback=collector.on_hotkey_event)

        _combo_down(bridge, ts=0)
        bridge.tick(200)

        event_types = [e for e, _ in collector.events]
        assert Event.KEY_DOWN in event_types
        assert Event.TIMER_EXPIRED in event_types

    def test_hold_end_sends_key_up(self) -> None:
        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        collector = _EventCollector()
        bridge = _HotkeyBridge(classifier=classifier, callback=collector.on_hotkey_event)

        _combo_down(bridge, ts=0)
        bridge.tick(200)
        _combo_up(bridge, ts=1000)

        event_types = [e for e, _ in collector.events]
        assert event_types == [Event.KEY_DOWN, Event.TIMER_EXPIRED, Event.KEY_UP]

    def test_esc_sends_esc_event(self) -> None:
        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        collector = _EventCollector()
        bridge = _HotkeyBridge(classifier=classifier, callback=collector.on_hotkey_event)

        classifier.set_active(True)
        bridge.on_key_event(_clf.VK_ESCAPE, _clf.KeyAction.KEY_DOWN, 0)

        event_types = [e for e, _ in collector.events]
        assert Event.ESC in event_types

    def test_tap_drives_full_state_machine_cycle(self) -> None:
        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        sm = StateMachine(tap_threshold_ms=200)
        daemon = DaemonCore(
            state_machine=sm,
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hello"),
                clock=lambda: 0.0,
            ),
            overlay=FakeOverlayRenderer(),
            tray=FakeTrayRenderer(),
            clipboard=FakeClipboardIO(),
            keystroke=FakeKeystrokeSender(),
            foreground=FakeForegroundTracker(),
        )
        bridge = _HotkeyBridge(classifier=classifier, callback=daemon.on_hotkey_event)

        _combo_down(bridge, ts=0)
        _combo_up(bridge, ts=100)

        assert sm.state == State.TOGGLE_REC

    def test_hold_drives_ptt_recording(self) -> None:
        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        sm = StateMachine(tap_threshold_ms=200)
        daemon = DaemonCore(
            state_machine=sm,
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hello"),
                clock=lambda: 0.0,
            ),
            overlay=FakeOverlayRenderer(),
            tray=FakeTrayRenderer(),
            clipboard=FakeClipboardIO(),
            keystroke=FakeKeystrokeSender(),
            foreground=FakeForegroundTracker(),
        )
        bridge = _HotkeyBridge(classifier=classifier, callback=daemon.on_hotkey_event)

        _combo_down(bridge, ts=0)
        bridge.tick(200)

        assert sm.state == State.PTT_REC

    def test_enqueue_then_tick_drives_state_machine(self) -> None:
        """The hook thread enqueues key events; tick (main thread) drains them."""
        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        sm = StateMachine(tap_threshold_ms=200)
        daemon = DaemonCore(
            state_machine=sm,
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hello"),
                clock=lambda: 0.0,
            ),
            overlay=FakeOverlayRenderer(),
            tray=FakeTrayRenderer(),
            clipboard=FakeClipboardIO(),
            keystroke=FakeKeystrokeSender(),
            foreground=FakeForegroundTracker(),
        )
        bridge = _HotkeyBridge(classifier=classifier, callback=daemon.on_hotkey_event)

        bridge.enqueue_key_event(_clf.VK_LCONTROL, _clf.KeyAction.KEY_DOWN, 0)
        bridge.enqueue_key_event(_clf.VK_LWIN, _clf.KeyAction.KEY_DOWN, 0)
        bridge.enqueue_key_event(_clf.VK_LWIN, _clf.KeyAction.KEY_UP, 100)

        assert sm.state == State.IDLE, "queue must not be drained until tick"
        bridge.tick(100)
        assert sm.state == State.TOGGLE_REC

    def test_hold_then_release_transcribes(self) -> None:
        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        sm = StateMachine(tap_threshold_ms=200)
        keystroke = FakeKeystrokeSender()
        daemon = DaemonCore(
            state_machine=sm,
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hello world"),
                clock=lambda: 0.0,
            ),
            overlay=FakeOverlayRenderer(),
            tray=FakeTrayRenderer(),
            clipboard=FakeClipboardIO(),
            keystroke=keystroke,
            foreground=FakeForegroundTracker(),
        )
        bridge = _HotkeyBridge(classifier=classifier, callback=daemon.on_hotkey_event)

        _combo_down(bridge, ts=0)
        bridge.tick(200)
        _combo_up(bridge, ts=1500)

        assert sm.state == State.IDLE
        assert keystroke.paste_count == 1


# ── Full adapter integration ────────────────────────────────────────────


class TestAdapterIntegration:
    def test_overlay_adapter_with_daemon_core(self) -> None:
        clock = _Clock()
        state = OverlayState(clock=clock)
        widget = _FakeWidget()
        overlay = _OverlayAdapter(state=state, widget=widget)

        sm = StateMachine(tap_threshold_ms=200)
        daemon = DaemonCore(
            state_machine=sm,
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hello"),
                clock=lambda: 0.0,
            ),
            overlay=overlay,
            tray=FakeTrayRenderer(),
        )

        daemon.on_hotkey_event(Event.KEY_DOWN, now_ms=0)

        assert widget.shown
        assert state.phase == OverlayPhase.FADING_IN

    def test_tray_adapter_with_daemon_core(self) -> None:
        icon = _FakeTrayIcon()
        tray = _TrayAdapter(icon=icon)

        sm = StateMachine(tap_threshold_ms=200)
        daemon = DaemonCore(
            state_machine=sm,
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hello"),
                clock=lambda: 0.0,
            ),
            overlay=FakeOverlayRenderer(),
            tray=tray,
        )

        daemon.on_hotkey_event(Event.KEY_DOWN, now_ms=0)

        assert icon.last_state is not None
        assert icon.last_state.current_icon_variant() == IconVariant.Recording

    def test_full_tap_cycle_with_adapters(self) -> None:
        clock = _Clock()
        overlay_state = OverlayState(clock=clock)
        widget = _FakeWidget()
        overlay = _OverlayAdapter(state=overlay_state, widget=widget)

        icon = _FakeTrayIcon()
        tray = _TrayAdapter(icon=icon)

        classifier = _clf.HotkeyClassifier(tap_threshold_ms=200)
        sm = StateMachine(tap_threshold_ms=200)
        keystroke = FakeKeystrokeSender()
        daemon = DaemonCore(
            state_machine=sm,
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hello world"),
                clock=lambda: 0.0,
            ),
            overlay=overlay,
            tray=tray,
            clipboard=FakeClipboardIO(),
            keystroke=keystroke,
            foreground=FakeForegroundTracker(),
        )
        bridge = _HotkeyBridge(classifier=classifier, callback=daemon.on_hotkey_event)

        _combo_down(bridge, ts=0)
        assert icon.last_state is not None
        assert icon.last_state.current_icon_variant() == IconVariant.Recording

        _combo_up(bridge, ts=100)

        _combo_down(bridge, ts=500)

        assert sm.state == State.IDLE
        assert keystroke.paste_count == 1
        assert icon.last_state.current_icon_variant() == IconVariant.Idle
