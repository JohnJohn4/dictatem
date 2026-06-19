"""Protocol contracts for all OS-dependent operations.

Every module that touches OS surfaces depends on these Protocols, never on
concrete implementations.  Windows adapters implement them at runtime;
in-memory fakes implement them in tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.types import (
        AudioChunk,
        HardwareProfile,
        RecordingMode,
        TranscriptionResult,
    )


@runtime_checkable
class ClipboardIO(Protocol):
    """Read/write the system clipboard with save/restore support."""

    def open(self) -> None:
        """Acquire exclusive clipboard access. Raises ``OSError`` on contention.

        Adapters translate any native contention error (pywin32's
        ``pywintypes.error`` on Windows) into ``OSError`` so the pure pipeline's
        retry engages and stays testable with an ``OSError``-raising fake (#145).
        """
        ...

    def close(self) -> None:
        """Release exclusive clipboard access."""
        ...

    def save(self) -> str | None:
        """Save the current clipboard text content. Returns None if empty."""
        ...

    def set_text(self, text: str) -> None:
        """Place *text* on the clipboard."""
        ...

    def restore(self, saved: str | None) -> None:
        """Restore previously saved clipboard content.

        Like :meth:`open`, raises ``OSError`` on contention — the deferred restore
        races the target's paste handler, and the pipeline swallows it (#145/#23).
        """
        ...

    def copy(self, text: str) -> None:
        """Place *text* on the clipboard as a normal, persistent copy.

        Unlike the transient ``set_text``/``restore`` writes of the dictation
        paste path — which the clutter-proof write keeps out of Win+V history
        (ADR-0023 / #138) — this is an explicit user copy (the tray "Copy last
        dictation" item), so it is a *normal* copy that DOES appear in Win+V.
        Opens, replaces, and closes the clipboard in one call. See
        ``CONTEXT.md#most-recent-dictation``.
        """
        ...


@runtime_checkable
class KeystrokeSender(Protocol):
    """Simulate keyboard input to the foreground application."""

    def send_paste(self) -> None:
        """Send a Ctrl+V keystroke via the OS input system."""
        ...

    def send_backspaces(self, n: int) -> None:
        """Send *n* backspace keystrokes via the OS input system.

        Used by the Trigger Fire path to delete the Last Paste before
        typing the transformed text. See ``CONTEXT.md#trigger-fire``.
        """
        ...

    def send_text(self, text: str) -> None:
        """Type *text* directly via the OS input system, character-by-character.

        Used by the Trigger Fire path instead of clipboard+Ctrl+V: avoids
        racing the target window's paste handler over clipboard ownership
        (see #23) and leaves the user's clipboard untouched.
        """
        ...


@runtime_checkable
class ForegroundTracker(Protocol):
    """Track and restore the foreground identity (``target_id``).

    ``target_id`` is an opaque integer the Trigger Fire rail compares for
    equality — a window handle (HWND) on Windows, the frontmost-app PID on
    macOS (see ADR-0018 and ``CONTEXT.md#last-paste``).
    """

    def capture(self) -> int:
        """Return the current foreground identity (``target_id``)."""
        ...

    def restore(self, target_id: int) -> None:
        """Restore focus to the foreground identified by *target_id*."""
        ...


@runtime_checkable
class KeyboardHook(Protocol):
    """Low-level keyboard hook for hotkey detection.

    Adapters translate native OS key codes into platform-neutral ``Key``
    identities (see ``dictatem.hotkey.classifier.Key`` and ADR-0018) before
    delivering them, so the hotkey classifier never sees a raw OS key code.

    The key-event handler — a thread-safe ``Callable[[Key, KeyAction, int],
    None]`` receiving ``(key, action, timestamp_ms)`` — is injected through
    the adapter's constructor, not passed to ``install``: events arrive on a
    hook thread the adapter owns, so the handler must exist before the OS
    hook goes live. ``_PlatformAdapters.install_keyboard_hook`` in
    ``dictatem.daemon`` is the wiring seam that builds the adapter around
    the daemon's handler and installs it.
    """

    def install(self) -> None:
        """Install the OS hook; events flow to the constructor-injected handler."""
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
class HardwareProbe(Protocol):
    """Detect the machine's transcription-relevant hardware.

    Implementations inspect CUDA presence and VRAM and degrade gracefully to
    a CPU profile when neither is available. Consulted exactly once on first
    run; the resolved result is baked into the config (see ADR-0007).
    """

    def probe(self) -> HardwareProfile:
        """Return a snapshot of CUDA availability and total VRAM."""
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
class TransformBackend(Protocol):
    """Text-to-text Transform backend (e.g. a local LLM via Ollama).

    See ``CONTEXT.md#transform``.
    """

    def transform(self, text: str, system_prompt: str) -> str:
        """Apply *system_prompt* to *text* and return the rewritten text.

        Raises ``TransformFailedError`` for any failure (connection
        refused, timeout, non-200, malformed response, etc.).
        """
        ...

    def warm(self) -> bool:
        """Best-effort: load the model into memory so the next transform is
        instant. Returns False (not raises) on any failure, so a Preload that
        can't reach the backend simply skips it (see ``CONTEXT.md#transform``).
        """
        ...

    def is_model_available(self) -> bool:
        """Best-effort: whether the configured model is ready to serve. Returns
        False (not raises) when the backend is unreachable or the model is
        missing — used only to gate Preload."""
        ...


@runtime_checkable
class AutostartRegistrar(Protocol):
    """Register/unregister the daemon's OS autostart (start-at-login) entry.

    The daemon owns autostart and reconciles the OS entry to
    ``config.startup.autostart`` on launch (see ADR-0012). Implementations write
    the per-OS entry pointing at the installed ``dictatem`` launcher — on Windows
    the ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` key. The
    reconcile *decision* is pure (``autostart.reconcile``); this Protocol is only
    the I/O seam, with an in-memory fake in tests.
    """

    def enable(self) -> None:
        """Register the autostart entry. Idempotent — a no-op if present."""
        ...

    def disable(self) -> None:
        """Remove the autostart entry. Idempotent — a no-op if absent."""
        ...

    def is_enabled(self) -> bool:
        """Return whether the autostart entry currently exists."""
        ...


@runtime_checkable
class DaemonStopper(Protocol):
    """Terminate any running Dictatem daemon so the install dir unlocks (#69).

    ``dictatem --uninstall`` (and the tray Upgrade, #100) must stop the running
    daemon before ``uv tool uninstall``/``uv tool install`` touches the locked
    ``…\\uv\\tools\\dictatem\\Scripts`` directory, which Windows otherwise refuses
    with ``Access is denied``. The match *decision* is pure
    (``process.daemon_stop``); this Protocol is only the I/O seam — enumerate
    processes, terminate the path-matched ones, exclude the current process — with
    an in-memory fake in tests.
    """

    def stop_running_daemons(self) -> list[int]:
        """Terminate matching daemon processes best-effort; return stopped PIDs.

        Best-effort: a process that cannot be opened or terminated is skipped,
        never raised, so uninstall/upgrade always proceeds to its final step.
        """
        ...


@runtime_checkable
class OverlayRenderer(Protocol):
    """Render the on-screen recording/transcribing overlay pill."""

    def show(self, mode: RecordingMode) -> None:
        """Show the overlay in the given recording mode."""
        ...

    def show_loading(self, label: str = "Model Loading") -> None:
        """Show the overlay in the 'model loading' state — a "*label*…" pill with
        animated dots, shown while a transcription or Transform model loads, and
        during tray Preload. *label* names what is loading, e.g. "Loading Dict.
        Model", "Loading LLM Model", or "Preloading Models"."""
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

    def set_model_loaded(self, loaded: bool) -> None:
        """Update whether the transcription model is currently loaded.

        Used to enable/disable the Preload and Unload menu items.
        """
        ...

    def set_model_loading(self, loading: bool) -> None:
        """Update whether a model load is currently in progress.

        Used to disable Preload and Unload while a background load runs.
        """
        ...

    def set_has_last_dictation(self, has_last_dictation: bool) -> None:
        """Update whether a Most-recent dictation exists (ADR-0023 / #119).

        Enables the tray "Copy last dictation" item once the first dictation
        has been retained in the daemon's buffer.
        """
        ...

    def show_notification(self, title: str, message: str) -> None:
        """Display a tray balloon/notification."""
        ...
