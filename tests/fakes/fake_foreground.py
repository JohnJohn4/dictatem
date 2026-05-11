"""Fake foreground window tracker for testing paste pipeline logic."""

from __future__ import annotations


class FakeForegroundTracker:
    def __init__(self, hwnd: int = 1234) -> None:
        self._hwnd: int = hwnd
        self.captured: list[int] = []
        self.restored: list[int] = []

    def capture(self) -> int:
        self.captured.append(self._hwnd)
        return self._hwnd

    def restore(self, hwnd: int) -> None:
        self.restored.append(hwnd)
