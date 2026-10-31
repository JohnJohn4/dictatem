"""Load-time Trigger Word collision check — pure, no I/O (#251, ADR-0028).

Spec #226 Layer 4. Run once at startup over the whole lexicon — the built-in
``paste`` action (with the user's ``[trigger_words].paste_aliases``) and every
Prompt File's Aliases — it reports:

- **collisions**: two Aliases of *different* actions that sound alike, so the
  fuzzy tier would make them compete for the same utterances;
- **exact-only** Aliases: shorter than :data:`FUZZY_MIN_ALIAS_LEN`, so they
  get no fuzzy tolerance at all.

Two Aliases collide when they are equal, when their phonetic keys are equal
(and long enough to mean something), or — only when both are long enough for
fuzzy tolerance — when their spelling or phonetic-key similarity is at least
:data:`COLLISION_SCORE`. An exact-only Alias never fires on a near-miss, so it
is only paired on an identical sound.

:data:`COLLISION_SCORE` (0.60) is a deliberately cautious "within fuzzy range"
heuristic (spec #226 Layer 4: an Alias that "sits within fuzzy range of"
another), not a derived guarantee. It sits below the recognizer's weak band
(:data:`FUZZY_WEAK_SCORE`) so that pairs a mishearing could plausibly carry
from one to the other are flagged — "palace" / "polish" scores only 0.67 on
phonetic keys yet is exactly the kind of pair a user should hear about. A
false warning costs a log line; a missed one costs a wrong Trigger Fire
(ADR-0028). Aliases of the same action ("summarize" / "summarise") never
collide.

Alias names are configuration, not dictated content, so the daemon logs them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dictatem.transform.alias import normalise_alias
from dictatem.transform.phonetic import phonetic_key, similarity
from dictatem.transform.recognizer import (
    FUZZY_MIN_ALIAS_LEN,
    FUZZY_MIN_EQUAL_KEY_LEN,
    PASTE_ACTION,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# The action label the report uses for the built-in `paste` action.
PASTE_ACTION_LABEL = f"built-in `{PASTE_ACTION}`"

# Cautious "within fuzzy range" bound for warning about two Aliases (see the
# module docstring and ADR-0028). A heuristic, deliberately below the weak band.
COLLISION_SCORE = 0.60


@dataclass(frozen=True)
class AliasCollision:
    """*alias* (of *action*) sounds like *other_alias* (of *other_action*)."""

    alias: str
    action: str
    other_alias: str
    other_action: str


@dataclass(frozen=True)
class ExactOnlyAlias:
    """*alias* (of *action*) is too short for fuzzy tolerance."""

    alias: str
    action: str


@dataclass(frozen=True)
class LexiconReport:
    collisions: list[AliasCollision] = field(default_factory=list)
    exact_only: list[ExactOnlyAlias] = field(default_factory=list)


def check_trigger_lexicon(
    prompt_files: Mapping[str, Iterable[str]],
    *,
    paste_aliases: Iterable[str] = (),
) -> LexiconReport:
    """Check the Trigger Word lexicon for collisions and exact-only Aliases.

    *prompt_files* maps a Prompt File name to its Aliases, in load order. The
    built-in ``paste`` action and *paste_aliases* come first. An Alias already
    claimed by an earlier action is skipped: a Prompt File alias shadowed by
    ``paste`` (warned separately) or an alias duplicated across files (the
    loader keeps the first) never competes, so it is not a collision.
    """
    lexicon: list[tuple[str, str]] = []  # (alias, action label), deduped
    claimed: set[str] = set()
    sources: list[tuple[str, Iterable[str]]] = [
        (PASTE_ACTION_LABEL, [PASTE_ACTION, *paste_aliases]),
        *prompt_files.items(),
    ]
    for action, aliases in sources:
        for raw in aliases:
            alias = normalise_alias(raw)
            if alias and alias not in claimed:
                claimed.add(alias)
                lexicon.append((alias, action))

    collisions: list[AliasCollision] = []
    for i, (alias, action) in enumerate(lexicon):
        for other_alias, other_action in lexicon[i + 1 :]:
            if other_action != action and _sound_alike(alias, other_alias):
                collisions.append(AliasCollision(alias, action, other_alias, other_action))

    exact_only = [
        ExactOnlyAlias(alias, action)
        for alias, action in lexicon
        if len(alias) < FUZZY_MIN_ALIAS_LEN
    ]
    return LexiconReport(collisions=collisions, exact_only=exact_only)


def _sound_alike(a: str, b: str) -> bool:
    if a == b:
        return True
    key_a, key_b = phonetic_key(a), phonetic_key(b)
    if key_a == key_b and len(key_a) >= FUZZY_MIN_EQUAL_KEY_LEN:
        return True
    # An exact-only Alias gets no fuzzy tolerance, so merely similar spelling
    # can't make it compete — only an identical sound (above) can.
    if min(len(a), len(b)) < FUZZY_MIN_ALIAS_LEN:
        return False
    return max(similarity(a, b), similarity(key_a, key_b)) >= COLLISION_SCORE

