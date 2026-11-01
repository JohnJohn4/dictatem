"""Fake keystroke sender for testing paste pipeline logic."""

from __future__ import annotations


class FakeKeystrokeSender:
    def __init__(self) -> None:
        self.paste_count: int = 0
        self.backspace_counts: list[int] = []
        self.typed_texts: list[str] = []
        self.events: list[tuple[str, object]] = []
        # Scripted modifier state (#269): each held_modifiers() poll pops the
        # next entry; the last entry sticks. Empty script = nothing ever held.
        self.held_script: list[frozenset[str]] = []
        self.held_polls: int = 0

    def held_modifiers(self) -> frozenset[str]:
        self.held_polls += 1
        if not self.held_script:
            return frozenset()
        if len(self.held_script) > 1:
            return self.held_script.pop(0)
        return self.held_script[0]

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
