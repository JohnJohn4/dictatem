"""Pure tray state logic — no Qt or OS imports."""

from __future__ import annotations

import enum
from dataclasses import dataclass


def glyph_tint_rgba(is_dark_background: bool) -> tuple[int, int, int, int]:
    """RGBA colour to repaint the brand glyph in, given the taskbar darkness.

    The tray glyph is rendered theme-adaptive monochrome so it stays visible on
    any taskbar (ADR-0006): a light glyph on a dark taskbar, a dark glyph on a
    light one. Always fully opaque — opacity comes from the glyph's own alpha
    mask, not from this colour.
    """
    channel = 255 if is_dark_background else 0
    return (channel, channel, channel, 255)


def uses_native_tray_menu(platform: str) -> bool:
    """Whether the tray menu is shown as an OS-native menu by our own code.

    Windows: yes. A ``TrackPopupMenuEx`` menu on left- or right-click behaves
    like every other notification-area app (the hidden-icons flyout stays open
    behind it, an outside click dismisses it). macOS: Qt's context menu
    already is the native status-item menu, opened on any click.
    """
    return platform == "win32"


class IconVariant(enum.Enum):
    Idle = "idle"
    Recording = "recording"
    Error = "error"


# The understated maker credit (#311): one line, no logo, no colour change.
MATAVEX_URL = "https://matavex.com"
MAKER_CREDIT = "free from Matavex"


def version_label(version: str) -> str:
    """The tray's version footer, e.g. ``Dictatem v0.8.3 — free from Matavex``.

    Empty when the version can't be read, which hides the footer.
    """
    return f"Dictatem v{version} — {MAKER_CREDIT}" if version else ""


class MenuItem(enum.Enum):
    # Non-interactive header showing the activation hotkey (#104). Always
    # disabled; its label is set from config by the daemon, hidden where there
    # is no global-hotkey adapter. Kept first so it reads as a menu title.
    HOTKEY_HINT = "hotkey_hint"
    # Manual Start/Stop recording. Shown only where there is no global hotkey
    # (then they're the only way to record); hidden otherwise, because clicking
    # the tray steals focus from the window the dictation should paste into.
    START = "start"
    STOP = "stop"
    # "Copy last dictation" — copies the Most-recent dictation to the clipboard
    # on demand (ADR-0023). A NORMAL copy (appears in Win+V); the recovery for a
    # dictation that landed nowhere when saying "paste" isn't convenient.
    # Disabled until a dictation exists (driven by TrayState.has_last_dictation).
    COPY_LAST_DICTATION = "copy_last_dictation"
    # "Unload model": free GPU/RAM now (e.g. before other AI work). There is no
    # "Preload model" item: the model loads on arm, and [startup] preload_model
    # covers an always-warm setup.
    UNLOAD = "unload"
    # "Microphone ▸": System default + each connected input; the choice is
    # saved to [audio] device. Shown only for the PortAudio (Windows) capture.
    MICROPHONE = "microphone"
    # "Start at login" — a checkable toggle bound to config.startup.autostart.
    # Always enabled; its checked state is driven separately by the daemon, not
    # by TrayState (which tracks enable/disable only). See ADR-0012.
    AUTOSTART = "autostart"
    SHOW_LOG = "show_log"
    # "Open config file…" — opens ~/.dictatem/config.toml in the OS default
    # editor (ADR-0022). Always enabled. Dictatem has no settings UI; this is the
    # discoverable escape hatch to the hand-edited config. Grouped next to
    # SHOW_LOG since both just open a file in the default app.
    OPEN_CONFIG = "open_config"
    # "How to use Dictatem…" — opens the read-only in-app Usage Guide window
    # (CONTEXT.md / ADR-0019). Always enabled; its content is set from live
    # config by the daemon via set_usage_guide_html. Grouped next to SHOW_LOG
    # since both open a separate surface rather than acting on recording.
    HELP = "help"
    RESTART = "restart"
    # "Check for Updates…" — resolves the latest GitHub release and, if newer,
    # re-runs the install one-liner at that tag (ADR-0011/0015). Always enabled.
    UPGRADE = "upgrade"
    QUIT = "quit"
    # Footer showing the installed version, so the user can confirm which build
    # they're on (e.g. after an upgrade), plus the understated "free from
    # Matavex" credit (#311). A non-interactive label — always disabled.
    # Its label comes from version_label(), fed from importlib.metadata.
    VERSION = "version"


@dataclass
class TrayState:
    is_recording: bool
    is_model_loaded: bool
    has_error: bool
    is_model_loading: bool = False
    # Whether a Most-recent dictation exists yet (ADR-0023 / #119). Gates the
    # "Copy last dictation" item; driven by the daemon, not derived here.
    has_last_dictation: bool = False

    def current_icon_variant(self) -> IconVariant:
        # Per ADR-0006 the Tray Icon no longer encodes recording state — the
        # tray renders the same theme-adaptive brand glyph for every variant.
        # This classifier is retained as the canonical mapping of TrayState to
        # a recording phase (still exercised by the daemon's tray-adapter tests)
        # but it no longer selects the tray glyph.
        if self.has_error:
            return IconVariant.Error
        if self.is_recording:
            return IconVariant.Recording
        return IconVariant.Idle

    def menu_item_enabled(self, item: MenuItem) -> bool:
        if item is MenuItem.HOTKEY_HINT or item is MenuItem.VERSION:
            # Non-interactive labels (header hint, version footer) — always disabled.
            return False
        if item is MenuItem.STOP:
            return self.is_recording
        if item is MenuItem.UNLOAD:
            return self.is_model_loaded and not self.is_model_loading
        if item is MenuItem.COPY_LAST_DICTATION:
            # Nothing to copy until the first dictation has been retained.
            return self.has_last_dictation
        return True
