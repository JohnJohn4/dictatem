"""Daemon core — command dispatcher, error handling, and platform gate."""

from __future__ import annotations

import logging
import queue
import sys
import threading
from typing import TYPE_CHECKING

from dictatem.exceptions import (
    AudioCaptureError,
    ModelLoadError,
    PlatformNotSupportedError,
    TranscriptionFailedError,
    TransformFailedError,
)
from dictatem.state import Command, Event, State
from dictatem.transform.last_paste import LastPaste
from dictatem.types import EmptyResult, RecordingMode

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.audio.buffer import AudioBuffer
    from dictatem.hotkey.classifier import HotkeyClassifier, HotkeyEvent, KeyAction
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
    from dictatem.transform.detector import TriggerDetector
    from dictatem.transform.lifecycle import TransformLifecycle

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
        self._widget.update_level(level)  # type: ignore[attr-defined]

    def show_transcribing(self) -> None:
        self._state.show_transcribing()

    def show_error(self) -> None:
        self._state.flash_error()

    def hide(self) -> None:
        self._state.hide()


class _HotkeyBridge:
    """Maps HotkeyClassifier events to StateMachine events and forwards them.

    The OS keyboard hook runs on a separate thread; Qt widget operations
    must run on the GUI thread.  ``enqueue_key_event`` is the thread-safe
    entry point for the hook thread, and ``tick`` (driven by a Qt timer on
    the GUI thread) drains the queue and runs all classifier + dispatch
    logic single-threaded.
    """

    def __init__(
        self,
        *,
        classifier: HotkeyClassifier,
        callback: Callable[..., None],
    ) -> None:
        self._classifier = classifier
        self._callback = callback
        self._combo_active = False
        self._queue: queue.Queue[tuple[int, KeyAction, int]] = queue.Queue()

    def enqueue_key_event(
        self, vk: int, action: KeyAction, timestamp_ms: int
    ) -> None:
        """Thread-safe entry point invoked from the keyboard hook thread."""
        self._queue.put((vk, action, timestamp_ms))

    def on_key_event(self, vk: int, action: KeyAction, timestamp_ms: int) -> object:
        decision, event = self._classifier.process_event(vk, action, timestamp_ms)
        is_combo = self._classifier.combo_held

        if not self._combo_active and is_combo:
            self._combo_active = True
            self._callback(Event.KEY_DOWN, now_ms=timestamp_ms)

        if event is not None:
            self._dispatch_event(event, timestamp_ms)

        if self._combo_active and not is_combo and event is None:
            self._combo_active = False

        return decision

    def tick(self, timestamp_ms: int) -> None:
        while True:
            try:
                vk, action, ev_ts = self._queue.get_nowait()
            except queue.Empty:
                break
            self.on_key_event(vk, action, ev_ts)

        event = self._classifier.tick(timestamp_ms)
        if event is not None:
            self._dispatch_event(event, timestamp_ms)

    def _dispatch_event(self, event: HotkeyEvent, timestamp_ms: int) -> None:
        from dictatem.hotkey.classifier import HotkeyEvent

        if event == HotkeyEvent.TAP:
            self._callback(Event.KEY_UP, now_ms=timestamp_ms)
            self._combo_active = False
        elif event == HotkeyEvent.HOLD_START:
            self._callback(Event.TIMER_EXPIRED, now_ms=timestamp_ms)
        elif event == HotkeyEvent.HOLD_END:
            self._callback(Event.KEY_UP, now_ms=timestamp_ms)
            self._combo_active = False
        elif event == HotkeyEvent.ESC:
            self._callback(Event.ESC, now_ms=timestamp_ms)
            self._combo_active = False


class _TrayAdapter:
    """Bridges a QtTrayIcon to the TrayRenderer protocol."""

    def __init__(self, *, icon: object) -> None:
        self._icon = icon
        self._recording = False
        self._error = False
        self._model_loaded = False
        self._model_loading = False

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

    def set_model_loaded(self, loaded: bool) -> None:
        if loaded == self._model_loaded:
            return
        self._model_loaded = loaded
        self._sync()

    def set_model_loading(self, loading: bool) -> None:
        if loading == self._model_loading:
            return
        self._model_loading = loading
        self._sync()

    def show_notification(self, title: str, message: str) -> None:
        self._icon.show_notification(title, message)  # type: ignore[attr-defined]

    def _sync(self) -> None:
        from dictatem.tray.state import TrayState

        self._icon.update_state(  # type: ignore[attr-defined]
            TrayState(
                is_recording=self._recording,
                is_model_loaded=self._model_loaded,
                has_error=self._error,
                is_model_loading=self._model_loading,
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
        max_recording_s: float = 300.0,
        transform_lifecycle: TransformLifecycle | None = None,
        trigger_detector: TriggerDetector | None = None,
        transform_enabled: bool = False,
        last_paste_ttl_s: float = 300.0,
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
        self._max_recording_s = max_recording_s
        self._last_text: str | None = None
        self._transcription_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._transcription_active: bool = False
        self._transcription_thread: threading.Thread | None = None
        # --- Trigger Words / Transform state (see CONTEXT.md) ---
        self._transform_lifecycle = transform_lifecycle
        self._trigger_detector = trigger_detector
        self._transform_enabled = transform_enabled
        self._last_paste_ttl_s = last_paste_ttl_s
        self._last_paste: LastPaste | None = None
        self._pending_replace_chars: int = 0
        self._transform_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._transform_active: bool = False
        self._transform_thread: threading.Thread | None = None

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
            if self._audio_buffer.duration_seconds >= self._max_recording_s:
                logger.info(
                    "Max recording duration reached (%.0f s), transcribing",
                    self._max_recording_s,
                )
                self._tray.show_notification(
                    "Dictatem",
                    "Max duration reached — transcribing…",
                )
                commands = self._sm.handle(Event.MAX_DURATION, now_ms=now_ms)
                self._execute_commands(commands, now_ms=now_ms)
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
            self._do_paste(now_ms=now_ms)
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

        self._transcription_active = True

        def _worker(captured_audio: object) -> None:
            try:
                result = self._lifecycle.transcribe(captured_audio)  # type: ignore[arg-type]
            except TranscriptionFailedError:
                self._transcription_queue.put(("transcription_failed", None))
            except ModelLoadError as exc:
                self._transcription_queue.put(("model_error", exc))
            except Exception as exc:
                self._transcription_queue.put(("unexpected_error", exc))
            else:
                self._transcription_queue.put(("ok", result))

        t = threading.Thread(
            target=_worker, args=(audio,), daemon=True, name="transcribe-worker"
        )
        self._transcription_thread = t
        t.start()

    def check_transcription_result(self, *, now_ms: int = 0) -> None:
        """Drain the transcription result queue and process any completed result.

        Called on every 50 ms tick so the Qt event loop stays responsive
        while faster-whisper runs on the worker thread.
        """
        try:
            kind, data = self._transcription_queue.get_nowait()
        except queue.Empty:
            return

        if not self._transcription_active:
            return  # ESC was pressed before result arrived — discard

        try:
            if kind == "transcription_failed":
                self._transcription_active = False
                logger.error("GPU memory exhausted; transcription failed")
                self._tray.show_notification(
                    "Transcription Failed",
                    "GPU memory exhausted; transcription failed.",
                )
                self._recover_to_idle()
            elif kind == "model_error":
                self._transcription_active = False
                logger.error("Model unavailable; check log", exc_info=data)  # type: ignore[arg-type]
                self._tray.show_notification(
                    "Model Unavailable",
                    "Model unavailable; check log",
                )
                self._recover_to_idle()
            elif kind == "unexpected_error":
                self._transcription_active = False
                logger.error("Unexpected transcription error: %s", data)
                self._tray.show_notification(
                    "Transcription Error",
                    "An unexpected error occurred during transcription; check log",
                )
                self._recover_to_idle()
            else:
                result = data
                if isinstance(result, EmptyResult):
                    self._transcription_active = False
                    logger.info("Transcription produced empty result")
                    commands = self._sm.handle(Event.EMPTY_RESULT, now_ms=now_ms)
                    self._execute_commands(commands, now_ms=now_ms)
                    return

                # Trigger Word detection — see CONTEXT.md#trigger-fire.
                prompt = self._detect_trigger(result)  # type: ignore[arg-type]
                if prompt is None:
                    self._transcription_active = False
                    logger.info(
                        "Transcription complete (%d chars): %r",
                        len(result),  # type: ignore[arg-type]
                        result[:80] + ("..." if len(result) > 80 else ""),  # type: ignore[index,operator]
                    )
                    self._last_text = result  # type: ignore[assignment]
                    commands = self._sm.handle(Event.TRANSCRIPTION_DONE, now_ms=now_ms)
                    self._execute_commands(commands, now_ms=now_ms)
                else:
                    self._handle_trigger_fire(prompt, now_ms=now_ms)
        except Exception:
            logger.error("Unhandled error processing transcription result", exc_info=True)
            self._recover_to_idle()

    def _detect_trigger(self, text: str) -> str | None:
        """Return the prompt body for *text* if it is a Trigger Word.

        Returns ``None`` if the feature is disabled, no detector is wired,
        no Last Paste exists, or *text* is just regular dictation.
        """
        if not self._transform_enabled:
            return None
        if self._trigger_detector is None:
            return None
        if self._last_paste is None:
            return None
        return self._trigger_detector.match(text)

    def _handle_trigger_fire(self, prompt: str, *, now_ms: int) -> None:
        """Run a Transform on the Last Paste; defer the SM event until it returns.

        Safety rails (HWND + TTL) gate the call. On rail failure the
        transcription leg is closed with EMPTY_RESULT so the existing
        FLASH_ERROR path runs; the document is untouched.
        """
        assert self._last_paste is not None
        assert self._transform_lifecycle is not None

        current_hwnd = self._foreground.capture() if self._foreground is not None else 0
        if not self._last_paste.rails_ok(
            current_hwnd=current_hwnd,
            now_ms=now_ms,
            ttl_s=self._last_paste_ttl_s,
        ):
            logger.info(
                "Trigger Fire aborted: rails failed "
                "(hwnd_now=%s, hwnd_paste=%s, age_ms=%d, ttl_s=%.0f)",
                current_hwnd,
                self._last_paste.hwnd,
                now_ms - self._last_paste.pasted_at_ms,
                self._last_paste_ttl_s,
            )
            self._last_paste = None
            self._transcription_active = False
            commands = self._sm.handle(Event.EMPTY_RESULT, now_ms=now_ms)
            self._execute_commands(commands, now_ms=now_ms)
            return

        captured = self._last_paste
        lifecycle = self._transform_lifecycle
        self._transform_active = True
        logger.info(
            "Trigger Fire: starting Transform on %d-char Last Paste",
            captured.char_count,
        )

        def _worker() -> None:
            try:
                out = lifecycle.transform(captured.text, prompt)
            except TransformFailedError as exc:
                self._transform_queue.put(("transform_failed", exc))
            except Exception as exc:
                self._transform_queue.put(("transform_unexpected", exc))
            else:
                self._transform_queue.put(("ok", (out, captured.char_count)))

        t = threading.Thread(
            target=_worker, daemon=True, name="transform-worker"
        )
        self._transform_thread = t
        t.start()

    def check_transform_result(self, *, now_ms: int = 0) -> None:
        """Drain the transform result queue and feed the SM the deferred event."""
        try:
            kind, data = self._transform_queue.get_nowait()
        except queue.Empty:
            return

        if not self._transform_active or not self._transcription_active:
            # ESC pressed during transform; discard.
            return

        self._transform_active = False
        self._transcription_active = False

        try:
            if kind == "ok":
                text, replace_chars = data  # type: ignore[misc]
                logger.info(
                    "Transform complete (%d chars), replacing %d chars",
                    len(text),
                    replace_chars,
                )
                self._last_text = text
                self._pending_replace_chars = replace_chars
                commands = self._sm.handle(Event.TRANSCRIPTION_DONE, now_ms=now_ms)
                self._execute_commands(commands, now_ms=now_ms)
            else:
                logger.warning("Transform failed: %s", data)
                self._tray.show_notification(
                    "Transform Failed",
                    "The Trigger Word transform could not be applied; check log",
                )
                commands = self._sm.handle(Event.EMPTY_RESULT, now_ms=now_ms)
                self._execute_commands(commands, now_ms=now_ms)
        except Exception:
            logger.error("Unhandled error processing transform result", exc_info=True)
            self._recover_to_idle()

    def drain_transcription_for_test(self, *, now_ms: int = 0) -> None:
        """Block until in-flight transcription (and any deferred transform)
        completes, then process the result.

        Only for use in tests — production code uses the 50 ms tick timer.
        """
        if self._transcription_thread is not None:
            self._transcription_thread.join(timeout=5.0)
        self.check_transcription_result(now_ms=now_ms)
        if self._transform_thread is not None:
            self._transform_thread.join(timeout=5.0)
        self.check_transform_result(now_ms=now_ms)

    def _do_paste(self, *, now_ms: int = 0) -> None:
        replace = self._pending_replace_chars
        self._pending_replace_chars = 0

        if self._last_text and self._clipboard and self._keystroke and self._foreground:
            from dictatem.paste.pipeline import normalize_pasted_text, paste

            paste(
                self._last_text,
                clipboard=self._clipboard,
                keystroke=self._keystroke,
                foreground=self._foreground,
                replace_chars=replace,
            )
            normalized = normalize_pasted_text(self._last_text)
            self._last_paste = LastPaste(
                text=normalized,
                char_count=len(normalized),
                hwnd=self._foreground.capture(),
                pasted_at_ms=now_ms,
            )
        else:
            logger.warning(
                "Paste skipped: text=%r, clipboard=%s, keystroke=%s, foreground=%s",
                bool(self._last_text),
                self._clipboard is not None,
                self._keystroke is not None,
                self._foreground is not None,
            )
        self._overlay.hide()
        self._tray.set_idle()
        self._last_text = None

    def _do_cancel(self) -> None:
        self._transcription_active = False
        self._transform_active = False
        self._pending_replace_chars = 0
        self._last_paste = None
        try:
            self._audio_capture.stop()
        except Exception:
            logger.exception("Error stopping audio capture during cancel")
        self._overlay.hide()
        self._tray.set_idle()
        self._last_text = None

    def on_tray_preload(self) -> None:
        try:
            self._lifecycle.preload()
        except Exception:
            logger.error("Error preloading model", exc_info=True)
        self.sync_model_loaded()

    def on_tray_unload(self) -> None:
        try:
            self._lifecycle.unload()
        except Exception:
            logger.error("Error unloading model", exc_info=True)
        self.sync_model_loaded()

    def on_tray_quit(self, quit_callback: Callable[[], None]) -> None:
        """Unload the model gracefully, then invoke ``quit_callback`` to exit."""
        self.on_tray_unload()
        quit_callback()

    def sync_model_loaded(self) -> None:
        """Push the current model-load state into the tray.

        Model loading runs on a background thread, so the tray must be
        polled to reflect transitions in/out of the loaded and loading
        states.
        """
        try:
            self._tray.set_model_loaded(self._lifecycle.is_loaded)  # type: ignore[attr-defined]
            self._tray.set_model_loading(self._lifecycle.is_loading)  # type: ignore[attr-defined]
        except Exception:
            logger.error("Error syncing model-load state", exc_info=True)

    def check_idle(self) -> None:
        try:
            self._lifecycle.check_idle()
        except Exception:
            logger.error("Error during idle check", exc_info=True)

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
        self._transcription_active = False
        self._transform_active = False
        self._pending_replace_chars = 0
        self._last_paste = None
        self._sm._state = State.IDLE
        try:
            self._audio_capture.stop()
        except Exception:
            logger.exception("Error stopping audio capture during recovery")
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
    from dictatem.hardware.nvidia_probe import NvidiaHardwareProbe
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
    from dictatem.transform.detector import TriggerDetector
    from dictatem.transform.lifecycle import TransformLifecycle
    from dictatem.transform.ollama_backend import OllamaBackend
    from dictatem.transform.prompts import (
        bootstrap_prompts,
        default_prompts_dir,
        load_prompts_dir,
    )
    from dictatem.tray.qt_tray import QtTrayIcon

    config_path = Path.home() / ".dictatem" / "config.toml"
    # First run with no config: probe the machine once and bake the resolved
    # Hardware Tier (model/device/compute_type + transform tag) into the file.
    # Existing configs are read unchanged and the probe is not consulted.
    config = load_config(config_path, probe=NvidiaHardwareProbe())

    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # Library chatter — model-download HTTP requests, hub probes, etc. — is
    # noisy at INFO. Our own load/unload lines tell the user what they need.
    for noisy in ("httpx", "huggingface_hub", "filelock", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    app = QApplication(sys.argv)

    audio_capture = SoundDeviceCapture(config)

    backend = FasterWhisperBackend(
        model_name=config.model.name,
        compute_type=config.model.compute_type,
        device=config.model.device,
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

    transform_backend = OllamaBackend(
        model_name=config.transform.model_name,
        base_url=config.transform.base_url,
        timeout_s=float(config.transform.timeout_s),
    )
    transform_lifecycle = TransformLifecycle(backend=transform_backend)
    prompts_dir = Path.home() / ".dictatem" / "prompts"
    bootstrap_prompts(prompts_dir, default_prompts_dir())
    trigger_detector = TriggerDetector(load_prompts_dir(prompts_dir))

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
        max_recording_s=float(config.behaviour.max_recording_seconds),
        transform_lifecycle=transform_lifecycle,
        trigger_detector=trigger_detector,
        transform_enabled=config.transform.enabled,
        last_paste_ttl_s=float(config.transform.last_paste_ttl_s),
    )

    tray_icon.on_start = daemon.on_tray_start_recording
    tray_icon.on_stop = daemon.on_tray_stop_recording
    tray_icon.on_preload = daemon.on_tray_preload
    tray_icon.on_unload = daemon.on_tray_unload
    tray_icon.on_quit = lambda: daemon.on_tray_quit(app.quit)

    classifier = HotkeyClassifier(tap_threshold_ms=config.hotkey.tap_threshold_ms)
    classifier.set_active(True)
    bridge = _HotkeyBridge(classifier=classifier, callback=daemon.on_hotkey_event)
    hook = WHKeyboardLLHook(bridge.enqueue_key_event)
    hook.install()

    silence_timer = QTimer()
    silence_timer.setInterval(5000)

    def _on_silence_tick() -> None:
        daemon.check_silence(now_ms=int(time.monotonic() * 1000))
        daemon.check_idle()
        daemon.sync_model_loaded()

    silence_timer.timeout.connect(_on_silence_tick)
    silence_timer.start()

    if config.startup.preload_model:
        logger.info("Startup preload enabled — loading model in background")
        daemon.on_tray_preload()

    def _on_tick() -> None:
        now = int(time.monotonic() * 1000)
        bridge.tick(now)
        overlay.update_level(audio_capture._buffer.current_level())
        daemon.check_transcription_result(now_ms=now)
        daemon.check_transform_result(now_ms=now)

    tick_timer = QTimer()
    tick_timer.setInterval(50)
    tick_timer.timeout.connect(_on_tick)
    tick_timer.start()

    logger.info("Dictatem daemon started")
    app.exec()
