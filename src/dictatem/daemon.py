"""Daemon core — command dispatcher, error handling, and platform dispatch."""

from __future__ import annotations

import logging
import logging.handlers
import queue
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dictatem.exceptions import (
    AudioCaptureError,
    ModelLoadError,
    PlatformNotSupportedError,
    TranscriptionFailedError,
    TransformFailedError,
)

# HotkeyEvent is a pure, light enum used by _HotkeyBridge on the hot
# per-event/tick path, so it is imported eagerly rather than lazily under the
# bridge lock (the heavier classifier types stay TYPE_CHECKING-only below).
from dictatem.hotkey.classifier import HotkeyEvent
from dictatem.state import Command, Event, State
from dictatem.transform.detector import PASTE_ACTION, match_builtin_action
from dictatem.transform.last_paste import LastPaste
from dictatem.types import EmptyResult, RecordingMode

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from dictatem.audio.buffer import AudioBuffer
    from dictatem.hotkey.classifier import (
        HookDecision,
        HotkeyClassifier,
        Key,
        KeyAction,
    )
    from dictatem.interfaces import (
        AudioCapture,
        AutostartRegistrar,
        ClipboardIO,
        DaemonStopper,
        ForegroundTracker,
        HardwareProbe,
        KeystrokeSender,
        OverlayRenderer,
        TrayRenderer,
    )
    from dictatem.overlay.state import OverlayState
    from dictatem.permissions.mapper import PermissionGuidance
    from dictatem.state import StateMachine
    from dictatem.transcribe.latency_monitor import LatencyMonitor
    from dictatem.transcribe.lifecycle import TranscribeLifecycle
    from dictatem.transcribe.replacements import Replacement
    from dictatem.transform.detector import TriggerDetector
    from dictatem.transform.lifecycle import TransformLifecycle

logger = logging.getLogger(__name__)


def _add_rotating_log_file() -> logging.handlers.TimedRotatingFileHandler | None:
    """Attach a rotating file handler at the platform's daemon.log path.

    The daemon launches via a windowless gui-scripts entry point (ADR-0011),
    which has no console — so stderr-only logging is lost. Without this the
    "check the logs" error and the tray "Open log" menu both point at a file
    that is never written. Returns the handler so the caller can align its
    ``backupCount`` with ``config.logging.rotation_days`` once config loads,
    or ``None`` if the platform has no log path or the file could not be
    opened. Per-OS locations live in :func:`dictatem.logpaths.daemon_log_path`.
    """
    from dictatem.logpaths import default_daemon_log_path

    log_path = default_daemon_log_path()
    if log_path is None:
        return None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.TimedRotatingFileHandler(
            str(log_path),
            when="midnight",
            backupCount=7,
            encoding="utf-8",
        )
    except OSError:
        logger.warning(
            "Could not open log file under %s", log_path.parent, exc_info=True
        )
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

    The keyboard and mouse hooks each run on their own OS thread, but a mouse
    button can share one Hotkey Combo with keyboard modifiers (``ctrl+mouse4``,
    ADR-0020), so both must feed **one** classifier. The classifier is advanced
    *eagerly* on whichever hook thread delivered the event (under ``_lock``, so
    the two threads never mutate it concurrently) and the resulting state-machine
    work is *deferred* to a thread-safe queue. ``tick`` — driven by a Qt timer on
    the GUI thread — drains that queue and invokes the callback, so every Qt
    widget touch happens on the GUI thread. Keyboard timing is unchanged: the
    callback still fires on the tick, not on the hook thread.

    Why eager advancement: the mouse hook needs the suppress/pass-through
    decision *synchronously* (a low-level hook can only swallow an event from its
    proc on the hook thread). For ``ctrl+mouse4`` that decision depends on
    whether Ctrl is currently held, so the classifier must already reflect the
    keyboard state when the mouse event arrives — hence both hooks advance it the
    moment their event lands, not lazily on the next tick.
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
        self._lock = threading.Lock()
        # Deferred state-machine work, produced under ``_lock`` on hook threads
        # and drained on the GUI thread by ``tick`` — never touch Qt off-thread.
        self._actions: queue.Queue[tuple[Event, int]] = queue.Queue()

    def enqueue_key_event(
        self, key: Key, action: KeyAction, timestamp_ms: int
    ) -> None:
        """Thread-safe entry point invoked from the keyboard hook thread.

        Keyboard keys are never suppressed (the classifier's decision is ignored
        here, exactly as before), so this advances the classifier and defers the
        resulting state-machine work to the next ``tick``.
        """
        self._advance_and_defer(key, action, timestamp_ms)

    def process_mouse_event(
        self, key: Key, action: KeyAction, timestamp_ms: int
    ) -> HookDecision:
        """Thread-safe entry point invoked from the mouse hook thread.

        Returns the classifier's per-event ``HookDecision`` synchronously so the
        hook proc can swallow a trigger-button event (ADR-0020); the resulting
        state-machine work is deferred to the next ``tick`` like the keyboard.
        """
        return self._advance_and_defer(key, action, timestamp_ms)

    def _advance_and_defer(
        self, key: Key, action: KeyAction, timestamp_ms: int
    ) -> HookDecision:
        with self._lock:
            decision, actions = self._advance_locked(key, action, timestamp_ms)
            for sm_event in actions:
                self._actions.put(sm_event)
        return decision

    def on_key_event(
        self, key: Key, action: KeyAction, timestamp_ms: int
    ) -> HookDecision:
        """Advance the classifier and dispatch synchronously.

        The synchronous sibling of ``enqueue_key_event`` — used where the caller
        is already on the dispatch thread (the tests) — so it advances and fires
        the callback in one call rather than deferring to ``tick``.
        """
        with self._lock:
            decision, actions = self._advance_locked(key, action, timestamp_ms)
        for sm_event, ts in actions:
            self._callback(sm_event, now_ms=ts)
        return decision

    def _advance_locked(
        self, key: Key, action: KeyAction, timestamp_ms: int
    ) -> tuple[HookDecision, list[tuple[Event, int]]]:
        """Advance the classifier and return ``(decision, state-machine work)``.

        Pure bookkeeping — never calls the callback — so callers choose whether
        to dispatch now or defer. Must be called with ``_lock`` held.
        """
        decision, event = self._classifier.process_event(key, action, timestamp_ms)
        is_combo = self._classifier.combo_held
        actions: list[tuple[Event, int]] = []

        if not self._combo_active and is_combo:
            self._combo_active = True
            actions.append((Event.KEY_DOWN, timestamp_ms))

        if event is not None:
            actions.extend(self._event_to_actions(event, timestamp_ms))

        if self._combo_active and not is_combo and event is None:
            self._combo_active = False

        return decision, actions

    def tick(self, timestamp_ms: int) -> None:
        # Advance time for HOLD_START detection under the lock, then dispatch all
        # pending work on this (GUI) thread: the deferred input-driven actions
        # first (FIFO), then any HOLD action this tick produced.
        with self._lock:
            event = self._classifier.tick(timestamp_ms)
            hold_actions = self._event_to_actions(event, timestamp_ms)

        while True:
            try:
                sm_event, ts = self._actions.get_nowait()
            except queue.Empty:
                break
            self._callback(sm_event, now_ms=ts)

        for sm_event, ts in hold_actions:
            self._callback(sm_event, now_ms=ts)

    def _event_to_actions(
        self, event: HotkeyEvent | None, timestamp_ms: int
    ) -> list[tuple[Event, int]]:
        """Translate a classifier ``HotkeyEvent`` into state-machine work.

        Owns the ``_combo_active`` resets that used to live in ``_dispatch_event``
        so all of that state is mutated under ``_lock`` by the ``_advance_locked``
        / ``tick`` callers. Must be called with ``_lock`` held.
        """
        if event is HotkeyEvent.TAP:
            self._combo_active = False
            return [(Event.KEY_UP, timestamp_ms)]
        if event is HotkeyEvent.HOLD_START:
            return [(Event.TIMER_EXPIRED, timestamp_ms)]
        if event is HotkeyEvent.HOLD_END:
            self._combo_active = False
            return [(Event.KEY_UP, timestamp_ms)]
        if event is HotkeyEvent.ESC:
            self._combo_active = False
            return [(Event.ESC, timestamp_ms)]
        return []


class _TrayAdapter:
    """Bridges a QtTrayIcon to the TrayRenderer protocol."""

    def __init__(self, *, icon: object) -> None:
        self._icon = icon
        self._recording = False
        self._error = False
        self._model_loaded = False
        self._model_loading = False
        self._has_last_dictation = False

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

    def set_has_last_dictation(self, has_last_dictation: bool) -> None:
        if has_last_dictation == self._has_last_dictation:
            return
        self._has_last_dictation = has_last_dictation
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
                has_last_dictation=self._has_last_dictation,
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
        replacements: list[Replacement] | None = None,
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
        # --- Most-recent dictation buffer (ADR-0023 / #119) ---
        # The exact payload of the last REGULAR dictation (normalised, with
        # Replacements applied) — the text that was (or would have been) pasted.
        # Unlike _last_text (the transient pending-paste payload, nulled after
        # every paste) and Last Paste (needs a successful paste + target_id),
        # this is kept ACROSS pastes and even when the dictation landed nowhere,
        # so it carries no target_id and does not arm Trigger Words. It is what
        # the tray "Copy last dictation" item and the built-in `paste` Trigger
        # Word (#139) recover — the guarantee a dictation is never lost.
        self._most_recent_dictation: str | None = None
        # Built-in action words → their handlers (ADR-0023 / #139). Routed by
        # lookup, not an equality check, so adding a word to
        # BUILTIN_ACTION_WORDS without a handler fails loudly here (caught by
        # check_transcription_result's try/except) instead of silently falling
        # through to regular dictation.
        self._builtin_action_handlers: dict[str, Callable[..., None]] = {
            PASTE_ACTION: self._handle_paste_action,
        }
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
        # _awaiting_download_completion: a first-run model fetch (ADR-0025 /
        # #162) is in flight; the tick polls it to fire the "ready" tray
        # notification once (and only on success).
        self._awaiting_download_completion: bool = False
        self._llm_warming: bool = False
        self._llm_warm_thread: threading.Thread | None = None
        # Monotonic-ms deadline until which the LLM is presumed warm (#74).
        self._llm_warm_until_ms: int = 0
        # --- Replacements (deterministic find/replace, ADR-0024 / #125) ---
        # Applied to REGULAR dictation only, just before it becomes the text to
        # paste. Trigger Word utterances are intercepted before this point, so
        # they (and the Transform output) are never rewritten.
        self._replacements = replacements or []
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
            raise _AbortCommandChain from None
        self._overlay.show(RecordingMode.PTT)
        self._tray.set_recording()
        # Load-on-arm (ADR-0025 / #161): kick the Whisper load the instant
        # dictation is armed so the cold load overlaps the seconds the user
        # spends talking, not the dead air after the utterance. preload() is
        # idempotent (a no-op when the model is already resident or a load is
        # in flight) and returns immediately — the load runs on a background
        # thread — so this only ever starts the load EARLIER, never blocks
        # record-start. A cancel (Esc) leaves the in-flight load running to
        # completion (faster-whisper's load can't be cancelled — ADR-0016), and
        # idle-unload stays the sole reaper, so no extra VRAM is held when idle.
        # Guarded so a rare thread-spawn hiccup can't bubble to on_hotkey_event
        # and abort the recording already started above; the load then simply
        # falls back to lazy-load at transcribe.
        try:
            self._lifecycle.preload()
        except Exception:
            logger.error("Error starting load-on-arm preload", exc_info=True)

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
            # When the one-time first-run weights download is still in flight,
            # the load is waiting on it — show the distinct "Downloading model…"
            # caption rather than "Loading Dict. Model" (ADR-0025/-0016 family).
            label = (
                "Downloading model"
                if self._lifecycle.is_downloading
                else "Loading Dict. Model"
            )
            self._overlay.show_loading(label)
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

                # Built-in action words (today: `paste`) are matched BEFORE the
                # Transform alias map and run regardless of [transform].enabled
                # or any Last Paste — they are the recovery path (ADR-0023 /
                # #139). Detected before Replacements so a rule can't rewrite or
                # mask them, and before _detect_trigger so they bypass both of
                # its gates (transform-enabled + Last-Paste-exists).
                action = match_builtin_action(result)  # type: ignore[arg-type]
                if action is not None:
                    self._builtin_action_handlers[action](now_ms=now_ms)
                    return

                # Trigger Word detection — see CONTEXT.md#trigger-fire. Detect
                # BEFORE applying Replacements so a Replacement rule can never
                # rewrite (or mask) a Trigger Word; the trigger path is
                # intercepted here and bypasses find/replace entirely (#125).
                prompt = self._detect_trigger(result)  # type: ignore[arg-type]
                if prompt is None:
                    self._transcription_active = False
                    # Regular dictation only: apply deterministic Replacements
                    # (ADR-0024) just before this text becomes the paste payload.
                    text = self._apply_replacements(result)  # type: ignore[arg-type]
                    logger.info(
                        "Transcription complete (%d chars): %r",
                        len(text),
                        text[:80] + ("..." if len(text) > 80 else ""),
                    )
                    self._last_text = text
                    commands = self._sm.handle(Event.TRANSCRIPTION_DONE, now_ms=now_ms)
                    self._execute_commands(commands, now_ms=now_ms)
                else:
                    self._handle_trigger_fire(prompt, now_ms=now_ms)
        except Exception:
            logger.error("Unhandled error processing transcription result", exc_info=True)
            self._recover_to_idle()

    def _apply_replacements(self, text: str) -> str:
        """Apply deterministic Replacements to regular-dictation *text* (#125).

        A no-op when no rules are configured. Pure logic lives in
        ``transcribe.replacements``; this is the thin daemon seam. Only reached
        on the regular-dictation branch, so Trigger Words and Transform output
        are never touched.
        """
        if not self._replacements:
            return text
        from dictatem.transcribe.replacements import apply_replacements

        return apply_replacements(text, self._replacements)

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

    def _handle_paste_action(self, *, now_ms: int) -> None:
        """Re-paste the Most-recent dictation — the built-in ``paste`` recovery.

        The voice recovery for a dictation that landed nowhere (ADR-0023 /
        #139). Runs regardless of ``[transform].enabled`` and needs no Last
        Paste; it reads the Most-recent dictation buffer (#119), **not** Last
        Paste. An empty buffer flashes the existing overlay error and types
        nothing — it never falls back to typing the literal word "paste". The
        re-paste lands like a normal dictation (clipboard + Ctrl+V) and so
        becomes the new Last Paste, re-arming Trigger Words at the new spot.
        """
        self._transcription_active = False
        if self._most_recent_dictation is None:
            logger.info("`paste` action: no Most-recent dictation to recover")
            commands = self._sm.handle(Event.EMPTY_RESULT, now_ms=now_ms)
            self._execute_commands(commands, now_ms=now_ms)
            return
        logger.info(
            "`paste` action: re-pasting %d-char Most-recent dictation",
            len(self._most_recent_dictation),
        )
        # Route the buffer through the normal paste path. replace_chars stays 0
        # so it's a clipboard + Ctrl+V paste (not a typed Trigger-Fire
        # replacement), and _do_paste records the new Last Paste.
        self._last_text = self._most_recent_dictation
        self._pending_replace_chars = 0
        commands = self._sm.handle(Event.TRANSCRIPTION_DONE, now_ms=now_ms)
        self._execute_commands(commands, now_ms=now_ms)

    def _handle_trigger_fire(self, prompt: str, *, now_ms: int) -> None:
        """Run a Transform on the Last Paste; defer the SM event until it returns.

        Safety rails (foreground target + TTL) gate the call. On rail failure
        the transcription leg is closed with EMPTY_RESULT so the existing
        FLASH_ERROR path runs; the document is untouched.
        """
        assert self._last_paste is not None
        assert self._transform_lifecycle is not None

        current_target_id = (
            self._foreground.capture() if self._foreground is not None else 0
        )
        if not self._last_paste.rails_ok(
            current_target_id=current_target_id,
            now_ms=now_ms,
            ttl_s=self._last_paste_ttl_s,
        ):
            logger.info(
                "Trigger Fire aborted: rails failed "
                "(target_now=%s, target_paste=%s, age_ms=%d, ttl_s=%.0f)",
                current_target_id,
                self._last_paste.target_id,
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
            FailureReason.SERVER_ERROR: "Ollama Server Error",
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
                target_id=self._foreground.capture(),
                pasted_at_ms=now_ms,
            )
            # Retain regular dictation for voice/tray recovery (ADR-0023 / #119).
            # A Trigger Fire (replace > 0) pastes Transform output, not a
            # dictation, so it must NOT overwrite the Most-recent dictation.
            if replace == 0:
                self._most_recent_dictation = normalized
                self._tray.set_has_last_dictation(True)
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

    def on_tray_copy_last_dictation(self) -> None:
        """Copy the Most-recent dictation to the clipboard (ADR-0023 / #119).

        A NORMAL copy (it appears in Win+V) via ``ClipboardIO.copy`` — the user
        explicitly asked for the text on their clipboard, so it is not
        clutter-proofed like the automatic dictation juggling (#138). A no-op
        when there is no dictation yet (the tray item is disabled then anyway)
        or no clipboard adapter. Wrapped so a clipboard hiccup never crashes the
        daemon.
        """
        try:
            if self._most_recent_dictation is None or self._clipboard is None:
                return
            self._clipboard.copy(self._most_recent_dictation)
            logger.info(
                "Copied %d-char Most-recent dictation to the clipboard",
                len(self._most_recent_dictation),
            )
        except Exception:
            logger.error("Error copying last dictation", exc_info=True)

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

    def begin_first_run_model_fetch(self) -> None:
        """Kick the one-time, best-effort first-run model download (ADR-0025 / #162).

        Downloads the resolved tier's weights to the on-disk cache (NOT into
        VRAM) so the first *dictation* works offline, lifting the multi-GB
        download out of the dictation latency path. Announces it with a tray
        notification; if the user dictates while it runs, the pill shows a
        distinct "Downloading model…" caption. Best-effort and non-blocking: an
        offline/failed download is swallowed by the lifecycle and the model
        lazy-downloads on the first dictation instead. A no-op if a load (e.g.
        startup preload) is already pulling the weights.
        """
        try:
            if self._lifecycle.is_loaded or self._lifecycle.is_loading:
                return
            logger.info("First run — fetching the model to disk (one-time)")
            self._tray.show_notification(
                "Dictatem — one-time setup",
                "Downloading the speech model — a one-time background setup. "
                "Once it finishes, dictation works fully offline.",
            )
            # Await a completion notification only if the prefetch actually
            # started (it no-ops if a load already began pulling the weights),
            # so check_model_download never reports a download that didn't run.
            self._awaiting_download_completion = self._lifecycle.prefetch_to_disk()
        except Exception:
            logger.error("Error starting first-run model fetch", exc_info=True)

    def check_model_download(self) -> None:
        """Surface the one-time first-run model download finishing (#162).

        Polled on the tick. On a successful download a tray notification closes
        the loop; a failed/offline download stays quiet — the lifecycle already
        logged it and the model falls back to lazy-download on the first
        dictation, so there is nothing actionable to surface.
        """
        try:
            if (
                self._awaiting_download_completion
                and not self._lifecycle.is_downloading
            ):
                self._awaiting_download_completion = False
                if self._lifecycle.last_download_succeeded:
                    self._tray.show_notification(
                        "Dictatem — ready",
                        "Speech model downloaded. Dictation now works offline.",
                    )
        except Exception:
            logger.error("Error polling first-run model download", exc_info=True)

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

    With no arguments, starts the daemon — dispatching on ``sys.platform`` to
    the Windows or macOS adapter set (#54); unsupported platforms raise
    :class:`PlatformNotSupportedError`. ``--uninstall`` runs the cleanup that
    removes the daemon-owned autostart entry (and, on macOS, the generated
    ``.app``) and prints the final ``uv tool uninstall dictatem`` step (see
    ADR-0011); a bare tool uninstall would otherwise orphan those.
    ``--install-macos-app`` generates the ``Dictatem.app`` identity shell
    (#61 / ADR-0014) instead of starting the daemon.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="dictatem", description="Local voice-dictation daemon."
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the autostart entry, then print the uv tool uninstall step.",
    )
    parser.add_argument(
        "--install-macos-app",
        action="store_true",
        help="Generate ~/Applications/Dictatem.app — the stable identity that "
        "macOS permission grants bind to (macOS only).",
    )
    args = parser.parse_args(argv)

    if sys.platform not in ("win32", "darwin"):
        raise PlatformNotSupportedError(
            "Dictatem supports Windows and macOS. "
            f"Current platform: {sys.platform}"
        )

    if args.uninstall:
        _run_uninstall()
        return

    if args.install_macos_app:
        if sys.platform != "darwin":
            parser.error("--install-macos-app is only available on macOS")
        _run_install_macos_app()
        return

    if sys.platform == "win32":
        _start_windows_daemon()
    else:
        _start_macos_daemon()


def _run_uninstall() -> None:
    """Wire the platform registrar and run the uninstall cleanup (#58/#61).

    The gui-scripts launcher is windowless on Windows (ADR-0011), so console
    output is invisible — collect the cleanup's guidance and show it in a
    message box so the user sees the remaining ``uv tool uninstall dictatem``
    step. On macOS the cleanup also removes ``~/Applications/Dictatem.app``;
    both daemon-owned artifacts must go before the tool uninstall deletes the
    ``.app``'s exec-shim target. The README also documents the two-step
    uninstall as the canonical reference.
    """
    from dictatem.autostart.reconcile import run_uninstall

    remove_app: Callable[[], Path | None] | None = None
    if sys.platform == "darwin":
        from functools import partial

        from dictatem.macapp.bundle import default_app_bundle_path, remove_app_bundle

        remove_app = partial(remove_app_bundle, default_app_bundle_path())

    lines: list[str] = []
    try:
        run_uninstall(
            registrar=_platform_autostart_registrar(),
            out=lines.append,
            remove_app_bundle=remove_app,
        )
    except Exception:
        # A directory squatting on the plist path, a symlink where the .app
        # should be — cleanup must degrade to guidance, never to a traceback
        # that hides the remaining step.
        logger.error("Error during uninstall cleanup", exc_info=True)
        lines.append("Some cleanup failed — check the daemon log.")
        lines.append("You can still finish removing Dictatem with:")
        lines.append("    uv tool uninstall dictatem")

    # Stop the running daemon so step 2 (`uv tool uninstall`) isn't blocked by
    # the `…\Scripts` file lock (#69). Autostart was removed first (above, per
    # ADR-0012). Best-effort: failures are logged, never surfaced, so the
    # remaining-step guidance always shows.
    stopper = _platform_daemon_stopper()
    if stopper is not None:
        try:
            stopped = stopper.stop_running_daemons()
            if stopped:
                logger.info("Stopped running daemon process(es): %s", stopped)
        except Exception:
            logger.error("Failed to stop the running daemon during uninstall", exc_info=True)

    _show_uninstall_message("\n".join(lines))


def _run_install_macos_app() -> None:
    """Generate the ``Dictatem.app`` identity shell (#61 / ADR-0014).

    Thin darwin glue around the pure ``macapp.bundle`` machinery: resolve the
    uv-installed launcher for the exec shim (mirroring the win32 registrar's
    ``_launch_command``), stamp the installed version into the Info.plist, and
    report what happened. Unlike the windowless ``--uninstall`` this runs from
    a terminal (install.sh or the user), so plain stdout is the surface.
    """
    import shutil
    from importlib.metadata import PackageNotFoundError, version
    from pathlib import Path

    from dictatem.assets import asset_path
    from dictatem.autostart.launch_agent import default_agents_dir
    from dictatem.macapp.bundle import (
        default_apps_dir,
        install_app_bundle,
        resolve_launcher,
    )

    try:
        pkg_version: str | None = version("dictatem")
    except PackageNotFoundError:
        pkg_version = None

    launcher = resolve_launcher(shutil.which("dictatem"), home=Path.home())
    bundle, agent_refreshed = install_app_bundle(
        apps_dir=default_apps_dir(),
        agents_dir=default_agents_dir(),
        launcher=launcher,
        icns_source=asset_path("app.icns"),
        version=pkg_version,
    )
    print(f"Generated {bundle}")
    print(f"It launches the dictatem daemon at: {launcher}")
    if not launcher.exists():
        # The which() miss fell back to uv's default tool-bin path (see
        # resolve_launcher) — generation still succeeds, but be honest that
        # the shim's target isn't there yet rather than claiming a working app.
        print(
            "WARNING: that launcher does not exist yet (dictatem was not "
            "found on PATH). The app will not launch until the uv tool "
            "install puts it there — install it, then re-run "
            "`dictatem --install-macos-app`."
        )
    if agent_refreshed:
        print(
            "Refreshed the start-at-login LaunchAgent (launches the daemon "
            "directly)."
        )
    # The daemon must run under launchd, never via the .app (its status item is
    # suppressed when bundle-associated, #54) and never straight from a terminal
    # (macOS attributes its hotkey/paste permissions to the terminal, #56/#59).
    # install.sh starts it via launchctl; otherwise it starts at the next login.
    print(
        "Dictatem runs in the menu bar and starts at login. It must run under "
        "launchd — do not launch it straight from a terminal (its hotkey and "
        "paste permissions would be attributed to the terminal)."
    )


def _platform_autostart_registrar() -> AutostartRegistrar | None:
    """Build this platform's autostart registrar, or None where none exists.

    The single platform→registrar construction point, shared by ``--uninstall``
    and the daemon starters so they cannot drift (``--install-macos-app``'s
    LaunchAgent refresh builds the same launch command through
    ``macapp.bundle.launch_arguments``). On macOS the LaunchAgent launches the
    uv-installed daemon launcher **directly** — launching via the ``.app``
    makes the daemon inherit the bundle identity, which suppresses its menu-bar
    status item (#54, ADR-0012/0014 revised). It is built unconditionally —
    uninstall must be able to remove the LaunchAgent regardless.
    """
    if sys.platform == "win32":
        from dictatem.autostart.win32_registrar import Win32AutostartRegistrar

        return Win32AutostartRegistrar()
    if sys.platform == "darwin":
        import shutil
        from pathlib import Path

        from dictatem.autostart.launch_agent import (
            LaunchAgentRegistrar,
            default_agents_dir,
        )
        from dictatem.macapp.bundle import launch_arguments, resolve_launcher

        launcher = resolve_launcher(shutil.which("dictatem"), home=Path.home())
        return LaunchAgentRegistrar(
            agents_dir=default_agents_dir(),
            program_arguments=launch_arguments(launcher),
        )
    return None


def _platform_daemon_stopper() -> DaemonStopper | None:
    """Build this platform's daemon stopper, or None where none is needed.

    Windows is the only platform with the ``…\\Scripts`` file-lock problem the
    stopper solves (#69): the loaded interpreter blocks ``uv tool uninstall``.
    On macOS the daemon launches differently and uninstall is a separate flow, so
    there is no stopper to build (``None``) — uninstall there just prints its
    two-step guidance. Mirrors :func:`_platform_autostart_registrar`; the win32
    adapter is imported lazily so ``dictatem.daemon`` stays importable anywhere
    (``test_import_safety``).
    """
    if sys.platform == "win32":
        from dictatem.process.win32_stopper import Win32DaemonStopper

        return Win32DaemonStopper()
    return None


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


@dataclass(frozen=True)
class _PlatformAdapters:
    """The OS-specific seam for the daemon wiring (#54 / ADR-0018).

    Everything else in :func:`_run_daemon` is platform-neutral (Qt tray and
    overlay, sounddevice capture, faster-whisper, Ollama). Each
    ``_start_*_daemon`` builds this set with lazy imports so the daemon module
    stays importable on any OS (``test_import_safety``).

    A ``None`` field means the platform has no such adapter — absent, not
    faked: DaemonCore's existing None-tolerant paths handle it honestly (the
    paste path logs "Paste skipped" and records no Last Paste; the autostart
    reconcile is skipped and the tray hides the toggle). On macOS the
    LaunchAgent registrar is ``None`` until the user generates the ``.app``
    it launches (``--install-macos-app``, #61).

    ``install_keyboard_hook`` receives the thread-safe key-event handler,
    installs the platform hook, and returns it (the caller keeps it alive for
    the lifetime of the event loop). ``None`` means the platform has no
    global-hotkey adapter — recording then runs from the tray menu only.

    ``install_mouse_hook`` is its mouse counterpart (ADR-0020): it receives the
    thread-safe mouse-event handler — which, unlike the keyboard handler, returns
    a ``HookDecision`` so the hook can suppress a trigger button — installs the
    platform mouse hook, and returns it. It feeds the *same* classifier as the
    keyboard hook so a mouse button can share a combo with modifiers. ``None``
    means the platform has no mouse-trigger adapter yet (macOS: #121).

    ``check_permissions`` probes the platform's manually-granted permissions
    once at startup and returns the guidance to show (#57 / ADR-0014) — empty
    means all granted, show nothing. ``None`` means the platform has no guided
    permission UX (Windows: the mic permission surfaces in-flow when capture
    fails).
    """

    probe: HardwareProbe
    autostart_registrar: AutostartRegistrar | None
    clipboard: ClipboardIO | None
    keystroke: KeystrokeSender | None
    foreground: ForegroundTracker | None
    install_keyboard_hook: (
        Callable[[Callable[[Key, KeyAction, int], None]], object] | None
    )
    install_mouse_hook: (
        Callable[[Callable[[Key, KeyAction, int], HookDecision]], object] | None
    )
    check_permissions: Callable[[], tuple[PermissionGuidance, ...]] | None


def _acquire_single_instance_lock(lock_path: Path) -> object | None:
    """Acquire the cross-platform single-instance lock (#92).

    Returns a lock object the caller must keep alive for the whole process, or
    ``None`` when another *live* Dictatem daemon already holds the lock (the
    caller then exits). Backed by ``QtCore.QLockFile`` so Windows and macOS
    share one guard — the Win32-only alternative (a named ``CreateMutexW``
    mutex) would split the code path. A garbage-collected ``QLockFile`` releases
    the lock and silently drops the guard, hence the keep-alive contract.

    A daemon killed hard (kill -9) leaves its lock file behind, but ``QLockFile``
    records the creating PID and steals a lock whose owner is no longer running,
    so a fresh start never deadlocks on a stale lock.

    **Best-effort, like the clipboard markers (ADR-0023): the guard must never be
    the reason the daemon fails to start.** If the lock file cannot be
    *established* at all — ``~/.dictatem`` is unwritable, or sits on a network/
    redirected home that is offline — log it and return a (non-held) lock so the
    daemon starts anyway. That is no worse than the pre-#92 no-guard behaviour,
    and avoids #92 newly turning a lock-file IO error into a confusing silent
    "already running" exit. ``None`` is reserved for a genuine ``LockFailedError``
    (the lock is held by a process that is currently alive).

    Known limitation: ``QLockFile`` decides "held" from the recorded PID, so if a
    hard-killed daemon's PID is reused by an unrelated live process the lock looks
    held and a fresh start is refused until that process exits (or the lock file
    is deleted). Defeating that needs more than ``QLockFile`` offers; accepted as
    a rare edge — the common relaunch path (the installer's ``Stop-DictatemDaemon``
    / #98) stops the old daemon first, leaving no stale lock.

    The import stays lazy so ``dictatem.daemon`` imports with no Qt present
    (``test_import_safety``).
    """
    from PySide6.QtCore import QLockFile  # type: ignore[import-not-found]

    lock = QLockFile(str(lock_path))
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Try once without blocking: a redundant instance must fail fast and
        # exit, not queue up waiting for the live daemon to release the lock.
        if lock.tryLock(0):
            return lock
        if lock.error() == QLockFile.LockError.LockFailedError:
            return None  # genuinely held by a live daemon — the caller exits
    except OSError:
        logger.warning(
            "Could not prepare the single-instance lock at %s; starting without "
            "the guard",
            lock_path,
            exc_info=True,
        )
        return lock
    # tryLock failed for a reason other than contention (a permission/IO error on
    # the lock file itself): degrade to running without the guard rather than
    # block startup. Returning the un-held lock keeps the contract simple
    # (non-None ⇒ proceed) and holding the object is harmless.
    logger.warning(
        "Single-instance lock unavailable (error=%s); starting without the guard",
        lock.error(),
    )
    return lock


def _run_daemon(adapters: _PlatformAdapters) -> None:
    """Wire the platform-neutral daemon around *adapters* and run the Qt loop.

    Everything here is OS-independent: config load + Hardware Tier baking, the
    Qt tray/overlay, sounddevice capture, the faster-whisper and Ollama
    backends, DaemonCore, and the timers. The OS-specific pieces arrive
    pre-built in *adapters* (see :class:`_PlatformAdapters`); heavy imports
    stay lazy so importing ``dictatem.daemon`` pulls in no GUI/audio/ML
    dependency.
    """
    import time
    from pathlib import Path

    from PySide6.QtCore import QTimer  # type: ignore[import-not-found]
    from PySide6.QtWidgets import QApplication  # type: ignore[import-not-found]

    from dictatem.audio.sounddevice_capture import SoundDeviceCapture
    from dictatem.autostart.reconcile import apply_autostart
    from dictatem.config import default_config_path, load_config, write_config
    from dictatem.hotkey.classifier import HotkeyClassifier
    from dictatem.onboarding import (
        mark_usage_guide_seen,
        should_auto_open_usage_guide,
        usage_guide_seen_marker,
    )
    from dictatem.overlay.qt_widget import QtOverlayWidget
    from dictatem.overlay.state import OverlayState
    from dictatem.state import StateMachine
    from dictatem.transcribe.faster_whisper_backend import FasterWhisperBackend
    from dictatem.transcribe.latency_monitor import LatencyMonitor
    from dictatem.transcribe.lifecycle import TranscribeLifecycle
    from dictatem.transcribe.replacements import (
        bootstrap_replacements,
        load_replacements,
    )
    from dictatem.transcribe.vocabulary import (
        bootstrap_vocabulary,
        load_vocabulary,
    )
    from dictatem.transform.detector import (
        TriggerDetector,
        shadowed_builtin_aliases,
    )
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

    # Single-instance guard (#92). Two concurrent daemons each register the
    # global hotkey hook, so every gesture is recorded, transcribed, and pasted
    # twice (the most likely trigger is an upgrade relaunch while the old tray
    # instance is still alive; a dev clone next to the installed build does it
    # too). Acquire the lock BEFORE any hook, audio, model, or tray setup so a
    # redundant instance exits cleanly here, leaving the live daemon untouched.
    # ``_instance_lock`` is intentionally bound for the whole function: it must
    # outlive setup (app.exec() below holds it until the process exits), and
    # releasing the QLockFile would drop the guard.
    _instance_lock = _acquire_single_instance_lock(
        Path.home() / ".dictatem" / "daemon.lock"
    )
    if _instance_lock is None:
        logger.warning("Another Dictatem instance is already running; exiting")
        return

    config_path = default_config_path()
    # First run with no config: probe the machine once and bake the resolved
    # Hardware Tier (model/device/compute_type + transform tag) into the file.
    # Existing configs are read unchanged and the probe is not consulted.
    # Capture "is this a first run?" BEFORE load_config writes the file — it is
    # the signal to fetch the model to disk so the first dictation works offline
    # (ADR-0025 / #162), the run the installer triggers as its last step.
    is_first_run = not config_path.exists()
    probe = adapters.probe
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
    # flag is the single source of truth: register the OS entry (the HKCU Run
    # key on Windows) when the flag is on and it's missing, remove it when the
    # flag is off and it's present. apply_autostart runs the pure decision and
    # applies it via the registrar adapter; the tray "Start at login" toggle
    # flips the same flag. Platforms with no registrar yet (macOS until #61)
    # skip the reconcile, and the tray hides the toggle below.
    autostart_registrar = adapters.autostart_registrar
    if autostart_registrar is not None:
        try:
            apply_autostart(
                desired=config.startup.autostart, registrar=autostart_registrar
            )
        except Exception:
            # A reconcile hiccup — a registry error, EACCES out of
            # Path.is_file (pre-3.13), a directory squatting on the plist
            # path — must never kill startup; the tray toggle path is wrapped
            # the same way.
            logger.error("Error reconciling autostart on launch", exc_info=True)

    app = QApplication(sys.argv)
    # The daemon is a tray app with no persistent main window: the overlay pill
    # and the guided permission dialogs are transient. Without this, Qt's
    # default quits the whole daemon when the last window closes — on macOS,
    # closing the first-run permission dialog killed the daemon (and its
    # menu-bar icon) outright (#57 QA). Tray/hotkey keep it alive instead.
    app.setQuitOnLastWindowClosed(False)

    if sys.platform == "darwin":
        # Make the running process a menu-bar accessory: the .app's LSUIElement
        # does not apply because the daemon runs as the interpreter the shim
        # execs into, not as the bundle (#61). Without this, a Dock icon shows
        # and the status item does not register. Lazy import — the module binds
        # AppKit and is macOS-only.
        from dictatem.macapp.activation import set_accessory_activation_policy

        set_accessory_activation_policy()

    audio_capture = SoundDeviceCapture(config)

    # Vocabulary + Replacements live in their own line-based files under
    # ~/.dictatem (ADR-0024), bootstrapped on first run with opt-in/commented
    # defaults. Vocabulary biases recognition BEFORE text exists; Replacements
    # rewrite regular dictation AFTER transcription (Trigger Words excluded).
    dictatem_dir = Path.home() / ".dictatem"
    bootstrap_vocabulary(dictatem_dir / "vocabulary.md")
    bootstrap_replacements(dictatem_dir / "replacements.md")
    vocabulary = load_vocabulary(dictatem_dir / "vocabulary.md")
    replacements = load_replacements(dictatem_dir / "replacements.md")

    backend = FasterWhisperBackend(
        model_name=effective_model,
        compute_type=effective_compute_type,
        device=effective_device,
        language=config.model.language,
        vad_filter=config.model.vad_filter,
        vocabulary=vocabulary,
    )
    lifecycle = TranscribeLifecycle(
        backend=backend,
        idle_timeout_s=config.model.idle_unload_minutes * 60,
        min_transcription_chars=config.model.min_transcription_chars,
    )

    clipboard = adapters.clipboard
    keystroke = adapters.keystroke
    foreground = adapters.foreground

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
    prompt_aliases = load_prompts_dir(prompts_dir)
    # A user Prompt File that reuses a built-in action name (`paste`) is
    # shadowed by the built-in — its Transform can never fire (ADR-0023 / #139).
    # Warn so the collision is visible rather than silently dead.
    shadowed = shadowed_builtin_aliases(prompt_aliases)
    if shadowed:
        logger.warning(
            "Prompt File alias(es) %s are shadowed by the built-in `paste` "
            "action and will never fire as a Transform — rename them in %s",
            ", ".join(shadowed),
            prompts_dir,
        )
    trigger_detector = TriggerDetector(prompt_aliases)

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
        replacements=replacements,
    )

    tray_icon.on_start = daemon.on_tray_start_recording
    tray_icon.on_stop = daemon.on_tray_stop_recording
    tray_icon.on_copy_last_dictation = daemon.on_tray_copy_last_dictation
    tray_icon.on_preload = daemon.on_tray_preload
    tray_icon.on_unload = daemon.on_tray_unload
    tray_icon.on_autostart_toggled = daemon.on_tray_set_autostart
    tray_icon.set_autostart_checked(config.startup.autostart)
    # A visible toggle backed by no registrar would show a checkmark that the
    # OS never honors — hide it until the platform has one (macOS: #61).
    tray_icon.set_autostart_available(autostart_registrar is not None)
    tray_icon.on_quit = lambda: daemon.on_tray_quit(app.quit)

    # Tray "Check for Updates…" (#100). Resolve the latest GitHub release off the
    # UI thread and, if newer, re-run the install one-liner at that tag — which
    # stops the daemon, picks the right GPU/CPU extra, installs, and relaunches
    # (ADR-0011/0015; the same verified upgrade path as #98), not a bundled
    # updater. Kept alive for the event loop's lifetime, like the hook below.
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _installed_version

    from dictatem.upgrade.core import GITHUB_REPO
    from dictatem.upgrade.github import fetch_latest_tag
    from dictatem.upgrade.qt_update_check import UpdateChecker

    def _current_version() -> str:
        try:
            return _installed_version("dictatem")
        except PackageNotFoundError:
            return ""

    def _start_upgrade(tag: str) -> None:
        if sys.platform == "win32":
            from dictatem.upgrade.win32_upgrader import spawn_upgrade

            spawn_upgrade(tag)
        else:
            # No Windows `…\Scripts` file lock to dance around off-win32; the
            # in-app upgrade is Windows-only until a macOS installer path lands.
            logger.info("In-app upgrade is Windows-only for now; tag=%s", tag)

    _update_checker = UpdateChecker(
        current_version=_current_version(),
        fetch_latest_tag=lambda: fetch_latest_tag(repo=GITHUB_REPO),
        notify=tray_icon.show_notification,
        start_upgrade=_start_upgrade,
    )
    tray_icon.on_upgrade = _update_checker.check
    # In-app upgrade re-runs install.ps1 (Windows-only). Hide the item elsewhere
    # so it never promises a restart it can't deliver (_start_upgrade no-ops).
    tray_icon.set_upgrade_available(sys.platform == "win32")
    # Footer showing the installed version, so the user can confirm which build
    # they're on (e.g. after an upgrade). Hidden if the version can't be read.
    _ver = _current_version()
    tray_icon.set_version_label(f"Dictatem v{_ver}" if _ver else "")

    # Usage Guide (ADR-0019): build the read-only help content from live config
    # so the "How to use Dictatem…" item reflects the actual activation chord.
    from dictatem.tray.usage_guide import usage_guide_html

    tray_icon.set_usage_guide_html(
        usage_guide_html(
            config.hotkey.modifiers,
            platform=sys.platform,
            trigger_words=sorted(prompt_aliases),
        )
    )

    bridge: _HotkeyBridge | None = None
    if adapters.install_keyboard_hook is not None:
        classifier = HotkeyClassifier(
            tap_threshold_ms=config.hotkey.tap_threshold_ms,
            modifiers=config.hotkey.modifiers,
        )
        classifier.set_active(True)
        bridge = _HotkeyBridge(classifier=classifier, callback=daemon.on_hotkey_event)
        # The returned hook(s) must outlive this scope (on Windows their ctypes
        # callbacks would otherwise be collected); app.exec() below keeps the
        # references alive until the daemon exits.
        _hook = adapters.install_keyboard_hook(bridge.enqueue_key_event)
        # The mouse hook (ADR-0020) feeds the SAME bridge/classifier so a mouse
        # button can complete a combo alongside keyboard modifiers; it returns a
        # HookDecision so the hook can suppress a trigger button.
        if adapters.install_mouse_hook is not None:
            _mouse_hook = adapters.install_mouse_hook(bridge.process_mouse_event)
        # Tell the user what to press, derived from the live config and formatted
        # for this platform (#104). Only when a hook is live — advertising a
        # hotkey the platform can't fire would mislead.
        from dictatem.tray.hotkey_hint import hotkey_hint_label

        tray_icon.set_hotkey_hint(
            hotkey_hint_label(config.hotkey.modifiers, platform=sys.platform)
        )
    else:
        # No global-hotkey adapter on this platform yet (macOS: #56). Recording
        # runs from the tray menu, so no classifier/bridge machinery is built and
        # the hotkey hint stays hidden.
        logger.info("No global-hotkey adapter on this platform — use the tray menu")

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

    # First-run model fetch (ADR-0025 / #162): on the daemon's first run — the
    # run the installer triggers, right after tier resolution, while the network
    # is still up — download the resolved tier's weights to disk so the first
    # *dictation* works offline. Deferred like the balloons below so the tray
    # icon + event loop are up first (a QSystemTrayIcon notification needs a
    # running loop). Best-effort and non-blocking; the daemon never waits on it.
    if is_first_run:
        QTimer.singleShot(2500, daemon.begin_first_run_model_fetch)

    def _on_tick() -> None:
        now = int(time.monotonic() * 1000)
        if bridge is not None:
            bridge.tick(now)
        overlay.update_level(audio_capture._buffer.current_level())
        daemon.check_loading_overlay(now_ms=now)
        daemon.check_model_download()
        daemon.check_transcription_result(now_ms=now)
        daemon.check_transform_result(now_ms=now)

    tick_timer = QTimer()
    tick_timer.setInterval(50)
    tick_timer.timeout.connect(_on_tick)
    tick_timer.start()

    # First-run onboarding (#122 / ADR-0021): auto-open the Usage Guide once so
    # a new user meets it without hunting through the tray menu. Gated by a
    # sentinel marker — never a config flag, since config.toml is never
    # app-rewritten (ADR-0009/0022) — written only AFTER the guide is shown, so a
    # launch that defers it (mid macOS permission flow) re-attempts next time.
    _guide_marker = usage_guide_seen_marker(Path.home())

    def _maybe_auto_open_usage_guide(*, permissions_pending: bool) -> None:
        try:
            if not should_auto_open_usage_guide(
                marker_path=_guide_marker, permissions_pending=permissions_pending
            ):
                return
            if tray_icon.open_usage_guide():
                mark_usage_guide_seen(_guide_marker)
                logger.info("First run — auto-opened the Usage Guide")
        except Exception:
            logger.error("Error auto-opening the Usage Guide", exc_info=True)

    # First-run permission UX (#57 / ADR-0014), deferred like the CPU-fallback
    # balloon below so the tray and event loop are up first. One probe per
    # launch: the platform callable reads the grant state, registers Dictatem
    # in the System Settings panes for anything missing, and returns the pure
    # mapper's guidance; the Qt dialogs then deep-link the user into the right
    # pane and explain the one-time relaunch. Empty guidance = no dialog. The
    # Usage Guide auto-open chains off it: deferred while a grant is still
    # pending (the daemon relaunches on grant), shown once permissions settle.
    if adapters.check_permissions is not None:
        check_permissions = adapters.check_permissions

        def _show_permission_guidance() -> None:
            permissions_pending = False
            try:
                guidances = check_permissions()
                if guidances:
                    permissions_pending = True
                    from dictatem.permissions.qt_dialog import show_permission_dialogs

                    show_permission_dialogs(guidances)
            except Exception:
                logger.error("Error in startup permission check", exc_info=True)
            finally:
                _maybe_auto_open_usage_guide(permissions_pending=permissions_pending)

        QTimer.singleShot(2000, _show_permission_guidance)
    else:
        # No first-run permission flow on this platform (Windows): auto-open the
        # guide shortly after the tray is up, on the same deferred tick.
        QTimer.singleShot(
            2000, lambda: _maybe_auto_open_usage_guide(permissions_pending=False)
        )

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


def _start_windows_daemon() -> None:
    """Build the Windows adapter set (lazy imports) and run the daemon."""
    from dictatem.hardware.nvidia_probe import NvidiaHardwareProbe
    from dictatem.hotkey.wh_keyboard_ll import WHKeyboardLLHook
    from dictatem.hotkey.wh_mouse_ll import WHMouseLLHook
    from dictatem.paste.win32_clipboard import Win32ClipboardIO
    from dictatem.paste.win32_foreground import Win32ForegroundTracker
    from dictatem.paste.win32_keystroke import Win32KeystrokeSender

    def _install_hook(handler: Callable[[Key, KeyAction, int], None]) -> object:
        hook = WHKeyboardLLHook(handler)
        hook.install()
        return hook

    def _install_mouse_hook(
        handler: Callable[[Key, KeyAction, int], HookDecision],
    ) -> object:
        hook = WHMouseLLHook(handler)
        hook.install()
        return hook

    _run_daemon(
        _PlatformAdapters(
            probe=NvidiaHardwareProbe(),
            autostart_registrar=_platform_autostart_registrar(),
            clipboard=Win32ClipboardIO(),
            keystroke=Win32KeystrokeSender(),
            foreground=Win32ForegroundTracker(),
            install_keyboard_hook=_install_hook,
            install_mouse_hook=_install_mouse_hook,
            check_permissions=None,
        )
    )


def _start_macos_daemon() -> None:
    """Build the macOS adapter set (lazy imports) and run the daemon (#54).

    Reuses every platform-neutral layer — Qt tray/overlay, sounddevice
    (CoreAudio) capture, the CPU faster-whisper backend (ADR-0013), the Ollama
    Transform. The native adapters: CGEventTap global hotkey (#56),
    NSPasteboard/CGEvent/NSWorkspace paste (#59), the CGPreflight permission
    check (#57), and the LaunchAgent autostart registrar (#61) — manual-QA
    only, like their win32 counterparts. MacHardwareProbe reports no CUDA, so
    first run bakes the CPU tier into the config.

    This body executes on the headless macOS CI leg (TestStarterAdapterSets):
    everything here must stay construction-only — no native call happens until
    the daemon actually runs.
    """
    from dictatem.hardware.mac_probe import MacHardwareProbe
    from dictatem.hotkey.mac_hook import CGEventTapHook
    from dictatem.macapp.bundle import default_app_bundle_path
    from dictatem.paste.mac_clipboard import MacClipboardIO
    from dictatem.paste.mac_foreground import MacForegroundTracker
    from dictatem.paste.mac_keystroke import MacKeystrokeSender
    from dictatem.permissions.mac_tcc import check_permissions

    def _install_hook(handler: Callable[[Key, KeyAction, int], None]) -> object:
        hook = CGEventTapHook(handler)
        hook.install()
        return hook

    # Autostart can only launch the generated .app — the identity TCC trusts
    # (ADR-0014). With no .app the registrar is kept only when a LaunchAgent
    # is already on disk, so a stale entry left behind after the user
    # hand-deleted the .app can still be reconciled away (flag off) or
    # toggled off — reconcile never ENABLEs over an existing plist, so this
    # can never *register* an entry pointing at a missing bundle. With
    # neither present the registrar stays absent (reconcile skipped, tray
    # toggle hidden) rather than faked. --uninstall deliberately skips this
    # guard.
    app_bundle = default_app_bundle_path()
    autostart_registrar: AutostartRegistrar | None = _platform_autostart_registrar()
    if not app_bundle.exists():
        try:
            has_stale_agent = (
                autostart_registrar is not None
                and autostart_registrar.is_enabled()
            )
        except OSError:
            has_stale_agent = False
        if has_stale_agent:
            logger.warning(
                "%s is missing but its start-at-login LaunchAgent is still "
                "registered — run `dictatem --install-macos-app` to "
                "regenerate the app, or turn off Start at login to remove "
                "the entry",
                app_bundle,
            )
        else:
            autostart_registrar = None
            logger.info(
                "No %s — run `dictatem --install-macos-app` to enable "
                "start-at-login and give permission grants a stable identity",
                app_bundle,
            )

    _run_daemon(
        _PlatformAdapters(
            probe=MacHardwareProbe(),
            autostart_registrar=autostart_registrar,
            clipboard=MacClipboardIO(),
            keystroke=MacKeystrokeSender(),
            foreground=MacForegroundTracker(),
            install_keyboard_hook=_install_hook,
            # macOS mouse-trigger hook (CGEventTap otherMouse*) is #121 (S9).
            install_mouse_hook=None,
            check_permissions=check_permissions,
        )
    )
