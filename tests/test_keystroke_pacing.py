"""Typed Trigger Fire pacing (#275): chunk boundaries and the time bound."""

from __future__ import annotations

import pytest

from dictatem.paste.backspace_units import split_backspace_units
from dictatem.paste.keystroke_pacing import (
    CHUNK_GAP_S,
    KEYS_PER_CHUNK,
    MAX_CHUNKS_PER_PHASE,
    PHASE_GAP_S,
    chunk_backspaces,
    chunk_text_units,
    keys_per_chunk,
    utf16_units,
)


def _is_high_surrogate(unit: int) -> bool:
    return 0xD800 <= unit <= 0xDBFF


@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, []), (-3, []), (1, [1]), (8, [8]), (9, [8, 1]), (182, [8] * 22 + [6])],
)
def test_chunk_backspaces(n: int, expected: list[int]) -> None:
    assert chunk_backspaces(n) == expected


def test_utf16_units_split_supplementary_characters() -> None:
    assert utf16_units("a\U0001F600") == [0x61, 0xD83D, 0xDE00]
    assert utf16_units("") == []


def test_ascii_text_chunks_at_keys_per_chunk() -> None:
    chunks = chunk_text_units("x" * 93)
    assert [len(c) for c in chunks] == [8] * 11 + [5]


def test_chunks_concatenate_back_to_the_text() -> None:
    text = "Café crème \U0001F468‍\U0001F469‍\U0001F467 \U0001F1EC\U0001F1E7 ok"
    chunks = chunk_text_units(text)
    assert [u for c in chunks for u in c] == utf16_units(text)


@pytest.mark.parametrize("offset", range(KEYS_PER_CHUNK))
def test_a_surrogate_pair_is_never_split(offset: int) -> None:
    # Slide an emoji across every position relative to a chunk boundary.
    text = "a" * offset + "\U0001F600" * 5 + "b" * 9
    for chunk in chunk_text_units(text):
        assert not _is_high_surrogate(chunk[-1])
        assert len(chunk) <= KEYS_PER_CHUNK


def test_a_grapheme_is_never_split_across_chunks() -> None:
    text = "abcdef" + "ẹ́" + "\U0001F44D\U0001F3FD" + "xyz"
    chunks = chunk_text_units(text)
    boundaries = {0}
    for c in chunks:
        boundaries.add(max(boundaries) + len(c))
    pos, grapheme_starts = 0, set()
    for g in split_backspace_units(text):
        grapheme_starts.add(pos)
        pos += len(utf16_units(g))
    assert boundaries - {pos} <= grapheme_starts


def test_an_oversized_grapheme_gets_its_own_chunk() -> None:
    family = "\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466"  # 11 units
    chunks = chunk_text_units("ab" + family + "cd")
    assert chunks == [utf16_units("ab"), utf16_units(family), utf16_units("cd")]


def test_chunk_size_grows_to_bound_the_chunk_count() -> None:
    assert keys_per_chunk(100) == KEYS_PER_CHUNK
    assert keys_per_chunk(2000) == 10
    assert len(chunk_backspaces(5000)) <= MAX_CHUNKS_PER_PHASE
    assert len(chunk_text_units("y" * 5000)) <= MAX_CHUNKS_PER_PHASE


def test_a_2000_char_replacement_sleeps_only_a_few_seconds() -> None:
    gaps = (
        (len(chunk_backspaces(2000)) - 1) * CHUNK_GAP_S
        + PHASE_GAP_S
        + (len(chunk_text_units("z" * 2000)) - 1) * CHUNK_GAP_S
    )
    assert gaps < 4.0
