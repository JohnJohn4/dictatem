"""Last Paste snapshot — the operand for Trigger Words."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LastPaste:
    """Snapshot of the most recent paste, with rails for safe replacement.

    See ``CONTEXT.md#last-paste``.

    ``char_count`` is the length, in Backspace Units (user-perceived
    characters, see ``paste.backspace_units``), of the *post-normalisation*
    string actually sent to the focused window (what
    ``paste.pipeline.normalize_pasted_text`` produced), so the Trigger Fire
    backspace count lines up with what's on screen (#242).
    """

    text: str
    char_count: int
    target_id: int
    pasted_at_ms: int

    def rails_ok(self, current_target_id: int, now_ms: int, ttl_s: float) -> bool:
        if current_target_id != self.target_id:
            return False
        age_ms = now_ms - self.pasted_at_ms
        return age_ms < int(ttl_s * 1000)
