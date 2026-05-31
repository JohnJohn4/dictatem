"""Daemon core — command dispatcher, error handling, and platform gate."""

from __future__ import annotations

import logging
import logging.handlers
import os
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
        AutostartRegistrar,
        ClipboardIO,
        ForegroundTracker,
        KeystrokeSender,
        OverlayRenderer,
        TrayRenderer,
    )
    from dictatem.overlay.state import OverlayState
    from dictatem.state import StateMachine
    from dictatem.transcribe.latency_monitor import LatencyMonitor
    from dictatem.transcribe.lifecycle import TranscribeLifecycle
    from dictatem.transform.detector import TriggerDetector
    from dictatem.transform.lifecycle import TransformLifecycle

logger = logging.getLogger(__name__)


def _add_rotating_log_file() -> logging.handlers.TimedRotatingFileHandler | None:
    """Attach a rotating file handler at %APPDATA%\\Dictatem\\logs\\daemon.log.

    The daemon launches via a windowless gui-scripts entry point (ADR-0011),
    which has no console — so stderr-only logging is lost. Without this the
    "check the logs" error and the tray "Open log" menu both point at a file
    that is never written. Returns the handler so the caller can align its
    ``backupCount`` with ``config.logging.rotation_days`` once config loads,
    or ``None`` if the log file could not be opened.
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    log_dir = os.path.join(appdata, "Dictatem", "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.handlers.TimedRotatingFileHandler(
            os.path.join(log_dir, "daemon.log"),
            when="midnight",
            backupCount=7,
            encoding="utf-8",
        )
    except OSError:
        logger.warning("Could not open log file under %s", log_dir, exc_info=True)
        return None
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    logging.getLogger().addHandler(handler)
    return handler




class _OverlayAdapter:
    """Bridges OverlayState + QtOverlayWidget to the OverlayRenderer protocol."""

    def __init__(self, *, state: OverlayState, widget: object) -> None:
        self._state = state
        self._widget = widget

    def show(self, mode: RecordingMode) -> None:
        self._state.show_recording(mode)
        self._widget.show_pill()  # type: ignore[attr-defined]

    def show_loading(self, label: str = "Model Loading") -> None:
        self._state.show_loading(label)
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
        restore_scheduler: Callable[[float, Callable[[], None]], None] | None = None,
        silence_timeout_s: float = 60.0,
        max_recording_s: float = 300.0,
        transform_lifecycle: TransformLifecycle | None = None,
        trigger_detector: TriggerDetector | None = None,
        transform_enabled: bool = False,
        last_paste_ttl_s: float = 300.0,
        transform_model_name: str = "",
        transform_base_url: str = "",
        llm_keep_alive_s: float = 1800.0,
        latency_monitor: LatencyMonitor | None = None,
        autostart_registrar: AutostartRegistrar | None = None,
        persist_autostart: Callable[[bool], None] | None = None,
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
        self._restore_scheduler = restore_scheduler
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
        self._transform_model_name = transform_model_name
        self._transform_base_url = transform_base_url
        # How long the LLM is presumed resident after a transform/warm — matches
        # the Ollama keep_alive window — so a follow-up trigger reads as
        # "computing" rather than "loading" (#74).
        self._llm_keep_alive_ms = int(llm_keep_alive_s * 1000)
        self._last_paste: LastPaste | None = None
        self._pending_replace_chars: int = 0
        self._transform_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._transform_active: bool = False
        self._transform_thread: threading.Thread | None = None
        # --- Model-loading overlay state (#74) ---
        # _loading_for_transcribe: a first-tap cold load is showing the "Model
        # Loading" pill, to be flipped to the transcribing dot once resident.
        # _preload_pill_active / _llm_warming: a tray Preload pill is up until
        # both Whisper and the (best-effort) LLM warm finish.
        self._loading_for_transcribe: bool = False
        self._preload_pill_active: bool = False
        self._llm_warming: bool = False
        self._llm_warm_thread: threading.Thread | None = None
        # Monotonic-ms deadline until which the LLM is presumed warm (#74).
        self._llm_warm_until_ms: int = 0
        # --- Latency tip (one-shot, see ADR-0007) ---
        self._latency_monitor = latency_monitor
        # --- Autostart toggle (see ADR-0012) ---
        self._autostart_registrar = autostart_registrar
        self._persist_autostart = persist_autostart

    def on_tray_set_autostart(self, enabled: bool) -> None:
        """Apply the tray "Start at login" toggle (see ADR-0012).

        Reconciles the OS autostart entry to *enabled* via the registrar and
        persists the new ``config.startup.autostart`` flag so it survives a
        restart — keeping the flag the single source of truth. Wrapped so a
        registry hiccup can never crash the daemon.
        """
        try:
            if self._autostart_registrar is not None:
                from dictatem.autostart.reconcile import apply_autostart

                apply_autostart(
                    desired=enabled, registrar=self._autostart_registrar
                )
            if self._persist_autostart is not None:
                self._persist_autostart(enabled)
        except Exception:
            logger.error("Error applying autostart toggle", exc_info=True)

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

        # Cold model load? Show the animated "Model Loading" pill and flip to
        # the amber transcribing dot once the model is resident (#74). A warm
        # model goes straight to transcribing.
        if self._lifecycle.is_loaded:
            self._overlay.show_transcribing()
            self._loading_for_transcribe = False
        else:
            self._overlay.show_loading("Loading Dict. Model")
            self._loading_for_transcribe = True

        if audio is None:
            self._recover_to_idle()
            return

        self._transcription_active = True

        from dictatem.types import SAMPLE_RATE

        def _worker(captured_audio: object) -> None:
            # Only one transcription runs at a time (the state machine gates
            # it), so the worker thread can safely drive the LatencyMonitor.
            audio_duration_s = len(captured_audio) / SAMPLE_RATE  # type: ignore[arg-type]
            if self._latency_monitor is not None:
                self._latency_monitor.begin()
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
                # One-shot "transcriptions are slow" tip (see ADR-0007):
                # surface ONE smaller-model hint when slowness is consistent.
                # Notifications must run on the Qt GUI thread, so route the
                # tip through the result queue rather than calling the tray
                # from this worker thread.
                if self._latency_monitor is not None and (
                    self._latency_monitor.end(audio_duration_s)
                ):
                    self._transcription_queue.put(("latency_tip", None))

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

        # The one-shot latency tip (see ADR-0007) is enqueued AFTER the "ok"
        # result, so by the time it is drained on a later tick the ok result
        # has already cleared ``_transcription_active``. Handle it here, before
        # the guard, so it is not silently discarded.
        if kind == "latency_tip":
            self._tray.show_notification(
                "Dictatem",
                "Transcriptions are slow — switching to a smaller model may "
                "help. See the README.",
            )
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
        # Within the keep_alive window the model is already resident, so the
        # work is generation ("computing"), not a load. Only call it "loading"
        # the first time or after it has gone idle and unloaded (#74).
        if now_ms < self._llm_warm_until_ms:
            self._overlay.show_loading("LLM Model Computing")
        else:
            self._overlay.show_loading("Loading LLM Model")

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
                # The model just generated, so it is resident: a follow-up
                # trigger within keep_alive is "computing", not "loading" (#74).
                self._llm_warm_until_ms = now_ms + self._llm_keep_alive_ms
                commands = self._sm.handle(Event.TRANSCRIPTION_DONE, now_ms=now_ms)
                self._execute_commands(commands, now_ms=now_ms)
            else:
                logger.warning("Transform failed: %s", data)
                title, message = self._diagnose_transform_failure(data)
                self._tray.show_notification(title, message)
                commands = self._sm.handle(Event.EMPTY_RESULT, now_ms=now_ms)
                self._execute_commands(commands, now_ms=now_ms)
        except Exception:
            logger.error("Unhandled error processing transform result", exc_info=True)
            self._recover_to_idle()

    def _diagnose_transform_failure(self, error: object) -> tuple[str, str]:
        """Map a failed Transform into a ``(title, message)`` to surface.

        For a ``TransformFailedError`` carrying a structured ``failure``
        signal, run the pure classifier so the user gets an actionable next
        step. Everything else falls back to a generic check-the-log message.
        """
        from dictatem.transform.failure_classifier import (
            FailureReason,
            classify_transform_failure,
        )

        failure = getattr(error, "failure", None)
        if failure is None:
            return (
                "Transform Failed",
                "The Trigger Word transform could not be applied; check log",
            )

        reason, message = classify_transform_failure(
            failure=failure,
            model_name=self._transform_model_name,
            base_url=self._transform_base_url,
        )
        titles = {
            FailureReason.NOT_RUNNING: "Ollama Not Running",
            FailureReason.MODEL_MISSING: "Ollama Model Missing",
            FailureReason.UNKNOWN: "Transform Failed",
        }
        return titles[reason], message

    def drain_transcription_for_test(self, *, now_ms: int = 0) -> None:
        """Block until in-flight transcription (and any deferred transform)
        completes, then process the result.

        Only for use in tests — production code uses the 50 ms tick timer.
        """
        if self._transcription_thread is not None:
            self._transcription_thread.join(timeout=5.0)
        # Mirror the production tick: flip the loading pill to transcribing once
        # the model is resident, before the result is processed (#74).
        self.check_loading_overlay(now_ms=now_ms)
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
                schedule_restore=self._restore_scheduler,
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
            both = self._transform_enabled and self._transform_lifecycle is not None
            self._overlay.show_loading(
                "Preloading Models" if both else "Loading Dict. Model"
            )
            self._preload_pill_active = True
            self._lifecycle.preload()
            self._start_llm_warm()
        except Exception:
            logger.error("Error preloading model", exc_info=True)
        self.sync_model_loaded()

    def _start_llm_warm(self) -> None:
        """Best-effort: warm the Transform LLM in the background during Preload.

        Skips (logged) when the Transform is disabled, Ollama is unreachable, or
        the model isn't pulled — Whisper preload is never affected, and nothing
        here can raise into the daemon (#74). The network probe and load run off
        the GUI thread.
        """
        if not self._transform_enabled or self._transform_lifecycle is None:
            return
        if self._llm_warming:
            return
        self._llm_warming = True
        lifecycle = self._transform_lifecycle

        def _worker() -> None:
            try:
                if not lifecycle.is_model_available():
                    logger.info(
                        "LLM preload skipped: %s unavailable in Ollama",
                        self._transform_model_name,
                    )
                    return
                if lifecycle.warm():
                    logger.info("LLM %s warmed", self._transform_model_name)
                else:
                    logger.warning(
                        "LLM warm did not complete for %s",
                        self._transform_model_name,
                    )
            except Exception:
                logger.error("Error warming LLM", exc_info=True)
            finally:
                self._llm_warming = False

        self._llm_warm_thread = threading.Thread(
            target=_worker, daemon=True, name="llm-warm"
        )
        self._llm_warm_thread.start()

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

    def check_loading_overlay(self, *, now_ms: int = 0) -> None:
        """Drive the "Model Loading" pill from background load state (#74).

        Runs on the fast tick: flips the first-tap loading pill to the amber
        transcribing dot once the transcription model is resident, and dismisses
        the Preload loading pill once both Whisper and the LLM warm finish.
        """
        try:
            if self._loading_for_transcribe and self._lifecycle.is_loaded:
                self._loading_for_transcribe = False
                if self._transcription_active:
                    self._overlay.show_transcribing()
            if (
                self._preload_pill_active
                and not self._lifecycle.is_loading
                and not self._llm_warming
            ):
                self._preload_pill_active = False
                self._overlay.hide()
        except Exception:
            logger.error("Error updating loading overlay", exc_info=True)

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


def main(argv: list[str] | None = None) -> None:
    """Entry point for the Dictatem daemon.

    With no arguments, starts the daemon (Windows only). ``--uninstall`` runs
    the cleanup that removes the daemon-owned autostart entry and prints the
    final ``uv tool uninstall dictatem`` step (see ADR-0011); a bare tool
    uninstall would otherwise orphan that entry.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="dictatem", description="Local voice-dictation daemon for Windows."
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the autostart entry, then print the uv tool uninstall step.",
    )
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        raise PlatformNotSupportedError(
            "Dictatem is Windows-only. "
            f"Current platform: {sys.platform}"
        )

    if args.uninstall:
        _run_uninstall()
        return

    _start_windows_daemon()


def _run_uninstall() -> None:
    """Wire the Windows registrar and run the uninstall cleanup (#58).

    The gui-scripts launcher is windowless (ADR-0011), so console output is
    invisible — collect the cleanup's guidance and show it in a message box so
    the user sees the remaining ``uv tool uninstall dictatem`` step. The README
    also documents the two-step uninstall as the canonical reference.
    """
    from dictatem.autostart.reconcile import run_uninstall
    from dictatem.autostart.win32_registrar import Win32AutostartRegistrar

    lines: list[str] = []
    run_uninstall(registrar=Win32AutostartRegistrar(), out=lines.append)
    _show_uninstall_message("\n".join(lines))


def _show_uninstall_message(message: str) -> None:
    """Surface uninstall guidance in a dialog; print as a fallback off Windows.

    A windowless launch has no console, so a message box is the only reliable
    way to reach the user. The dialog text is selectable (Ctrl+C copies it),
    and the full two-step uninstall also lives in the README.
    """
    if sys.platform != "win32":
        print(message)
        return
    import ctypes

    mb_ok_iconinfo = 0x40  # MB_OK | MB_ICONINFORMATION
    ctypes.windll.user32.MessageBoxW(0, message, "Dictatem", mb_ok_iconinfo)


def _start_windows_daemon() -> None:
    """Wire Windows adapters and start the Qt event loop."""
    import time
    from pathlib import Path

    from PySide6.QtCore import QTimer  # type: ignore[import-not-found]
    from PySide6.QtWidgets import QApplication  # type: ignore[import-not-found]

    from dictatem.audio.sounddevice_capture import SoundDeviceCapture
    from dictatem.autostart.reconcile import apply_autostart
    from dictatem.autostart.win32_registrar import Win32AutostartRegistrar
    from dictatem.config import load_config, write_config
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
    from dictatem.transcribe.latency_monitor import LatencyMonitor
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

    # Configure logging before load_config so the first-run Hardware Tier
    # baking line (logged inside load_config) is actually emitted. Start at
    # INFO, then drop to the configured level once we've read it.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # Persist to a rotating file so the windowless launch leaves a trail (the
    # console handler above goes nowhere when there is no console).
    log_file_handler = _add_rotating_log_file()
    # Library chatter — model-download HTTP requests, hub probes, etc. — is
    # noisy at INFO. Our own load/unload lines tell the user what they need.
    for noisy in ("httpx", "huggingface_hub", "filelock", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    config_path = Path.home() / ".dictatem" / "config.toml"
    # First run with no config: probe the machine once and bake the resolved
    # Hardware Tier (model/device/compute_type + transform tag) into the file.
    # Existing configs are read unchanged and the probe is not consulted.
    probe = NvidiaHardwareProbe()
    config = load_config(config_path, probe=probe)

    # Reconcile the config's pinned transcription hardware against the machine
    # we're actually on (#39 / ADR-0009). A config baked on a GPU box and then
    # run on a CPU-only machine would otherwise crash faster-whisper at model
    # load. On the absent-GPU case we fall back to the CPU tier FOR THIS SESSION
    # only — the config file is never rewritten, so the user's pinned GPU values
    # return automatically once the hardware does.
    from dictatem.hardware.resolver import HardwareTierResolver

    effective, did_fall_back = HardwareTierResolver().reconcile(
        device=config.model.device,
        model=config.model.name,
        compute_type=config.model.compute_type,
        profile=probe.probe(),
    )
    # Transcription hardware only. We deliberately do NOT apply
    # effective.transform_model: the Transform/Ollama model is independent of
    # CUDA and reconcile carries the CPU tier's tag in the fallback case purely
    # as a side effect of returning the whole row (see ADR-0009).
    effective_model = effective.model
    effective_device = effective.device
    effective_compute_type = effective.compute_type

    logging.getLogger().setLevel(
        getattr(logging, config.logging.level.upper(), logging.INFO)
    )
    if log_file_handler is not None:
        log_file_handler.backupCount = config.logging.rotation_days

    # Reconcile the OS autostart entry to config.startup.autostart on launch
    # (#55 / ADR-0012). The daemon — not the installer — owns autostart, so the
    # flag is the single source of truth: register the HKCU Run entry when the
    # flag is on and it's missing, remove it when the flag is off and it's
    # present. apply_autostart runs the pure decision and applies it via the
    # registrar adapter; the tray "Start at login" toggle flips the same flag.
    autostart_registrar = Win32AutostartRegistrar()
    apply_autostart(desired=config.startup.autostart, registrar=autostart_registrar)

    app = QApplication(sys.argv)

    audio_capture = SoundDeviceCapture(config)

    backend = FasterWhisperBackend(
        model_name=effective_model,
        compute_type=effective_compute_type,
        device=effective_device,
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
        timeout_s=float(config.behaviour.model_timeout_s),
        # Keep the LLM resident for the same idle window as Whisper so repeat
        # Trigger Words don't re-pay the ~50 s cold load (#74).
        keep_alive=f"{config.model.idle_unload_minutes}m",
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

    latency_monitor = LatencyMonitor(clock=time.monotonic)

    def _persist_autostart(enabled: bool) -> None:
        # Flip the live flag and rewrite the config so the toggle survives a
        # restart. The config file is the single source of truth (ADR-0012).
        config.startup.autostart = enabled
        write_config(config, config_path)

    def _schedule_clipboard_restore(
        delay_s: float, callback: Callable[[], None]
    ) -> None:
        # Defer the clipboard restore on the Qt event loop so the target window
        # reads our pasted text before the user's clipboard is put back (#66).
        # _do_paste runs on the Qt thread, so creating the timer here is safe.
        QTimer.singleShot(int(delay_s * 1000), callback)

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
        restore_scheduler=_schedule_clipboard_restore,
        silence_timeout_s=float(config.behaviour.silence_timeout_s),
        max_recording_s=float(config.behaviour.max_recording_seconds),
        transform_lifecycle=transform_lifecycle,
        trigger_detector=trigger_detector,
        transform_enabled=config.transform.enabled,
        last_paste_ttl_s=float(config.transform.last_paste_ttl_s),
        transform_model_name=config.transform.model_name,
        transform_base_url=config.transform.base_url,
        llm_keep_alive_s=float(config.model.idle_unload_minutes * 60),
        latency_monitor=latency_monitor,
        autostart_registrar=autostart_registrar,
        persist_autostart=_persist_autostart,
    )

    tray_icon.on_start = daemon.on_tray_start_recording
    tray_icon.on_stop = daemon.on_tray_stop_recording
    tray_icon.on_preload = daemon.on_tray_preload
    tray_icon.on_unload = daemon.on_tray_unload
    tray_icon.on_autostart_toggled = daemon.on_tray_set_autostart
    tray_icon.set_autostart_checked(config.startup.autostart)
    tray_icon.on_quit = lambda: daemon.on_tray_quit(app.quit)

    classifier = HotkeyClassifier(
        tap_threshold_ms=config.hotkey.tap_threshold_ms,
        modifiers=config.hotkey.modifiers,
    )
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
        daemon.check_loading_overlay(now_ms=now)
        daemon.check_transcription_result(now_ms=now)
        daemon.check_transform_result(now_ms=now)

    tick_timer = QTimer()
    tick_timer.setInterval(50)
    tick_timer.timeout.connect(_on_tick)
    tick_timer.start()

    # Surface the session CPU fallback once, after the loop is up. A
    # QSystemTrayIcon balloon needs a visible icon and a running event loop, so
    # we defer it with a single-shot timer rather than firing it inline (#39).
    if did_fall_back:
        logger.warning(
            "Configured GPU (device=%s, model=%s, compute_type=%s) is "
            "unavailable on this machine — running on CPU "
            "(%s/%s/%s) for this session. The config file is unchanged.",
            config.model.device,
            config.model.name,
            config.model.compute_type,
            effective_model,
            effective_device,
            effective_compute_type,
        )
        QTimer.singleShot(
            2000,
            lambda: tray.show_notification(
                "Running on CPU",
                "Configured GPU (cuda) isn't available — running on CPU this "
                "session. Your config is unchanged; restore the GPU to use it "
                "again.",
            ),
        )

    logger.info("Dictatem daemon started")
    app.exec()
