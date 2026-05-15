"""Last Paste snapshot — the operand for Trigger Words."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LastPaste:
    """Snapshot of the most recent paste, with rails for safe replacement.

    See ``CONTEXT.md#last-paste``.

    ``char_count`` is the length of the *post-normalisation* string actually
    sent to the focused window (i.e. what ``paste.pipeline._normalize``
    produced), so backspace counts line up with what's on screen.
    """

    text: str
    char_count: int
    hwnd: int
    pasted_at_ms: int

    def rails_ok(self, current_hwnd: int, now_ms: int, ttl_s: float) -> bool:
        if current_hwnd != self.hwnd:
            return False
        age_ms = now_ms - self.pasted_at_ms
        return age_ms < int(ttl_s * 1000)
