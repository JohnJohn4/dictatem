"""Fake clipboard for testing paste pipeline logic."""

from __future__ import annotations


class FakeClipboardIO:
    def __init__(self) -> None:
        self._content: str | None = None
        self.calls: list[tuple[str, ...]] = []

    def save(self) -> str | None:
        self.calls.append(("save",))
        return self._content

    def set_text(self, text: str) -> None:
        self.calls.append(("set_text", text))
        self._content = text

    def restore(self, saved: str | None) -> None:
        self.calls.append(("restore", str(saved)))
        self._content = saved
