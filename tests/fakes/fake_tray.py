"""Fake tray renderer for testing tray state logic."""

from __future__ import annotations


class FakeTrayRenderer:
    def __init__(self) -> None:
        self.state: str = "idle"
        self.notifications: list[tuple[str, str]] = []

    def set_idle(self) -> None:
        self.state = "idle"

    def set_recording(self) -> None:
        self.state = "recording"

    def set_error(self) -> None:
        self.state = "error"

    def show_notification(self, title: str, message: str) -> None:
        self.notifications.append((title, message))
