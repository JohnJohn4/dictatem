"""Fake tray renderer for testing tray state logic."""

from __future__ import annotations


class FakeTrayRenderer:
    def __init__(self) -> None:
        self.state: str = "idle"
        self.model_loaded: bool = False
        self.model_loading: bool = False
        self.notifications: list[tuple[str, str]] = []

    def set_idle(self) -> None:
        self.state = "idle"

    def set_recording(self) -> None:
        self.state = "recording"

    def set_error(self) -> None:
        self.state = "error"

    def set_model_loaded(self, loaded: bool) -> None:
        self.model_loaded = loaded

    def set_model_loading(self, loading: bool) -> None:
        self.model_loading = loading

    def show_notification(self, title: str, message: str) -> None:
        self.notifications.append((title, message))
