"""Fake keystroke sender for testing paste pipeline logic."""

from __future__ import annotations


class FakeKeystrokeSender:
    def __init__(self) -> None:
        self.paste_count: int = 0
        self.backspace_counts: list[int] = []
        self.typed_texts: list[str] = []
        self.events: list[tuple[str, object]] = []

    def send_paste(self) -> None:
        self.paste_count += 1
        self.events.append(("paste", 1))

    def send_backspaces(self, n: int) -> None:
        self.backspace_counts.append(n)
        self.events.append(("backspaces", n))

    def send_text(self, text: str) -> None:
        self.typed_texts.append(text)
        self.events.append(("send_text", text))

    @property
    def total_backspaces(self) -> int:
        return sum(self.backspace_counts)
