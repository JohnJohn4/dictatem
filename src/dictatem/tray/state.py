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


class IconVariant(enum.Enum):
    Idle = "idle"
    Recording = "recording"
    Error = "error"


class MenuItem(enum.Enum):
    # Non-interactive header showing the activation hotkey (#104). Always
    # disabled; its label is set from config by the daemon, hidden where there
    # is no global-hotkey adapter. Kept first so it reads as a menu title.
    HOTKEY_HINT = "hotkey_hint"
    START = "start"
    STOP = "stop"
    PRELOAD = "preload"
    UNLOAD = "unload"
    # "Start at login" — a checkable toggle bound to config.startup.autostart.
    # Always enabled; its checked state is driven separately by the daemon, not
    # by TrayState (which tracks enable/disable only). See ADR-0012.
    AUTOSTART = "autostart"
    SHOW_LOG = "show_log"
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
    # Non-interactive footer showing the installed version, so the user can
    # confirm which build they're on (e.g. after an upgrade). Always disabled;
    # its label is set from importlib.metadata by the daemon.
    VERSION = "version"


@dataclass
class TrayState:
    is_recording: bool
    is_model_loaded: bool
    has_error: bool
    is_model_loading: bool = False

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
            # Non-interactive header/footer labels — always disabled.
            return False
        if item is MenuItem.STOP:
            return self.is_recording
        if item is MenuItem.UNLOAD:
            return self.is_model_loaded and not self.is_model_loading
        if item is MenuItem.PRELOAD:
            return not self.is_model_loaded and not self.is_model_loading
        return True
