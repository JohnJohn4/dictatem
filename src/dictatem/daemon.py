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
from dictatem.types import EmptyResult

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
    from dictatem.state import StateMachine
    from dictatem.transcribe.lifecycle import TranscribeLifecycle

logger = logging.getLogger(__name__)


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
            pass

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
        self._last_text = None

    def _do_cancel(self) -> None:
        self._overlay.hide()
        self._last_text = None

    def _recover_to_idle(self) -> None:
        self._sm._state = State.IDLE
        self._overlay.hide()
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
