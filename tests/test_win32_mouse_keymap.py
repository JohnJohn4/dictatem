"""Tests for the pure Windows mouse-message → neutral (Key, KeyAction) map.

ADR-0020: the X1/X2 side buttons and the wheel click are trigger inputs;
left/right click, movement, and the wheel are not. The hook reports the event
kind in its ``wParam`` and the side button in the high word of ``mouseData``.
"""

from __future__ import annotations

import pytest

from dictatem.hotkey.classifier import Key, KeyAction
from dictatem.hotkey.win32_mouse_keymap import (
    WM_MBUTTONDOWN,
    WM_MBUTTONUP,
    WM_XBUTTONDOWN,
    WM_XBUTTONUP,
    XBUTTON1,
    XBUTTON2,
    mouse_event_to_key,
)

# Codes that are never trigger inputs (left/right click, move, wheel).
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A


class TestSideButtons:
    def test_xbutton1_down_is_mouse4_down(self) -> None:
        assert mouse_event_to_key(WM_XBUTTONDOWN, XBUTTON1) == (
            Key.MOUSE_4,
            KeyAction.KEY_DOWN,
        )

    def test_xbutton1_up_is_mouse4_up(self) -> None:
        assert mouse_event_to_key(WM_XBUTTONUP, XBUTTON1) == (
            Key.MOUSE_4,
            KeyAction.KEY_UP,
        )

    def test_xbutton2_down_is_mouse5_down(self) -> None:
        assert mouse_event_to_key(WM_XBUTTONDOWN, XBUTTON2) == (
            Key.MOUSE_5,
            KeyAction.KEY_DOWN,
        )

    def test_xbutton2_up_is_mouse5_up(self) -> None:
        assert mouse_event_to_key(WM_XBUTTONUP, XBUTTON2) == (
            Key.MOUSE_5,
            KeyAction.KEY_UP,
        )

    def test_unknown_xbutton_is_none(self) -> None:
        # XBUTTON3+ are not deliverable via WH_MOUSE_LL anyway; never a trigger.
        assert mouse_event_to_key(WM_XBUTTONDOWN, 0x0003) is None
        assert mouse_event_to_key(WM_XBUTTONUP, 0x0000) is None


class TestMiddleButton:
    def test_mbutton_down_is_middle_down(self) -> None:
        # The side-button discriminator is ignored for the middle button.
        assert mouse_event_to_key(WM_MBUTTONDOWN, 0) == (
            Key.MOUSE_MIDDLE,
            KeyAction.KEY_DOWN,
        )

    def test_mbutton_up_is_middle_up(self) -> None:
        assert mouse_event_to_key(WM_MBUTTONUP, 0) == (
            Key.MOUSE_MIDDLE,
            KeyAction.KEY_UP,
        )


class TestNonTriggerEvents:
    @pytest.mark.parametrize(
        "message",
        [
            WM_MOUSEMOVE,
            WM_LBUTTONDOWN,
            WM_LBUTTONUP,
            WM_RBUTTONDOWN,
            WM_RBUTTONUP,
            WM_MOUSEWHEEL,
        ],
    )
    def test_non_trigger_messages_map_to_none(self, message: int) -> None:
        assert mouse_event_to_key(message, 0) is None

    def test_left_click_never_triggers_even_with_xbutton_bits_set(self) -> None:
        # A stray high word on a left-click message must not be misread as X1/X2.
        assert mouse_event_to_key(WM_LBUTTONDOWN, XBUTTON1) is None
