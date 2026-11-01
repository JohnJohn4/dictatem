"""Tests for WHKeyboardLLHook callback logic.

The hook thread and SetWindowsHookEx are never exercised here (see
test_win32_ll_hook for those).  Instead we drive the real hook proc with a
KBDLLHOOKSTRUCT in memory, a fake handler, and a patched CallNextHookEx so we
can assert it is always called.
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
from dictatem.hotkey.win32_keymap import (
    DICTATEM_INJECTION_TAG,
    LLKHF_EXTENDED,
    LLKHF_INJECTED,
)

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


def _make_callback(handler, replay=None):  # type: ignore[no-untyped-def]
    """Build a hook and return its real hook proc, without starting the thread."""
    hook = WHKeyboardLLHook(handler, replay_masked_release=replay)
    return hook._ll_callback, hook


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

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
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

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda vk, action, ts: None)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    mock_u32.CallNextHookEx.assert_called_once()
    assert result != 1, "hook must never suppress"


def test_key_up_calls_next_hook() -> None:
    struct = _make_struct(VK_A)

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda vk, action, ts: None)
        cb(0, WM_KEYUP, ctypes.addressof(struct))

    mock_u32.CallNextHookEx.assert_called_once()


def test_syskeydown_treated_as_keydown() -> None:
    received: list[tuple[int, KeyAction, int]] = []

    def handler(vk: int, action: KeyAction, ts: int) -> None:
        received.append((vk, action, ts))

    struct = _make_struct(VK_LWIN)

    with (
        patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32,
        patch("dictatem.hotkey.wh_keyboard_ll.time.monotonic", return_value=1.234),
    ):
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(handler)
        cb(0, WM_SYSKEYDOWN, ctypes.addressof(struct))

    assert received == [(Key.LEFT_META, KeyAction.KEY_DOWN, 1234)]


def test_negative_ncode_skips_processing_and_calls_next() -> None:
    calls: list = []
    struct = _make_struct(VK_A)

    def handler(vk: int, action: KeyAction, ts: int) -> None:
        calls.append((vk, action, ts))

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
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

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(handler)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    mock_u32.CallNextHookEx.assert_called_once()
    assert result == 0


def test_callback_never_returns_none() -> None:
    """ctypes will pass NULL to Windows if the callback returns None."""
    struct = _make_struct(VK_A)

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda vk, action, ts: None)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    assert result is not None


def test_handler_exception_does_not_suppress_key() -> None:
    """A crashing handler must not accidentally suppress the key (return 1)."""
    handler = MagicMock(side_effect=RuntimeError("boom"))
    struct = _make_struct(VK_A)

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(handler)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    assert result != 1


# ── Menu mask: swallow-and-replay of a lone Alt/Win key-up (#171/#177) ──────


def _run_masked_keyup(replay, *, w_param: int = WM_KEYUP, mask: bool = True):  # type: ignore[no-untyped-def]
    struct = _make_struct(VK_LWIN)
    struct.scanCode = 0x5B
    struct.flags = LLKHF_EXTENDED
    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda vk, action, ts: mask, replay=replay)
        result = cb(0, w_param, ctypes.addressof(struct))
    return result, mock_u32.CallNextHookEx.call_count


def test_masked_keyup_is_replayed_then_swallowed() -> None:
    replays: list[tuple[int, int, int]] = []

    def replay(vk: int, scan: int, flags: int) -> bool:
        replays.append((vk, scan, flags))
        return True

    result, next_calls = _run_masked_keyup(replay)
    # The SAME key-up (vk, scan, extended flag) was re-emitted behind the mask…
    assert replays == [(VK_LWIN, 0x5B, LLKHF_EXTENDED)]
    # …so the original is swallowed (non-zero, no CallNextHookEx).
    assert result == 1
    assert next_calls == 0


@pytest.mark.parametrize(
    "replay_result",
    [False, None, RuntimeError("SendInput blew up")],
    ids=["short-sendinput", "non-bool", "raises"],
)
def test_failed_replay_passes_original_keyup_through(replay_result: object) -> None:
    """Never-stuck: if the key-up wasn't re-emitted, the original goes through."""

    def replay(vk: int, scan: int, flags: int) -> object:
        if isinstance(replay_result, Exception):
            raise replay_result
        return replay_result

    result, next_calls = _run_masked_keyup(replay)
    assert result != 1
    assert next_calls == 1


def test_every_swallowed_keyup_was_re_emitted() -> None:
    """Invariant across all outcomes: swallowed (result 1) <=> a full replay."""
    for outcome in (True, False):
        emitted: list[int] = []

        def replay(
            vk: int,
            scan: int,
            flags: int,
            _ok: bool = outcome,
            _emitted: list[int] = emitted,
        ) -> bool:
            if _ok:
                _emitted.append(vk)
            return _ok

        result, next_calls = _run_masked_keyup(replay)
        swallowed = result == 1 and next_calls == 0
        assert swallowed == (emitted == [VK_LWIN])
        assert swallowed or next_calls == 1


def test_no_replay_when_handler_does_not_ask() -> None:
    replays: list[int] = []
    result, next_calls = _run_masked_keyup(
        lambda vk, s, f: replays.append(vk) or True, mask=False
    )
    assert replays == []
    assert next_calls == 1 and result != 1


def test_key_down_is_never_swallowed_even_if_flagged() -> None:
    replays: list[int] = []
    result, next_calls = _run_masked_keyup(
        lambda vk, s, f: replays.append(vk) or True, w_param=WM_KEYDOWN
    )
    assert replays == []
    assert next_calls == 1 and result != 1


def test_no_replayer_passes_through() -> None:
    result, next_calls = _run_masked_keyup(None)
    assert next_calls == 1 and result != 1


# ── Own injections never reach the classifier (#269 follow-up) ──────────────


def _tagged_struct(vk: int, extra: int | None) -> KBDLLHOOKSTRUCT:
    s = _make_struct(vk)
    s.flags = LLKHF_INJECTED
    if extra is not None:
        s.dwExtraInfo = ctypes.cast(extra, ctypes.POINTER(ctypes.wintypes.ULONG))
    return s


def test_own_tagged_injection_skips_handler_but_passes_through() -> None:
    received: list[object] = []
    struct = _tagged_struct(VK_LCONTROL, DICTATEM_INJECTION_TAG)

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda *a: received.append(a) or True)
        result = cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    assert received == []
    mock_u32.CallNextHookEx.assert_called_once()
    assert result != 1


def test_foreign_injection_still_reaches_handler() -> None:
    received: list[object] = []
    struct = _tagged_struct(VK_LCONTROL, None)

    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        cb, _ = _make_callback(lambda *a: received.append(a) or False)
        cb(0, WM_KEYDOWN, ctypes.addressof(struct))

    assert len(received) == 1


# ── Passive observer feeding the paste rail's input timeline (#269) ─────────


def _observed_run(struct: KBDLLHOOKSTRUCT, w_param: int, observer, handler=None):  # type: ignore[no-untyped-def]
    received: list[object] = []
    with patch("dictatem.hotkey.win32_ll_hook.user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        hook = WHKeyboardLLHook(
            handler or (lambda *a: received.append(a) or False), observe_key=observer
        )
        result = hook._ll_callback(0, w_param, ctypes.addressof(struct))
    return result, mock_u32.CallNextHookEx.call_count, received


def test_observer_sees_user_and_own_events() -> None:
    seen: list[tuple[int, bool, bool]] = []
    _observed_run(_make_struct(VK_LWIN), WM_KEYUP, lambda *a: seen.append(a))
    _observed_run(
        _tagged_struct(VK_LWIN, DICTATEM_INJECTION_TAG), WM_KEYUP, lambda *a: seen.append(a)
    )
    _observed_run(_make_struct(VK_A), WM_SYSKEYDOWN, lambda *a: seen.append(a))
    assert seen == [(VK_LWIN, False, False), (VK_LWIN, False, True), (VK_A, True, False)]


def test_observer_failure_does_not_affect_the_key() -> None:
    def boom(*_a: object) -> None:
        raise RuntimeError("observer blew up")

    result, next_calls, received = _observed_run(_make_struct(VK_A), WM_KEYDOWN, boom)
    assert len(received) == 1  # the classifier still got the key
    assert next_calls == 1 and result != 1
