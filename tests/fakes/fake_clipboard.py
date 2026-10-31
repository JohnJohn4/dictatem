"""Fake clipboard for testing paste pipeline logic.

Holds an opaque ``ClipboardSnapshot`` like a real clipboard holds formats:
``save`` hands back what is held, ``restore`` puts a snapshot back as-is, and
``set_text``/``copy`` replace the clipboard with a single text entry. ``text``
is a convenience view for tests that only care about plain text.
"""

from __future__ import annotations

import time

from dictatem.paste.clipboard_snapshot import ClipboardSnapshot

# The fake's own text "format id" — any hashable works, the snapshot is opaque.
FAKE_TEXT_FORMAT = "text/plain"


def _text_snapshot(text: str) -> ClipboardSnapshot:
    return ClipboardSnapshot(entries=((FAKE_TEXT_FORMAT, text.encode("utf-8")),))


class FakeClipboardIO:
    def __init__(
        self,
        *,
        open_failures: int = 0,
        restore_failures: int = 0,
    ) -> None:
        self.held: ClipboardSnapshot = ClipboardSnapshot.empty()
        self.calls: list[tuple[object, ...]] = []
        self.open_timestamps: list[float] = []
        self.restore_timestamps: list[float] = []
        self._open_failures_remaining = open_failures
        self._restore_failures_remaining = restore_failures

    @property
    def text(self) -> str | None:
        """The held plain text, or None if the clipboard holds no text entry."""
        for fid, data in self.held.entries:
            if fid == FAKE_TEXT_FORMAT:
                return data.decode("utf-8")
        return None

    @text.setter
    def text(self, value: str | None) -> None:
        self.held = ClipboardSnapshot.empty() if value is None else _text_snapshot(value)

    def open(self) -> None:
        self.open_timestamps.append(time.monotonic())
        if self._open_failures_remaining > 0:
            self._open_failures_remaining -= 1
            msg = "clipboard is locked"
            raise OSError(msg)
        self.calls.append(("open",))

    def close(self) -> None:
        self.calls.append(("close",))

    def save(self) -> ClipboardSnapshot:
        self.calls.append(("save",))
        return self.held

    def set_text(self, text: str) -> None:
        self.calls.append(("set_text", text))
        self.text = text

    def copy(self, text: str) -> None:
        # The explicit, normal "Copy last dictation" copy (#119) — distinct from
        # the transient set_text juggling so tests can assert which path ran.
        self.calls.append(("copy", text))
        self.text = text

    def restore(self, saved: ClipboardSnapshot) -> None:
        self.restore_timestamps.append(time.monotonic())
        if self._restore_failures_remaining > 0:
            self._restore_failures_remaining -= 1
            msg = "clipboard is locked"
            raise OSError(msg)
        self.calls.append(("restore", saved))
        self.held = saved
