"""Daemon core — command dispatcher, error handling, and platform gate."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from dictatem.exceptions import (
    AudioCaptureError,
    ModelLoadError,
    PlatformNotSupportedError,
    TranscriptionFailedError,
)
from dictatem.state import Command, Event, State
from dictatem.types import EmptyResult, RecordingMode

if TYPE_CHECKING:
    from dictatem.audio.buffer import AudioBuffer
    from dictatem.interfaces import (
        AudioCapture,
        ClipboardIO,
        ForegroundTracker,
        KeystrokeSender,
        OverlayRenderer,
        TrayRenderer,
    )
    from dictatem.overlay.state import OverlayState
    from dictatem.state import StateMachine
    from dictatem.transcribe.lifecycle import TranscribeLifecycle

logger = logging.getLogger(__name__)


class _OverlayAdapter:
    """Bridges OverlayState + QtOverlayWidget to the OverlayRenderer protocol."""

    def __init__(self, *, state: OverlayState, widget: object) -> None:
        self._state = state
        self._widget = widget

    def show(self, mode: RecordingMode) -> None:
        self._state.show_recording(mode)
        self._widget.show_pill()  # type: ignore[attr-defined]

    def update_level(self, level: float) -> None:
        pass

    def show_transcribing(self) -> None:
        self._state.show_transcribing()

    def show_error(self) -> None:
        self._state.flash_error()

    def hide(self) -> None:
        self._state.hide()


class _HotkeyBridge:
    """Maps HotkeyClassifier events to StateMachine events and forwards them."""

    def __init__(
        self,
        *,
        classifier: object,
        callback: object,
    ) -> None:
        from dictatem.hotkey.classifier import HotkeyClassifier

        self._classifier: HotkeyClassifier = classifier  # type: ignore[assignment]
        self._callback = callback
        self._combo_active = False

    def on_key_event(self, vk: int, action: object, timestamp_ms: int) -> object:
        from dictatem.hotkey.classifier import HotkeyEvent

        was_combo = self._classifier.combo_held
        decision, event = self._classifier.process_event(vk, action, timestamp_ms)  # type: ignore[arg-type]
        is_combo = self._classifier.combo_held

        if not self._combo_active and is_combo:
            self._combo_active = True
            self._callback(Event.KEY_DOWN, now_ms=timestamp_ms)  # type: ignore[operator]

        if event is not None:
            self._dispatch_event(event, timestamp_ms)

        if self._combo_active and not is_combo and event is None:
            self._combo_active = False

        return decision

    def tick(self, timestamp_ms: int) -> None:
        from dictatem.hotkey.classifier import HotkeyEvent

        event = self._classifier.tick(timestamp_ms)
        if event is not None:
            self._dispatch_event(event, timestamp_ms)

    def _dispatch_event(self, event: object, timestamp_ms: int) -> None:
        from dictatem.hotkey.classifier import HotkeyEvent

        if event == HotkeyEvent.TAP:
            self._callback(Event.KEY_UP, now_ms=timestamp_ms)  # type: ignore[operator]
            self._combo_active = False
        elif event == HotkeyEvent.HOLD_START:
            self._callback(Event.TIMER_EXPIRED, now_ms=timestamp_ms)  # type: ignore[operator]
        elif event == HotkeyEvent.HOLD_END:
            self._callback(Event.KEY_UP, now_ms=timestamp_ms)  # type: ignore[operator]
            self._combo_active = False
        elif event == HotkeyEvent.ESC:
            self._callback(Event.ESC, now_ms=timestamp_ms)  # type: ignore[operator]
            self._combo_active = False


class _TrayAdapter:
    """Bridges a QtTrayIcon to the TrayRenderer protocol."""

    def __init__(self, *, icon: object) -> None:
        self._icon = icon
        self._recording = False
        self._error = False

    def set_idle(self) -> None:
        self._recording = False
        self._error = False
        self._sync()

    def set_recording(self) -> None:
        self._recording = True
        self._sync()

    def set_error(self) -> None:
        self._error = True
        self._sync()

    def show_notification(self, title: str, message: str) -> None:
        self._icon.show_notification(title, message)  # type: ignore[attr-defined]

    def _sync(self) -> None:
        from dictatem.tray.state import TrayState

        self._icon.update_state(  # type: ignore[attr-defined]
            TrayState(
                is_recording=self._recording,
                is_model_loaded=False,
                has_error=self._error,
            )
        )


class DaemonCore:
    """Wires the state machine to protocol implementations and handles errors.

    All public entry points have top-level try/except so that no exception
    can crash the daemon process.
    """

    def __init__(
        self,
        *,
        state_machine: StateMachine,
        audio_capture: AudioCapture,
        audio_buffer: AudioBuffer | None = None,
        lifecycle: TranscribeLifecycle,
        overlay: OverlayRenderer,
        tray: TrayRenderer,
        clipboard: ClipboardIO | None = None,
        keystroke: KeystrokeSender | None = None,
        foreground: ForegroundTracker | None = None,
        silence_timeout_s: float = 60.0,
    ) -> None:
        self._sm = state_machine
        self._audio_capture = audio_capture
        self._audio_buffer = audio_buffer
        self._lifecycle = lifecycle
        self._overlay = overlay
        self._tray = tray
        self._clipboard = clipboard
        self._keystroke = keystroke
        self._foreground = foreground
        self._silence_timeout_s = silence_timeout_s
        self._last_text: str | None = None

    def on_hotkey_event(self, event: Event, *, now_ms: int = 0) -> None:
        """Feed an event to the state machine and execute resulting commands."""
        try:
            commands = self._sm.handle(event, now_ms=now_ms)
            self._execute_commands(commands, now_ms=now_ms)
        except Exception:
            logger.error("Unhandled error in hotkey event handler", exc_info=True)
            self._tray.show_notification(
                "Dictatem Error",
                "An unexpected error occurred; check log",
            )
            self._recover_to_idle()

    def check_silence(self, *, now_ms: int = 0) -> None:
        """Poll audio buffer idle state and fire SILENCE_TIMEOUT if needed."""
        try:
            if self._sm.state not in (State.PTT_REC, State.TOGGLE_REC):
                return
            if self._audio_buffer is None:
                return
            if self._audio_buffer.is_idle_for_seconds(self._silence_timeout_s):
                logger.info(
                    "Silence timeout: no audio for %.0f s, auto-aborting",
                    self._silence_timeout_s,
                )
                commands = self._sm.handle(Event.SILENCE_TIMEOUT, now_ms=now_ms)
                self._execute_commands(commands, now_ms=now_ms)
        except Exception:
            logger.error("Error in silence check", exc_info=True)

    def _execute_commands(self, commands: list[Command], *, now_ms: int = 0) -> None:
        for cmd in commands:
            try:
                self._dispatch_command(cmd, now_ms=now_ms)
            except _AbortCommandChain:
                return

    def _dispatch_command(self, cmd: Command, *, now_ms: int = 0) -> None:
        if cmd is Command.RECORD_START:
            self._do_record_start()
        elif cmd is Command.RECORD_STOP_AND_TRANSCRIBE:
            self._do_transcribe(now_ms=now_ms)
        elif cmd is Command.CANCEL:
            self._do_cancel()
        elif cmd is Command.PASTE:
            self._do_paste()
        elif cmd is Command.FLASH_ERROR:
            self._overlay.show_error()
            self._tray.set_idle()
        elif cmd is Command.NOTIFY_ERROR:
            self._tray.show_notification(
                "Transcription Failed",
                "GPU memory exhausted; transcription failed.",
            )
        elif cmd is Command.RETRY_TRANSCRIPTION:
            self._do_transcribe(now_ms=now_ms)
        elif cmd is Command.START_TAP_TIMER:
            pass
        elif cmd is Command.CANCEL_TAP_TIMER:
            self._overlay.show(RecordingMode.TOGGLE)

    def _do_record_start(self) -> None:
        try:
            self._audio_capture.start()
        except AudioCaptureError:
            logger.warning(
                "Microphone unavailable — check Windows mic permissions "
                "(Settings → Privacy & security → Microphone)"
            )
            self._tray.show_notification(
                "Microphone Unavailable",
                "Microphone unavailable — check Windows mic permissions "
                "(Settings → Privacy & security → Microphone)",
            )
            self._recover_to_idle()
            raise _AbortCommandChain
        self._overlay.show(RecordingMode.PTT)
        self._tray.set_recording()

    def _do_transcribe(self, *, now_ms: int = 0) -> None:
        try:
            audio = self._audio_capture.stop()
        except Exception:
            audio = None

        self._overlay.show_transcribing()

        if audio is None:
            self._recover_to_idle()
            return

        try:
            result = self._lifecycle.transcribe(audio)
        except TranscriptionFailedError:
            logger.error("GPU memory exhausted; transcription failed")
            self._tray.show_notification(
                "Transcription Failed",
                "GPU memory exhausted; transcription failed.",
            )
            self._recover_to_idle()
            return
        except ModelLoadError:
            logger.error("Model unavailable; check log", exc_info=True)
            self._tray.show_notification(
                "Model Unavailable",
                "Model unavailable; check log",
            )
            self._recover_to_idle()
            return
        except Exception:
            logger.error("Unexpected transcription error", exc_info=True)
            self._tray.show_notification(
                "Transcription Error",
                "An unexpected error occurred during transcription; check log",
            )
            self._recover_to_idle()
            return

        if isinstance(result, EmptyResult):
            commands = self._sm.handle(Event.EMPTY_RESULT, now_ms=now_ms)
        else:
            self._last_text = result
            commands = self._sm.handle(Event.TRANSCRIPTION_DONE, now_ms=now_ms)

        self._execute_commands(commands, now_ms=now_ms)

    def _do_paste(self) -> None:
        if self._last_text and self._clipboard and self._keystroke and self._foreground:
            from dictatem.paste.pipeline import paste

            paste(
                self._last_text,
                clipboard=self._clipboard,
                keystroke=self._keystroke,
                foreground=self._foreground,
            )
        self._overlay.hide()
        self._tray.set_idle()
        self._last_text = None

    def _do_cancel(self) -> None:
        self._overlay.hide()
        self._tray.set_idle()
        self._last_text = None

    def on_tray_preload(self) -> None:
        try:
            self._lifecycle.preload()
        except Exception:
            logger.error("Error preloading model", exc_info=True)

    def on_tray_unload(self) -> None:
        try:
            self._lifecycle.unload()
        except Exception:
            logger.error("Error unloading model", exc_info=True)

    def on_tray_start_recording(self) -> None:
        if self._sm.state is not State.IDLE:
            return
        self.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        self.on_hotkey_event(Event.KEY_UP, now_ms=0)

    def on_tray_stop_recording(self) -> None:
        if self._sm.state is State.TOGGLE_REC:
            self.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
        elif self._sm.state in (State.PTT_REC, State.PRESSED):
            self.on_hotkey_event(Event.KEY_UP, now_ms=1000)

    def _recover_to_idle(self) -> None:
        self._sm._state = State.IDLE
        self._overlay.hide()
        self._tray.set_idle()
        self._last_text = None


class _AbortCommandChain(Exception):
    """Internal signal to stop processing remaining commands in a chain."""


def main() -> None:
    """Entry point for the Dictatem daemon."""
    if sys.platform != "win32":
        raise PlatformNotSupportedError(
            "Dictatem is Windows-only. "
            f"Current platform: {sys.platform}"
        )

    _start_windows_daemon()


def _start_windows_daemon() -> None:
    """Wire Windows adapters and start the Qt event loop."""
    import time
    from pathlib import Path

    from PySide6.QtCore import QTimer  # type: ignore[import-not-found]
    from PySide6.QtWidgets import QApplication  # type: ignore[import-not-found]

    from dictatem.audio.sounddevice_capture import SoundDeviceCapture
    from dictatem.config import load_config
    from dictatem.hotkey.classifier import HotkeyClassifier
    from dictatem.hotkey.wh_keyboard_ll import WHKeyboardLLHook
    from dictatem.overlay.qt_widget import QtOverlayWidget
    from dictatem.overlay.state import OverlayState
    from dictatem.paste.win32_clipboard import Win32ClipboardIO
    from dictatem.paste.win32_foreground import Win32ForegroundTracker
    from dictatem.paste.win32_keystroke import Win32KeystrokeSender
    from dictatem.state import StateMachine
    from dictatem.transcribe.faster_whisper_backend import FasterWhisperBackend
    from dictatem.transcribe.lifecycle import TranscribeLifecycle
    from dictatem.tray.qt_tray import QtTrayIcon

    config_path = Path.home() / ".dictatem" / "config.toml"
    config = load_config(config_path)

    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app = QApplication(sys.argv)

    audio_capture = SoundDeviceCapture(config)

    backend = FasterWhisperBackend(
        model_name=config.model.name,
        compute_type=config.model.compute_type,
        language=config.model.language,
        vad_filter=config.model.vad_filter,
    )
    lifecycle = TranscribeLifecycle(
        backend=backend,
        idle_timeout_s=config.model.idle_unload_minutes * 60,
        min_transcription_chars=config.model.min_transcription_chars,
    )

    clipboard = Win32ClipboardIO()
    keystroke = Win32KeystrokeSender()
    foreground = Win32ForegroundTracker()

    overlay_state = OverlayState(
        clock=time.monotonic,
        fade_in_ms=config.overlay.fade_in_ms,
        fade_out_ms=config.overlay.fade_out_ms,
    )
    overlay_widget = QtOverlayWidget(overlay_state)
    overlay = _OverlayAdapter(state=overlay_state, widget=overlay_widget)

    tray_icon = QtTrayIcon(app)
    tray = _TrayAdapter(icon=tray_icon)

    sm = StateMachine(tap_threshold_ms=config.hotkey.tap_threshold_ms)

    daemon = DaemonCore(
        state_machine=sm,
        audio_capture=audio_capture,
        audio_buffer=audio_capture._buffer,
        lifecycle=lifecycle,
        overlay=overlay,
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=foreground,
        silence_timeout_s=float(config.behaviour.silence_timeout_s),
    )

    tray_icon.on_start = daemon.on_tray_start_recording
    tray_icon.on_stop = daemon.on_tray_stop_recording
    tray_icon.on_preload = daemon.on_tray_preload
    tray_icon.on_unload = daemon.on_tray_unload
    tray_icon.on_quit = app.quit

    classifier = HotkeyClassifier(tap_threshold_ms=config.hotkey.tap_threshold_ms)
    bridge = _HotkeyBridge(classifier=classifier, callback=daemon.on_hotkey_event)
    hook = WHKeyboardLLHook(classifier)
    hook.install()

    silence_timer = QTimer()
    silence_timer.setInterval(5000)
    silence_timer.timeout.connect(
        lambda: daemon.check_silence(now_ms=int(time.monotonic() * 1000))
    )
    silence_timer.start()

    tick_timer = QTimer()
    tick_timer.setInterval(50)
    tick_timer.timeout.connect(
        lambda: bridge.tick(int(time.monotonic() * 1000))
    )
    tick_timer.start()

    logger.info("Dictatem daemon started")
    app.exec()
