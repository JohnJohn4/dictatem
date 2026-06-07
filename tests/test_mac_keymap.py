"""Tests for the pure macOS CGKeyCode → neutral Key map (ADR-0018)."""

from __future__ import annotations

import pytest

from dictatem.hotkey.classifier import META_KEYS, Key, KeyAction
from dictatem.hotkey.mac_keymap import (
    KVK_COMMAND,
    KVK_CONTROL,
    KVK_DOWN_ARROW,
    KVK_ESCAPE,
    KVK_LEFT_ARROW,
    KVK_OPTION,
    KVK_RIGHT_ARROW,
    KVK_RIGHT_COMMAND,
    KVK_RIGHT_CONTROL,
    KVK_RIGHT_OPTION,
    KVK_RIGHT_SHIFT,
    KVK_SHIFT,
    KVK_UP_ARROW,
    NX_DEVICELALTKEYMASK,
    NX_DEVICELCMDKEYMASK,
    NX_DEVICELCTLKEYMASK,
    NX_DEVICELSHIFTKEYMASK,
    NX_DEVICERALTKEYMASK,
    NX_DEVICERCMDKEYMASK,
    NX_DEVICERCTLKEYMASK,
    NX_DEVICERSHIFTKEYMASK,
    flags_changed_action,
    keycode_to_key,
)


@pytest.mark.parametrize(
    ("keycode", "expected"),
    [
        (KVK_COMMAND, Key.LEFT_META),
        (KVK_RIGHT_COMMAND, Key.RIGHT_META),
        (KVK_OPTION, Key.LEFT_ALT),
        (KVK_RIGHT_OPTION, Key.RIGHT_ALT),
        (KVK_CONTROL, Key.LEFT_CTRL),
        (KVK_RIGHT_CONTROL, Key.RIGHT_CTRL),
        (KVK_SHIFT, Key.LEFT_SHIFT),
        (KVK_RIGHT_SHIFT, Key.RIGHT_SHIFT),
        (KVK_ESCAPE, Key.ESCAPE),
        (KVK_LEFT_ARROW, Key.LEFT),
        (KVK_UP_ARROW, Key.UP),
        (KVK_RIGHT_ARROW, Key.RIGHT),
        (KVK_DOWN_ARROW, Key.DOWN),
    ],
)
def test_known_codes_map_to_identities(keycode: int, expected: Key) -> None:
    assert keycode_to_key(keycode) == expected


def test_unknown_code_maps_to_other() -> None:
    assert keycode_to_key(0x00) is Key.OTHER  # 'A' (kVK_ANSI_A)
    assert keycode_to_key(0x7A) is Key.OTHER  # F1 (kVK_F1)


def test_left_right_meta_distinct_but_share_group() -> None:
    """Left/right of a modifier are distinct identities (so either side sustains
    a combo) yet both belong to the same modifier group."""
    assert keycode_to_key(KVK_COMMAND) != keycode_to_key(KVK_RIGHT_COMMAND)
    assert keycode_to_key(KVK_COMMAND) in META_KEYS
    assert keycode_to_key(KVK_RIGHT_COMMAND) in META_KEYS


# Each side-specific modifier keycode paired with its NX_DEVICE* bit (IOLLEvent.h).
_MODIFIER_DEVICE_BITS = [
    (KVK_COMMAND, NX_DEVICELCMDKEYMASK),
    (KVK_RIGHT_COMMAND, NX_DEVICERCMDKEYMASK),
    (KVK_OPTION, NX_DEVICELALTKEYMASK),
    (KVK_RIGHT_OPTION, NX_DEVICERALTKEYMASK),
    (KVK_CONTROL, NX_DEVICELCTLKEYMASK),
    (KVK_RIGHT_CONTROL, NX_DEVICERCTLKEYMASK),
    (KVK_SHIFT, NX_DEVICELSHIFTKEYMASK),
    (KVK_RIGHT_SHIFT, NX_DEVICERSHIFTKEYMASK),
]


@pytest.mark.parametrize(("keycode", "device_bit"), _MODIFIER_DEVICE_BITS)
def test_flags_changed_is_down_when_device_bit_set(keycode: int, device_bit: int) -> None:
    assert flags_changed_action(keycode, device_bit) is KeyAction.KEY_DOWN


@pytest.mark.parametrize(("keycode", "device_bit"), _MODIFIER_DEVICE_BITS)
def test_flags_changed_is_up_when_device_bit_clear(keycode: int, device_bit: int) -> None:
    # Every OTHER bit set: only the queried keycode's own device bit decides,
    # so a release reads KEY_UP even with all other modifiers held.
    flags = 0xFFFFFFFF & ~device_bit
    assert flags_changed_action(keycode, flags) is KeyAction.KEY_UP


def test_releasing_left_side_while_right_side_held_reads_per_side() -> None:
    """Releasing left Command while right Command stays held: the coalesced
    Command group flag stays set, but the left device bit clears — the left
    keycode reads KEY_UP while the right keycode (same flags) reads KEY_DOWN."""
    k_cg_event_flag_mask_command = 0x00100000  # group bit, still set: right side held
    flags = k_cg_event_flag_mask_command | NX_DEVICERCMDKEYMASK
    assert flags_changed_action(KVK_COMMAND, flags) is KeyAction.KEY_UP
    assert flags_changed_action(KVK_RIGHT_COMMAND, flags) is KeyAction.KEY_DOWN


def test_non_modifier_keycodes_yield_none() -> None:
    # Caps lock (0x39) and fn (0x3F) also arrive as kCGEventFlagsChanged but
    # are not combo modifiers — the hook skips them. Non-flagsChanged keys
    # like Escape should never reach this helper; they read None defensively.
    assert flags_changed_action(0x39, 0xFFFFFFFF) is None  # kVK_CapsLock
    assert flags_changed_action(0x3F, 0xFFFFFFFF) is None  # kVK_Function
    assert flags_changed_action(KVK_ESCAPE, 0xFFFFFFFF) is None
