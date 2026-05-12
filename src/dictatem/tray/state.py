"""Pure tray state logic — no Qt or OS imports."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class IconVariant(enum.Enum):
    Idle = "idle"
    Recording = "recording"
    Error = "error"


class MenuItem(enum.Enum):
    START = "start"
    STOP = "stop"
    PRELOAD = "preload"
    UNLOAD = "unload"
    SHOW_LOG = "show_log"
    RESTART = "restart"
    QUIT = "quit"


@dataclass
class TrayState:
    is_recording: bool
    is_model_loaded: bool
    has_error: bool
    is_model_loading: bool = False

    def current_icon_variant(self) -> IconVariant:
        if self.has_error:
            return IconVariant.Error
        if self.is_recording:
            return IconVariant.Recording
        return IconVariant.Idle

    def menu_item_enabled(self, item: MenuItem) -> bool:
        if item is MenuItem.STOP:
            return self.is_recording
        if item is MenuItem.UNLOAD:
            return self.is_model_loaded and not self.is_model_loading
        if item is MenuItem.PRELOAD:
            return not self.is_model_loaded and not self.is_model_loading
        return True
