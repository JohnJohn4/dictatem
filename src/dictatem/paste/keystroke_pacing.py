"""Pacing for the typed Trigger Fire replacement (#275): pure chunking logic.

Trigger Fire deletes the Last Paste with Backspaces and *types* the new text
with ``KEYEVENTF_UNICODE`` keystrokes (ADR-0004). Sending each phase as ONE
giant ``SendInput`` batch is accepted in full by ``SendInput``, but some
targets can't keep up with the flood. Windows 11 Notepad (``RichEditD2DPT``)
deleted only part of a 182-Backspace Last Paste and then showed mostly blanks
instead of the 93 typed characters. Notepad++ (Scintilla) coped fine.

So the Win32 adapter sends each phase in small chunks of key presses with a
short sleep between chunks, and leaves a longer gap between the Backspace
phase and the typing phase. This module decides the chunk boundaries. The
adapter only builds the ``INPUT`` events and loops with an injected sleep.

Trade-off: pacing adds latency, roughly ``CHUNK_GAP_S`` for every
``KEYS_PER_CHUNK`` key presses. To keep that bounded, a phase never uses more
than ``MAX_CHUNKS_PER_PHASE`` chunks. Long replacements get bigger chunks
instead, so the gaps in one phase add up to at most
``MAX_CHUNKS_PER_PHASE * CHUNK_GAP_S`` (about 1.6 s). A 2,000-character
replacement of a 2,000-unit Last Paste then sleeps for about 3.2 s in total
(a little more if grapheme packing leaves chunks part-full). Replacing a
100-200 character Last Paste with similar-length text takes about 0.2-0.4 s.
Bigger chunks are a little less gentle on slow targets. That is the price of
the time bound, and it only applies past 1,600 key presses in a phase.

Chunks never split a UTF-16 surrogate pair. They also never split a Backspace
Unit (a user-perceived character, ``CONTEXT.md#backspace-unit``), so a
combining accent or ZWJ emoji sequence reaches the target within one batch.
"""

from __future__ import annotations

import math

from dictatem.paste.backspace_units import split_backspace_units

# Key presses (one down + one up event each) per SendInput chunk. Eight
# presses = 16 events: small enough that Win11 Notepad keeps up, large enough
# that a typical rewrite is only a few dozen chunks.
KEYS_PER_CHUNK = 8
# Sleep between two chunks of the same phase.
CHUNK_GAP_S = 0.008
# Sleep between the Backspace phase and the typing phase, so the target has
# finished deleting before the first typed character arrives. A fixed gap,
# not a barrier: SendMessageTimeout(WM_NULL) to the target returns as soon
# as its thread next pumps. Sent messages are dispatched ahead of queued
# input, and injected input may still be in the raw input thread, so a
# WM_NULL reply doesn't prove the Backspaces were processed (ADR-0004).
PHASE_GAP_S = 0.04
# Upper bound on chunks per phase. Past this the chunk size grows instead, so
# a phase's chunk gaps never total more than about 1.6 s.
MAX_CHUNKS_PER_PHASE = 200


def keys_per_chunk(n_keys: int) -> int:
    """Key presses per chunk for a phase of *n_keys* presses (time-bounded)."""
    return max(KEYS_PER_CHUNK, math.ceil(n_keys / MAX_CHUNKS_PER_PHASE))


def chunk_backspaces(n: int) -> list[int]:
    """Split *n* Backspace presses into per-chunk counts (empty for n <= 0)."""
    if n <= 0:
        return []
    size = keys_per_chunk(n)
    full, rest = divmod(n, size)
    return [size] * full + ([rest] if rest else [])


def utf16_units(text: str) -> list[int]:
    """*text* as UTF-16 code units: supplementary characters become surrogate pairs."""
    raw = text.encode("utf-16-le")
    return [int.from_bytes(raw[i : i + 2], "little") for i in range(0, len(raw), 2)]


def chunk_text_units(text: str) -> list[list[int]]:
    """Split *text* into chunks of UTF-16 code units, one key press per unit.

    Chunks are filled with whole Backspace Units (graphemes), up to
    ``keys_per_chunk`` code units each. A single grapheme longer than that
    (e.g. a long ZWJ family emoji) gets a chunk of its own rather than being
    split. So no chunk ever ends between a high and a low surrogate.
    Concatenating the chunks gives back ``utf16_units(text)``.
    """
    if not text:
        return []
    graphemes = [utf16_units(g) for g in split_backspace_units(text)]
    size = keys_per_chunk(sum(len(g) for g in graphemes))
    chunks: list[list[int]] = []
    current: list[int] = []
    for units in graphemes:
        if current and len(current) + len(units) > size:
            chunks.append(current)
            current = []
        current.extend(units)
    if current:
        chunks.append(current)
    return chunks
