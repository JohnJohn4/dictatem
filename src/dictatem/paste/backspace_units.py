"""Backspace Unit counter — how many Backspaces delete a pasted string (#242).

See ``CONTEXT.md#backspace-unit``.

A Backspace Unit is one user-perceived character: an *extended grapheme
cluster* in Unicode terms (UAX #29). Trigger Fire sends one Backspace per unit
to erase the Last Paste, so counting code points over-deletes on emoji and
decomposed accents (review F-5).

Python's standard library has no grapheme segmenter, and the ``regex`` package
(``\\X``) would add an install dependency (ADR-0011), so this is a small
stdlib-only **approximation** of UAX #29 built on ``unicodedata``. It covers:
combining marks (GB9/GB9a), CR LF (GB3), controls (GB4/GB5), Hangul syllable
sequences (GB6-GB8), emoji ZWJ sequences (GB11), emoji modifiers, variation
selectors, keycaps and emoji tag sequences (all Extend), and regional-indicator
flag pairs (GB12/GB13).

Known gaps (deliberate, rare in dictated/LLM text): Prepend characters
(GB9b) are treated as ordinary characters; Indic conjunct joining (GB9c,
Unicode 15.1) is not applied; Extended_Pictographic is approximated by code
point ranges rather than the full property table.
"""

from __future__ import annotations

import unicodedata
from enum import Enum, auto


class _Prop(Enum):
    """Grapheme_Cluster_Break property values this approximation needs."""

    CR = auto()
    LF = auto()
    CONTROL = auto()
    EXTEND = auto()
    SPACING_MARK = auto()
    ZWJ = auto()
    REGIONAL_INDICATOR = auto()
    EXT_PICT = auto()
    L = auto()
    V = auto()
    T = auto()
    LV = auto()
    LVT = auto()
    OTHER = auto()


# Approximation of Extended_Pictographic (emoji-capable symbols) by range. It
# only matters after a ZWJ (GB11), so over-including a few non-emoji symbols
# in these blocks is harmless.
_EXT_PICT_RANGES = (
    (0x00A9, 0x00A9),
    (0x00AE, 0x00AE),
    (0x203C, 0x203C),
    (0x2049, 0x2049),
    (0x2122, 0x2122),
    (0x2139, 0x2139),
    (0x2194, 0x21AA),
    (0x231A, 0x23FF),
    (0x24C2, 0x24C2),
    (0x25AA, 0x25FE),
    (0x2600, 0x27BF),
    (0x2934, 0x2935),
    (0x2B05, 0x2B55),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3299),
    (0x1F000, 0x1FAFF),
    (0x1FC00, 0x1FFFD),
)


def _is_ext_pict(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _EXT_PICT_RANGES)


def _prop(ch: str) -> _Prop:
    if ch == "\r":
        return _Prop.CR
    if ch == "\n":
        return _Prop.LF
    cp = ord(ch)
    if cp == 0x200D:
        return _Prop.ZWJ
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return _Prop.REGIONAL_INDICATOR
    # Grapheme_Extend code points whose General_Category doesn't say so:
    # emoji skin-tone modifiers (Sk), tag characters (Cf), ZWNJ (Cf), and the
    # half-width katakana sound marks (Lm).
    if (
        0x1F3FB <= cp <= 0x1F3FF
        or 0xE0020 <= cp <= 0xE007F
        or cp in (0x200C, 0xFF9E, 0xFF9F)
    ):
        return _Prop.EXTEND
    hangul = _hangul_prop(cp)
    if hangul is not None:
        return hangul
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me"):
        return _Prop.EXTEND
    if cat == "Mc":
        return _Prop.SPACING_MARK
    if cat in ("Cc", "Zl", "Zp", "Cf"):
        return _Prop.CONTROL
    if _is_ext_pict(cp):
        return _Prop.EXT_PICT
    return _Prop.OTHER


def _hangul_prop(cp: int) -> _Prop | None:
    if 0x1100 <= cp <= 0x115F or 0xA960 <= cp <= 0xA97C:
        return _Prop.L
    if 0x1160 <= cp <= 0x11A7 or 0xD7B0 <= cp <= 0xD7C6:
        return _Prop.V
    if 0x11A8 <= cp <= 0x11FF or 0xD7CB <= cp <= 0xD7FB:
        return _Prop.T
    if 0xAC00 <= cp <= 0xD7A3:
        # Precomposed syllables: every 28th is LV (no final consonant).
        return _Prop.LV if (cp - 0xAC00) % 28 == 0 else _Prop.LVT
    return None


_BREAKERS = (_Prop.CR, _Prop.LF, _Prop.CONTROL)

# GB6-GB8: Hangul syllable sequences that don't break.
_HANGUL_JOINS = {
    _Prop.L: (_Prop.L, _Prop.V, _Prop.LV, _Prop.LVT),
    _Prop.LV: (_Prop.V, _Prop.T),
    _Prop.V: (_Prop.V, _Prop.T),
    _Prop.LVT: (_Prop.T,),
    _Prop.T: (_Prop.T,),
}


def _is_boundary(
    prev: _Prop, cur: _Prop, *, in_pict_seq: bool, ri_run: int
) -> bool:
    if prev is _Prop.CR and cur is _Prop.LF:  # GB3
        return False
    if prev in _BREAKERS or cur in _BREAKERS:  # GB4, GB5
        return True
    if cur in _HANGUL_JOINS.get(prev, ()):  # GB6, GB7, GB8
        return False
    if cur in (_Prop.EXTEND, _Prop.ZWJ, _Prop.SPACING_MARK):  # GB9, GB9a
        return False
    if prev is _Prop.ZWJ and cur is _Prop.EXT_PICT and in_pict_seq:  # GB11
        return False
    # GB12/GB13: regional indicators pair up left to right.
    return not (
        prev is _Prop.REGIONAL_INDICATOR
        and cur is _Prop.REGIONAL_INDICATOR
        and ri_run % 2 == 1
    )


def count_backspace_units(text: str) -> int:
    """Return the number of user-perceived characters in *text*.

    Walks the code points once, applying the UAX #29 break rules to each
    adjacent pair; the result is the number of cluster starts.
    """
    count = 0
    prev: _Prop | None = None
    # GB11 tracker: inside ``ExtPict Extend* ZWJ?`` so far.
    in_pict_seq = False
    # GB12/GB13 tracker: regional indicators in the current unbroken run.
    ri_run = 0
    for ch in text:
        cur = _prop(ch)
        if prev is None or _is_boundary(
            prev, cur, in_pict_seq=in_pict_seq, ri_run=ri_run
        ):
            count += 1
        if cur is _Prop.EXT_PICT:
            in_pict_seq = True
        elif cur is _Prop.EXTEND or (cur is _Prop.ZWJ and prev is not _Prop.ZWJ):
            pass  # extenders (and one ZWJ) keep an emoji sequence open
        else:
            in_pict_seq = False
        ri_run = ri_run + 1 if cur is _Prop.REGIONAL_INDICATOR else 0
        prev = cur
    return count
