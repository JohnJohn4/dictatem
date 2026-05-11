"""Protocol contracts for all OS-dependent operations.

Every module that touches OS surfaces depends on these Protocols, never on
concrete implementations.  Windows adapters implement them at runtime;
in-memory fakes implement them in tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.types import AudioChunk, RecordingMode, TranscriptionResult


@runtime_checkable
class ClipboardIO(Protocol):
    """Read/write the system clipboard with save/restore support."""

    def save(self) -> str | None:
        """Save the current clipboard text content. Returns None if empty."""
        ...

    def set_text(self, text: str) -> None:
        """Place *text* on the clipboard."""
        ...

    def restore(self, saved: str | None) -> None:
        """Restore previously saved clipboard content."""
        ...


@runtime_checkable
class KeystrokeSender(Protocol):
    """Simulate keyboard input to the foreground application."""

    def send_paste(self) -> None:
        """Send a Ctrl+V keystroke via the OS input system."""
        ...


@runtime_checkable
class ForegroundTracker(Protocol):
    """Track and restore the foreground window."""

    def capture(self) -> int:
        """Return a handle to the current foreground window."""
        ...

    def restore(self, hwnd: int) -> None:
        """Bring the window identified by *hwnd* to the foreground."""
        ...


@runtime_checkable
class KeyboardHook(Protocol):
    """Low-level keyboard hook for hotkey detection."""

    def install(self, callback: Callable[[int, bool], None]) -> None:
        """Install the hook. *callback(vk_code, is_down)* is called for each event."""
        ...

    def uninstall(self) -> None:
        """Remove the keyboard hook."""
        ...


@runtime_checkable
class AudioCapture(Protocol):
    """Capture audio from the microphone."""

    def start(self) -> None:
        """Begin capturing audio from the configured input device."""
        ...

    def stop(self) -> AudioChunk:
        """Stop capturing and return the accumulated audio as a single chunk."""
        ...


@runtime_checkable
class TranscriberBackend(Protocol):
    """Speech-to-text transcription backend."""

    def load_model(self) -> None:
        """Load the transcription model into memory (GPU/CPU)."""
        ...

    def unload_model(self) -> None:
        """Unload the model and free resources."""
        ...

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        """Transcribe an audio chunk and return the result."""
        ...

    def empty_cache(self) -> None:
        """Free GPU memory cache."""
        ...

    def set_progress_callback(
        self, callback: Callable[[int, int], None] | None
    ) -> None:
        """Register a callback for model download progress updates."""
        ...

    @property
    def is_loaded(self) -> bool:
        """Whether the model is currently loaded."""
        ...


@runtime_checkable
class OverlayRenderer(Protocol):
    """Render the on-screen recording/transcribing overlay pill."""

    def show(self, mode: RecordingMode) -> None:
        """Show the overlay in the given recording mode."""
        ...

    def update_level(self, level: float) -> None:
        """Update the displayed audio level (0.0–1.0)."""
        ...

    def show_transcribing(self) -> None:
        """Transition the overlay to the 'transcribing' visual state."""
        ...

    def show_error(self) -> None:
        """Flash the overlay to indicate an error (e.g. empty result)."""
        ...

    def hide(self) -> None:
        """Fade out and hide the overlay."""
        ...


@runtime_checkable
class TrayRenderer(Protocol):
    """Render the system-tray icon and menu."""

    def set_idle(self) -> None:
        """Set the tray icon to the idle state."""
        ...

    def set_recording(self) -> None:
        """Set the tray icon to the recording state."""
        ...

    def set_error(self) -> None:
        """Set the tray icon to the error state."""
        ...

    def show_notification(self, title: str, message: str) -> None:
        """Display a tray balloon/notification."""
        ...
