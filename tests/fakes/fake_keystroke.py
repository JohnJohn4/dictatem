"""Fake keystroke sender for testing paste pipeline logic."""

from __future__ import annotations


class FakeKeystrokeSender:
    def __init__(self) -> None:
        self.paste_count: int = 0
        self.backspace_counts: list[int] = []
        self.events: list[tuple[str, int]] = []

    def send_paste(self) -> None:
        self.paste_count += 1
        self.events.append(("paste", 1))

    def send_backspaces(self, n: int) -> None:
        self.backspace_counts.append(n)
        self.events.append(("backspaces", n))

    @property
    def total_backspaces(self) -> int:
        return sum(self.backspace_counts)
