"""Backspace Unit counter — user-perceived characters in a Last Paste (#242).

Expected counts are what a user sees on screen (and what a text field deletes
per Backspace), taken from UAX #29's extended grapheme cluster rules — not
recomputed from the implementation.
"""

from __future__ import annotations

import pytest

from dictatem.paste.backspace_units import count_backspace_units


@pytest.mark.parametrize(
    "text",
    ["", "a", "hello world ", "The quick brown fox, 42 times!? "],
)
def test_plain_ascii_counts_equal_its_length(text: str) -> None:
    assert count_backspace_units(text) == len(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # q + combining dot below: no precomposed form, survives NFC.
        ("q\u0323", 1),
        # e + acute + dot below (two marks on one base).
        ("e\u0301\u0323", 1),
        # Devanagari "ki": KA + vowel sign I (spacing combining mark, Mc).
        ("\u0915\u093f", 1),
        ("caf\u00e9 ", 5),
        ("na\u0303o ", 4),
    ],
)
def test_combining_marks_join_their_base(text: str, expected: int) -> None:
    assert count_backspace_units(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Thumbs up + medium skin tone modifier.
        ("\U0001f44d\U0001f3fd", 1),
        ("ok \U0001f44b\U0001f3ff ", 5),
        # Red heart + VS16 (emoji presentation).
        ("\u2764\ufe0f", 1),
        # Text-presentation selector too.
        ("\u263a\ufe0e", 1),
        # Keycap "1": digit + VS16 + combining enclosing keycap.
        ("1\ufe0f\u20e3", 1),
        ("#\ufe0f\u20e3 tag", 5),
        # Flag of England: black flag + tag letters g b e n g + cancel tag.
        (
            "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067"
            "\U000e007f",
            1,
        ),
    ],
)
def test_emoji_extenders_join_their_base(text: str, expected: int) -> None:
    assert count_backspace_units(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Family: man ZWJ woman ZWJ girl ZWJ boy.
        ("\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466", 1),
        # Woman technologist, medium-dark skin: woman + modifier + ZWJ + laptop.
        ("\U0001f469\U0001f3fe\u200d\U0001f4bb", 1),
        # Rainbow flag: white flag + VS16 + ZWJ + rainbow.
        ("\U0001f3f3\ufe0f\u200d\U0001f308", 1),
        # Heart on fire: heart + VS16 + ZWJ + fire (BMP base).
        ("\u2764\ufe0f\u200d\U0001f525", 1),
        # A ZWJ between letters does not join them (GB11 is emoji-only).
        ("a\u200db", 2),
    ],
)
def test_zwj_sequences_are_one_unit(text: str, expected: int) -> None:
    assert count_backspace_units(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\U0001f1fa\U0001f1f8", 1),  # US
        ("\U0001f1ec\U0001f1e7\U0001f1eb\U0001f1f7", 2),  # GB FR
        ("\U0001f1ec\U0001f1e7\U0001f1eb", 2),  # GB + dangling F
        ("go \U0001f1ef\U0001f1f5!", 5),
    ],
)
def test_regional_indicators_pair_into_flags(text: str, expected: int) -> None:
    assert count_backspace_units(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\ud55c\uad6d\uc5b4", 3),  # precomposed syllables
        ("\u1112\u1161\u11ab", 1),  # conjoining jamo L V T
        ("\u1100\u1161", 1),  # L V
        ("\uac00\u11a8", 1),  # LV syllable + trailing T
        ("\uac01\u11a8", 1),  # LVT syllable + trailing T
        ("\u1100\uac00", 1),  # L + LV syllable
        ("\u11a8\u1100", 2),  # T then L: break
        ("\uac00\uac00", 2),  # two LV syllables: break
    ],
)
def test_hangul_syllable_sequences(text: str, expected: int) -> None:
    assert count_backspace_units(text) == expected


def test_crlf_is_one_unit_but_other_controls_stand_alone() -> None:
    assert count_backspace_units("a\r\nb") == 3
    assert count_backspace_units("a\n\rb") == 4
    # A control never absorbs a following mark.
    assert count_backspace_units("\n\u0301") == 2
