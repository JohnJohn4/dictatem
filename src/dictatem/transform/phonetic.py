"""Pure string-similarity helpers for the fuzzy Trigger Word tier (#247).

Two in-repo measures, no RapidFuzz/jellyfish (spec #226, ADR-0028):

- :func:`levenshtein` — plain edit distance;
- :func:`phonetic_key` — a small metaphone-style English consonant skeleton
  (digraphs ph→F, sh/ch→X, th→0; silent letters; vowels dropped after the
  first). It need not match any published algorithm; the recognizer's golden
  table is its contract.

:func:`similarity` normalises an edit distance to ``0.0..1.0``.
"""

from __future__ import annotations

import re

_VOWELS = frozenset("aeiou")
# Initial letter pairs whose first letter is silent ("knee", "write", ...).
_SILENT_INITIAL_PAIRS = ("kn", "gn", "pn", "wr", "ae")
# h is silent after these (the pair is a digraph or the h is mute).
_H_SILENT_AFTER = frozenset("cgpst")


def levenshtein(a: str, b: str) -> int:
    """Edit distance between *a* and *b* (insert / delete / substitute = 1)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (ca != cb),
            ))
        previous = current
    return previous[-1]


def similarity(a: str, b: str) -> float:
    """Normalised edit similarity: ``1 - distance / longer length`` (0 if both empty)."""
    longest = max(len(a), len(b))
    if longest == 0:
        return 0.0
    return 1.0 - levenshtein(a, b) / longest


def phonetic_key(word: str) -> str:
    """A metaphone-style consonant skeleton of *word* (letters only, uppercase)."""
    w = re.sub(r"[^a-z]", "", word.lower())
    w = re.sub(r"(.)\1+", r"\1", w)  # collapse doubled letters
    if not w:
        return ""
    for pair in _SILENT_INITIAL_PAIRS:
        if w.startswith(pair):
            w = w[1:]
            break
    if w.startswith("x"):
        w = "s" + w[1:]
    elif w.startswith("wh"):
        w = "w" + w[2:]

    n = len(w)

    def at(j: int) -> str:
        return w[j] if 0 <= j < n else ""

    out: list[str] = []
    i = 0
    while i < n:
        c, prev, nxt, nxt2 = w[i], at(i - 1), at(i + 1), at(i + 2)
        if c in _VOWELS:
            if i == 0:
                out.append("A")
        elif c == "b":
            if not (prev == "m" and i == n - 1):  # silent in "-mb"
                out.append("B")
        elif c == "c":
            if nxt == "h":
                out.append("X")
                i += 1
            elif nxt == "i" and nxt2 == "a":
                out.append("X")
            elif nxt in ("i", "e", "y"):
                out.append("S")
            elif nxt != "k":  # "ck" -> the k carries it
                out.append("K")
        elif c == "d":
            if nxt == "g" and nxt2 in ("e", "i", "y"):
                out.append("J")
                i += 1
            else:
                out.append("T")
        elif c == "g":
            if nxt == "h" and nxt2 not in _VOWELS:
                i += 1  # silent "gh"
            elif nxt == "n" and i + 2 == n:
                pass  # silent in final "-gn"
            elif nxt in ("e", "i", "y"):
                out.append("J")
            else:
                out.append("K")
        elif c == "h":
            if nxt in _VOWELS and prev not in _H_SILENT_AFTER:
                out.append("H")
        elif c == "k":
            if prev != "c":
                out.append("K")
        elif c == "p":
            if nxt == "h":
                out.append("F")
                i += 1
            else:
                out.append("P")
        elif c == "q":
            out.append("K")
        elif c == "s":
            if nxt == "h":
                out.append("X")
                i += 1
            elif nxt == "i" and nxt2 in ("o", "a"):
                out.append("X")
            else:
                out.append("S")
        elif c == "t":
            if nxt == "i" and nxt2 in ("o", "a"):
                out.append("X")
            elif nxt == "h":
                out.append("0")
                i += 1
            else:
                out.append("T")
        elif c == "v":
            out.append("F")
        elif c in ("w", "y"):
            if nxt in _VOWELS:
                out.append(c.upper())
        elif c == "x":
            out.append("KS")
        elif c == "z":
            out.append("S")
        else:
            out.append(c.upper())
        i += 1
    return "".join(out)
