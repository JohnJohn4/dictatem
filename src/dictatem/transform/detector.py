"""Trigger Word detection — pure logic, no I/O.

See ``CONTEXT.md#trigger-word``.

Match rule: strip whitespace, reject if multi-token, strip ASCII
punctuation, lowercase, then look up against an alias map.
"""

from __future__ import annotations

import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class TriggerDetector:
    def __init__(self, aliases: Mapping[str, str]) -> None:
        # Re-normalise the supplied aliases so callers can pass the surface
        # form they expect (e.g. "summarize", "Summarize.") without each
        # caller having to know our match rule.
        self._aliases: dict[str, str] = {
            _normalise(k): v for k, v in aliases.items() if _normalise(k)
        }

    def match(self, text: str) -> str | None:
        """Return the prompt body for *text*, or ``None`` if it isn't a Trigger Word."""
        if not self._aliases:
            return None
        stripped = text.strip()
        if not stripped:
            return None
        # Multi-token utterances can never be a Trigger Word.
        if any(ch.isspace() for ch in stripped):
            return None
        key = _normalise(stripped)
        if not key:
            return None
        return self._aliases.get(key)


def _normalise(token: str) -> str:
    return token.strip().strip(string.punctuation).lower()
