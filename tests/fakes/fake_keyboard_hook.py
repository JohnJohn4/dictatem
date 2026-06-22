"""Fake keyboard hook for testing hotkey classification logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.hotkey.classifier import Key, KeyAction


class FakeKeyboardHook:
    """In-memory ``KeyboardHook``: the key-event handler is constructor-injected,
    matching the production hooks; ``simulate_event`` plays the hook thread."""

    def __init__(self, on_key_event: Callable[[Key, KeyAction, int], bool]) -> None:
        self._on_key_event = on_key_event
        self.installed: bool = False

    def install(self) -> None:
        self.installed = True

    def uninstall(self) -> None:
        self.installed = False

    def simulate_event(self, key: Key, action: KeyAction, timestamp_ms: int) -> None:
        """Test helper: deliver a key event the way the hook thread would.

        Silent unless installed — a real OS hook delivers nothing before
        ``install`` or after ``uninstall``.
        """
        if self.installed:
            self._on_key_event(key, action, timestamp_ms)
