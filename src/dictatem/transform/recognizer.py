"""Trigger Word recognizer — the one pure trigger decision, no I/O.

See ``CONTEXT.md#trigger-word``. Merges the old exact Trigger Word detector and
the built-in-action matcher behind a single ``decide`` (#246, spec #226): given
an :class:`Utterance` and whether Transforms are armed, it returns a
:data:`TriggerDecision` — :class:`Dictation` or :class:`Fire`.

Match rule (exact): strip whitespace, reject if multi-token, strip ASCII
punctuation, lowercase, then look the key up. Built-in actions are checked
first, so they shadow a same-named Prompt File alias and fire regardless of the
armed state; a Transform is only a candidate when armed (Transform feature
enabled AND a Last Paste exists).
"""

from __future__ import annotations

import enum
import string
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from dictatem.types import SegmentConfidence

# Built-in action words — hard-coded Trigger Words that need no Prompt File and
# no LLM (CONTEXT.md#trigger-word). Today the only one is "paste", which
# re-pastes the Most-recent dictation (ADR-0023 / #139). They run regardless of
# whether the Transform feature is enabled.
PASTE_ACTION = "paste"
BUILTIN_ACTION_WORDS: frozenset[str] = frozenset({PASTE_ACTION})

# An utterance at most this long (seconds of speech) is "short": a Trigger Word
# candidate. Used today only to gate the short-utterance diagnostics log line
# (§6.3); the fuzzy tier (#226) will gate on it too.
SHORT_UTTERANCE_MAX_S = 2.5


@dataclass(frozen=True)
class Utterance:
    """What the recognizer judges: the transcript text and how it was heard.

    ``speech_duration_s`` is the post-VAD speech duration when the backend
    reported it, else the recording duration. ``confidence`` is ``None`` when
    the backend can't report it.
    """

    text: str
    speech_duration_s: float
    confidence: SegmentConfidence | None = None

    @property
    def is_short(self) -> bool:
        return self.speech_duration_s <= SHORT_UTTERANCE_MAX_S


@dataclass(frozen=True)
class BuiltinAction:
    """A built-in action target, e.g. ``paste`` (no Prompt File, no LLM)."""

    name: str


@dataclass(frozen=True)
class TransformTarget:
    """A Transform target: the matched (normalised) Alias and its prompt body."""

    alias: str
    prompt: str


TriggerTarget = BuiltinAction | TransformTarget


class MatchVia(enum.Enum):
    """How a Fire was matched. Only EXACT today; the fuzzy tier adds FUZZY."""

    EXACT = "exact"


@dataclass(frozen=True)
class Dictation:
    """Not a Trigger Word — paste the text as regular dictation."""


@dataclass(frozen=True)
class Fire:
    """A Trigger Word — run *target*."""

    target: TriggerTarget
    via: MatchVia = MatchVia.EXACT


TriggerDecision = Dictation | Fire


class TriggerWordRecognizer:
    """Decides Dictation vs Fire for an utterance. Built once at startup."""

    def __init__(self, prompt_aliases: Mapping[str, str]) -> None:
        # Re-normalise the supplied aliases so callers can pass the surface
        # form they expect (e.g. "summarize", "Summarize.") without each
        # caller having to know our match rule.
        self._transforms: dict[str, str] = {
            _normalise(k): v for k, v in prompt_aliases.items() if _normalise(k)
        }

    def decide(self, utterance: Utterance, *, transforms_armed: bool) -> TriggerDecision:
        key = _single_token_key(utterance.text)
        if key is None:
            return Dictation()
        # Built-in actions first: they shadow a same-named Prompt File alias
        # and fire whether or not Transforms are armed — they are the recovery
        # path (ADR-0023 / #139).
        if key in BUILTIN_ACTION_WORDS:
            return Fire(BuiltinAction(key))
        if transforms_armed and key in self._transforms:
            return Fire(TransformTarget(alias=key, prompt=self._transforms[key]))
        return Dictation()


def shadowed_builtin_aliases(aliases: Iterable[str]) -> list[str]:
    """Return the *aliases* that collide with a built-in action word.

    A user Prompt File alias that normalises to a built-in action (e.g.
    ``paste``) is **shadowed** — built-in matching runs first — so its
    Transform can never fire. The daemon warns on load (#139).
    """
    return sorted({a for a in aliases if _normalise(a) in BUILTIN_ACTION_WORDS})


def _single_token_key(text: str) -> str | None:
    """The normalised key for a single-token *text*, or ``None``."""
    stripped = text.strip()
    # Multi-token utterances can never be an exact Trigger Word.
    if not stripped or any(ch.isspace() for ch in stripped):
        return None
    return _normalise(stripped) or None


def _normalise(token: str) -> str:
    return token.strip().strip(string.punctuation).lower()
