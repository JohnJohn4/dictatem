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

Fuzzy tier (#247, ADR-0028): when no exact match fires and the utterance is
short (≤ ~2.5 s of speech, ≤ 3 tokens, and not an exact Alias followed by more
words), the joined tokens are scored against the lexicon by letter and
phonetic-key edit similarity. A strong, confident (or confidence-unknown),
unambiguous match fires ``via=FUZZY``; anything else is Dictation.
"""

from __future__ import annotations

import enum
import re
import string
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dictatem.transform.phonetic import phonetic_key, similarity

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

# Fuzzy tier (#247, spec #226). Constants, not config: tuned against — and
# pinned only by — the golden table in tests/test_trigger_recognizer.py.
FUZZY_MAX_TOKENS = 3
# Aliases shorter than this are matched exactly only.
FUZZY_MIN_ALIAS_LEN = 5
# Score = max(letter similarity, phonetic-key similarity), each 0..1.
FUZZY_STRONG_SCORE = 0.80
FUZZY_WEAK_SCORE = 0.70
# Equal phonetic keys of at least this many symbols also count as strong.
FUZZY_MIN_EQUAL_KEY_LEN = 3
# Candidates of different actions this close to the best are a tie.
FUZZY_TIE_MARGIN = 0.05
# Whisper's conventional "the model was unsure" thresholds; a guardrail on
# fuzzy fires only — never on exact matches.
MIN_CONFIDENT_AVG_LOGPROB = -1.0
MAX_CONFIDENT_NO_SPEECH_PROB = 0.6

_LETTERS_ONLY = re.compile(r"[^a-z]")


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
    """How a Fire was matched: the exact rule, or the fuzzy tier (#247)."""

    EXACT = "exact"
    FUZZY = "fuzzy"


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
    """Decides Dictation vs Fire for an utterance. Built once at startup.

    *paste_aliases* (``[trigger_words].paste_aliases``, #250) are the user's
    own words for the built-in ``paste`` action: they fire it exactly and
    fuzzily just like ``paste`` itself and shadow same-named Prompt File
    aliases. *fuzzy_matching* (``[trigger_words].fuzzy_matching``, default on)
    enables the fuzzy tier; off restores exact-only matching.
    """

    def __init__(
        self,
        prompt_aliases: Mapping[str, str],
        *,
        paste_aliases: Iterable[str] = (),
        fuzzy_matching: bool = True,
    ) -> None:
        # Re-normalise the supplied aliases so callers can pass the surface
        # form they expect (e.g. "summarize", "Summarize.") without each
        # caller having to know our match rule.
        self._transforms: dict[str, str] = {
            _normalise(k): v for k, v in prompt_aliases.items() if _normalise(k)
        }
        # User aliases for the built-in `paste` action ([trigger_words].
        # paste_aliases, #250): alias -> built-in action word.
        self._builtin_aliases: dict[str, str] = {w: w for w in BUILTIN_ACTION_WORDS}
        for alias in paste_aliases:
            if _normalise(alias):
                self._builtin_aliases.setdefault(_normalise(alias), PASTE_ACTION)
        self._fuzzy_matching = fuzzy_matching
        # Every exact Alias (built-ins + Prompt File Aliases, armed or not):
        # an utterance that *starts* with one and goes on ("summarize this",
        # "paste it") is always Dictation — the documented contract.
        self._exact_aliases = frozenset(self._builtin_aliases.keys() | self._transforms.keys())
        # Fuzzy lexicon: (alias, phonetic key, target). Prompt File aliases
        # shadowed by a built-in or a `paste` alias are left out (the built-in
        # wins) and so are Aliases too short for fuzzy tolerance (exact-only).
        builtins = [
            (alias, BuiltinAction(action))
            for alias, action in sorted(self._builtin_aliases.items())
        ]
        transforms = [
            (alias, TransformTarget(alias=alias, prompt=prompt))
            for alias, prompt in self._transforms.items()
            if alias not in self._builtin_aliases
        ]
        self._fuzzy_lexicon: list[tuple[str, str, TriggerTarget]] = [
            (alias, phonetic_key(alias), target)
            for alias, target in [*builtins, *transforms]
            if len(alias) >= FUZZY_MIN_ALIAS_LEN
        ]

    def decide(self, utterance: Utterance, *, transforms_armed: bool) -> TriggerDecision:
        key = _single_token_key(utterance.text)
        if key is not None:
            # Built-in actions first: they shadow a same-named Prompt File
            # alias and fire whether or not Transforms are armed — they are
            # the recovery path (ADR-0023 / #139).
            if key in self._builtin_aliases:
                return Fire(BuiltinAction(self._builtin_aliases[key]))
            if transforms_armed and key in self._transforms:
                return Fire(TransformTarget(alias=key, prompt=self._transforms[key]))
        if self._fuzzy_matching:
            return self._decide_fuzzy(utterance, transforms_armed=transforms_armed)
        return Dictation()

    def _decide_fuzzy(self, utterance: Utterance, *, transforms_armed: bool) -> TriggerDecision:
        """The fuzzy tier (#247): short utterances that *sound like* an Alias.

        Only decides "is this a Trigger Word" — never rewrites dictation
        (ADR-0024 / ADR-0028). Weak matches, unconfident strong matches and
        cross-action ties are Dictation until the Borderline ticket (#248).
        """
        tokens = [t for t in (_normalise(t) for t in utterance.text.split()) if t]
        if not tokens or len(tokens) > FUZZY_MAX_TOKENS or not utterance.is_short:
            return Dictation()
        if len(tokens) > 1 and tokens[0] in self._exact_aliases:
            return Dictation()
        joined = _LETTERS_ONLY.sub("", "".join(tokens))
        if not joined:
            return Dictation()
        joined_key = phonetic_key(joined)

        scored: list[tuple[float, bool, TriggerTarget]] = []
        for alias, alias_key, target in self._fuzzy_lexicon:
            if isinstance(target, TransformTarget) and not transforms_armed:
                continue  # an unarmed Transform is never a candidate
            score = max(similarity(joined, alias), similarity(joined_key, alias_key))
            keys_equal = joined_key == alias_key and len(alias_key) >= FUZZY_MIN_EQUAL_KEY_LEN
            strong = score >= FUZZY_STRONG_SCORE or keys_equal
            if strong or score >= FUZZY_WEAK_SCORE:
                scored.append((1.0 if keys_equal else score, strong, target))
        if not scored:
            return Dictation()
        scored.sort(key=lambda s: s[0], reverse=True)
        best_score, best_strong, best_target = scored[0]
        rival = any(
            _action_of(target) != _action_of(best_target)
            and best_score - score <= FUZZY_TIE_MARGIN
            for score, _strong, target in scored[1:]
        )
        if rival or not best_strong or not _is_confident(utterance.confidence):
            return Dictation()  # Borderline lands here in #248
        return Fire(best_target, via=MatchVia.FUZZY)


def shadowed_builtin_aliases(
    aliases: Iterable[str], *, paste_aliases: Iterable[str] = ()
) -> list[str]:
    """Return the *aliases* that collide with a built-in action word or alias.

    A user Prompt File alias that normalises to a built-in action (e.g.
    ``paste``) or to one of the user's *paste_aliases* (#250) is **shadowed**
    — built-in matching runs first — so its Transform can never fire. The
    daemon warns on load (#139).
    """
    builtin = BUILTIN_ACTION_WORDS | {_normalise(a) for a in paste_aliases if _normalise(a)}
    return sorted({a for a in aliases if _normalise(a) in builtin})


def _action_of(target: TriggerTarget) -> str:
    """Identity of the action a target runs — aliases of one Prompt File share it."""
    if isinstance(target, BuiltinAction):
        return f"builtin:{target.name}"
    return f"transform:{target.prompt}"


def _is_confident(confidence: SegmentConfidence | None) -> bool:
    """Unknown confidence is no evidence against (spec #226, Layer 2)."""
    if confidence is None:
        return True
    return (
        confidence.avg_logprob >= MIN_CONFIDENT_AVG_LOGPROB
        and confidence.no_speech_prob < MAX_CONFIDENT_NO_SPEECH_PROB
    )


def _single_token_key(text: str) -> str | None:
    """The normalised key for a single-token *text*, or ``None``."""
    stripped = text.strip()
    # Multi-token utterances can never be an exact Trigger Word.
    if not stripped or any(ch.isspace() for ch in stripped):
        return None
    return _normalise(stripped) or None


def _normalise(token: str) -> str:
    return token.strip().strip(string.punctuation).lower()
