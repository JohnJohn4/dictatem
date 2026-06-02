"""Tests for WHKeyboardLLHook callback logic.

The hook thread and SetWindowsHookEx are never exercised here — those require
a real Windows message loop and elevated context.  Instead we extract the
callback behaviour by driving a real KBDLLHOOKSTRUCT in memory, using a fake
handler, and patching CallNextHookEx so we can assert it is always called.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("wh_keyboard_ll is Windows-only", allow_module_level=True)

from dictatem.hotkey.classifier import Key, KeyAction
from dictatem.hotkey.wh_keyboard_ll import (
    _LPARAM,
    _WPARAM,
    KBDLLHOOKSTRUCT,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_SYSKEYDOWN,
    WHKeyboardLLHook,
)
from dictatem.hotkey.win32_keymap import vk_to_key

VK_A = 0x41
VK_LCONTROL = 0xA2
VK_LWIN = 0x5B


def _make_struct(vk: int, time: int = 1000) -> KBDLLHOOKSTRUCT:
    s = KBDLLHOOKSTRUCT()
    s.vkCode = vk
    s.scanCode = 0
    s.flags = 0
    s.time = time
    return s


def _make_callback(handler):  # type: ignore[no-untyped-def]
    """Build a hook and extract its callback without starting the hook thread."""
    hook = WHKeyboardLLHook(handler)

    captured: dict[str, object] = {}

    def fake_run_hook() -> None:
        from dictatem.hotkey.classifier import KeyAction

        def _ll_callback(n_code: int, w_param: int, l_param: int) -> int:
            try:
                if n_code >= 0:
                    kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    vk = kb.vkCode
                    is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    action = KeyAction.KEY_DOWN if is_down else KeyAction.KEY_UP
                    timestamp_ms = kb.time
                    handler(vk_to_key(vk), action, timestamp_ms)
            except Exception:
                pass
            from dictatem.hotkey import wh_keyboard_ll as _mod
            return _mod.user32.CallNextHookEx(hook._hook_handle, n_code, w_param, l_param)

        captured["cb"] = _ll_callback

    hook._run_hook = fake_run_hook  # type: ignore[method-assign]
    fake_run_hook()
    return captured["cb"], hook


# ── Type safety ──────────────────────────────────────────────────────────────


def test_wparam_is_pointer_sized() -> None:
    assert ctypes.sizeof(_WPARAM) == ctypes.sizeof(ctypes.c_void_p)


def test_lparam_is_pointer_sized() -> None:
    assert ctypes.sizeof(_LPARAM) == ctypes.sizeof(ctypes.c_void_p)


def test_large_64bit_lparam_does_not_overflow() -> None:
    """A pointer value above 2^31 must not raise OverflowError."""
    struct = _make_struct(VK_A)

    large_ptr = ctypes.c_ssize_t(ctypes.addressof(struct)).value
    assert large_ptr != 0

    with patch("dictatem.hotkey.wh_keyboard_ll.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0

        called_with: list[tuple] = []

        def fake_next(hhk, n_code, w_param, l_param):  # type: ignore[no-untyped-def]
            called_with.append((hhk, n_code, w_param, l_param))
            return 0

        mock_u32.CallNextHookEx.side_effect = fake_next

        cb, _ = _make_callback(lambda vk, action, ts: None)
        # Should not raise
        cb(0, WM_KEYDOWN, ctypes.addressof(struct))
        assert len(called_with) == 1


# ── Pass-through behaviour ───────────────────────────────────────────────────


def test_key_down_calls_next_hook() -> None:
    struct = _make_struct(VK_A)

    with patch("dictatem.hotkey.wh_keyboard_ll.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda vk, action, ts: None)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    mock_u32.CallNextHookEx.assert_called_once()
    assert result != 1, "hook must never suppress"


def test_key_up_calls_next_hook() -> None:
    struct = _make_struct(VK_A)

    with patch("dictatem.hotkey.wh_keyboard_ll.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda vk, action, ts: None)
        cb(0, WM_KEYUP, ctypes.addressof(struct))

    mock_u32.CallNextHookEx.assert_called_once()


def test_syskeydown_treated_as_keydown() -> None:
    received: list[tuple[int, KeyAction, int]] = []

    def handler(vk: int, action: KeyAction, ts: int) -> None:
        received.append((vk, action, ts))

    struct = _make_struct(VK_LWIN, time=1234)

    with patch("dictatem.hotkey.wh_keyboard_ll.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(handler)
        cb(0, WM_SYSKEYDOWN, ctypes.addressof(struct))

    assert received == [(Key.LEFT_META, KeyAction.KEY_DOWN, 1234)]


def test_negative_ncode_skips_processing_and_calls_next() -> None:
    calls: list = []
    struct = _make_struct(VK_A)

    def handler(vk: int, action: KeyAction, ts: int) -> None:
        calls.append((vk, action, ts))

    with patch("dictatem.hotkey.wh_keyboard_ll.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(handler)
        cb(-1, WM_KEYDOWN, ctypes.addressof(struct))

    assert calls == [], "handler must not be called when n_code < 0"
    mock_u32.CallNextHookEx.assert_called_once()


# ── Safety: keyboard must never be lost ─────────────────────────────────────


def test_handler_exception_still_calls_next_hook() -> None:
    """If the handler crashes, CallNextHookEx must still be called.

    Without this guarantee, a bug in application code would brick the
    system keyboard until the process is killed.
    """
    handler = MagicMock(side_effect=RuntimeError("boom"))
    struct = _make_struct(VK_A)

    with patch("dictatem.hotkey.wh_keyboard_ll.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(handler)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    mock_u32.CallNextHookEx.assert_called_once()
    assert result == 0


def test_callback_never_returns_none() -> None:
    """ctypes will pass NULL to Windows if the callback returns None."""
    struct = _make_struct(VK_A)

    with patch("dictatem.hotkey.wh_keyboard_ll.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda vk, action, ts: None)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    assert result is not None


def test_handler_exception_does_not_suppress_key() -> None:
    """A crashing handler must not accidentally suppress the key (return 1)."""
    handler = MagicMock(side_effect=RuntimeError("boom"))
    struct = _make_struct(VK_A)

    with patch("dictatem.hotkey.wh_keyboard_ll.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(handler)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    assert result != 1
