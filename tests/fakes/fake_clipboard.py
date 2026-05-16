"""Fake clipboard for testing paste pipeline logic."""

from __future__ import annotations

import time


class FakeClipboardIO:
    def __init__(
        self,
        *,
        open_failures: int = 0,
        restore_failures: int = 0,
    ) -> None:
        self._content: str | None = None
        self.calls: list[tuple[str, ...]] = []
        self.open_timestamps: list[float] = []
        self.restore_timestamps: list[float] = []
        self._open_failures_remaining = open_failures
        self._restore_failures_remaining = restore_failures

    def open(self) -> None:
        self.open_timestamps.append(time.monotonic())
        if self._open_failures_remaining > 0:
            self._open_failures_remaining -= 1
            msg = "clipboard is locked"
            raise OSError(msg)
        self.calls.append(("open",))

    def close(self) -> None:
        self.calls.append(("close",))

    def save(self) -> str | None:
        self.calls.append(("save",))
        return self._content

    def set_text(self, text: str) -> None:
        self.calls.append(("set_text", text))
        self._content = text

    def restore(self, saved: str | None) -> None:
        self.restore_timestamps.append(time.monotonic())
        if self._restore_failures_remaining > 0:
            self._restore_failures_remaining -= 1
            msg = "clipboard is locked"
            raise OSError(msg)
        self.calls.append(("restore", str(saved)))
        self._content = saved
