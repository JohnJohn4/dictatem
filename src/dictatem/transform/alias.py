"""The one Alias normaliser — pure, no I/O (#226).

Every place an Alias or a heard token is compared — Prompt File loading,
``[trigger_words].paste_aliases``, the Trigger Word recognizer and the
load-time collision check — normalises it the same way, so they always agree
on what counts as "the same word".
"""

from __future__ import annotations

import string


def normalise_alias(token: str) -> str:
    """Trim whitespace and surrounding punctuation, then lowercase.

    ``" Paste. "`` -> ``"paste"``. Returns ``""`` for a token that is only
    whitespace and punctuation.
    """
    return token.strip().strip(string.punctuation).lower()
