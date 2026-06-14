"""Trigger Word detection — pure logic, no I/O.

See ``CONTEXT.md#trigger-word``.

Match rule: strip whitespace, reject if multi-token, strip ASCII
punctuation, lowercase, then look up against an alias map.
"""

from __future__ import annotations

import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# Built-in action words — hard-coded Trigger Words that need no Prompt File and
# no LLM (CONTEXT.md#trigger-word). Today the only one is "paste", which
# re-pastes the Most-recent dictation (ADR-0023 / #139). They run regardless of
# whether the Transform feature is enabled.
PASTE_ACTION = "paste"
BUILTIN_ACTION_WORDS: frozenset[str] = frozenset({PASTE_ACTION})


def match_builtin_action(text: str) -> str | None:
    """Return the built-in action word *text* invokes, or ``None``.

    Uses the same match rule as Transform Trigger Words (strip whitespace +
    ASCII punctuation, lowercase, reject multi-token), so ``"Paste."``,
    ``"paste?"`` and ``"PASTE"`` all fire while ``"paste this"`` is regular
    dictation. Built-in actions are matched here — before, and independently of,
    the Transform alias map — so they run even with the Transform feature
    disabled (#139).
    """
    stripped = text.strip()
    if not stripped:
        return None
    # Multi-token utterances can never be a single action word.
    if any(ch.isspace() for ch in stripped):
        return None
    key = _normalise(stripped)
    return key if key in BUILTIN_ACTION_WORDS else None


def shadowed_builtin_aliases(aliases: Iterable[str]) -> list[str]:
    """Return the *aliases* that collide with a built-in action word.

    A user Prompt File alias that normalises to a built-in action (e.g.
    ``paste``) is **shadowed** — built-in detection runs first — so its
    Transform can never fire. The daemon warns on load. Pure so the collision
    rule is unit-tested (#139).
    """
    return sorted({a for a in aliases if _normalise(a) in BUILTIN_ACTION_WORDS})


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
