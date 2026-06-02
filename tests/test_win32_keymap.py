"""Tests for the pure Windows VK-code → neutral Key map (ADR-0018)."""

from __future__ import annotations

import pytest

from dictatem.hotkey.classifier import META_KEYS, Key
from dictatem.hotkey.win32_keymap import (
    VK_DOWN,
    VK_ESCAPE,
    VK_LCONTROL,
    VK_LEFT,
    VK_LMENU,
    VK_LSHIFT,
    VK_LWIN,
    VK_RCONTROL,
    VK_RIGHT,
    VK_RMENU,
    VK_RSHIFT,
    VK_RWIN,
    VK_UP,
    vk_to_key,
)


@pytest.mark.parametrize(
    ("vk", "expected"),
    [
        (VK_LWIN, Key.LEFT_META),
        (VK_RWIN, Key.RIGHT_META),
        (VK_LMENU, Key.LEFT_ALT),
        (VK_RMENU, Key.RIGHT_ALT),
        (VK_LCONTROL, Key.LEFT_CTRL),
        (VK_RCONTROL, Key.RIGHT_CTRL),
        (VK_LSHIFT, Key.LEFT_SHIFT),
        (VK_RSHIFT, Key.RIGHT_SHIFT),
        (VK_ESCAPE, Key.ESCAPE),
        (VK_LEFT, Key.LEFT),
        (VK_UP, Key.UP),
        (VK_RIGHT, Key.RIGHT),
        (VK_DOWN, Key.DOWN),
    ],
)
def test_known_codes_map_to_identities(vk: int, expected: Key) -> None:
    assert vk_to_key(vk) == expected


def test_unknown_code_maps_to_other() -> None:
    assert vk_to_key(0x41) is Key.OTHER  # 'A'
    assert vk_to_key(0x70) is Key.OTHER  # F1


def test_left_right_meta_distinct_but_share_group() -> None:
    """Left/right of a modifier are distinct identities (so either side sustains
    a combo) yet both belong to the same modifier group."""
    assert vk_to_key(VK_LWIN) != vk_to_key(VK_RWIN)
    assert vk_to_key(VK_LWIN) in META_KEYS
    assert vk_to_key(VK_RWIN) in META_KEYS
