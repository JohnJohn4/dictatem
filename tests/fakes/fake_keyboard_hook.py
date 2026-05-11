"""Fake keyboard hook for testing hotkey classification logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeKeyboardHook:
    def __init__(self) -> None:
        self._callback: Callable[[int, bool], None] | None = None
        self.installed: bool = False

    def install(self, callback: Callable[[int, bool], None]) -> None:
        self._callback = callback
        self.installed = True

    def uninstall(self) -> None:
        self._callback = None
        self.installed = False

    def simulate_event(self, vk_code: int, is_down: bool) -> None:
        """Test helper: inject a keyboard event."""
        if self._callback is not None:
            self._callback(vk_code, is_down)
