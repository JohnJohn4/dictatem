"""Fake keystroke sender for testing paste pipeline logic."""

from __future__ import annotations


class FakeKeystrokeSender:
    def __init__(self) -> None:
        self.paste_count: int = 0

    def send_paste(self) -> None:
        self.paste_count += 1
