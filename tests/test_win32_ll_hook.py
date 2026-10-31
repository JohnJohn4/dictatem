"""Tests for the shared low-level hook plumbing of both Windows hooks (#245).

``SetWindowsHookExW`` / ``UnhookWindowsHookEx`` are always patched — no real
global hook is ever installed. The hook thread and its message loop are real,
though: the uninstall test proves a posted ``WM_QUIT`` makes the real
``GetMessageW`` loop return and the thread exit.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows low-level hooks are Windows-only", allow_module_level=True)

from dictatem.hotkey import win32_ll_hook
from dictatem.hotkey.classifier import HookDecision
from dictatem.hotkey.wh_keyboard_ll import WH_KEYBOARD_LL, WHKeyboardLLHook
from dictatem.hotkey.wh_mouse_ll import WH_MOUSE_LL, WHMouseLLHook

ERROR_ACCESS_DENIED = 5

HookFactory = Callable[[Callable[[int], None] | None], Any]


def _keyboard(on_failed: Callable[[int], None] | None) -> WHKeyboardLLHook:
    return WHKeyboardLLHook(lambda key, action, ts: False, on_install_failed=on_failed)


def _mouse(on_failed: Callable[[int], None] | None) -> WHMouseLLHook:
    return WHMouseLLHook(
        lambda key, action, ts: HookDecision.PASS_THROUGH, on_install_failed=on_failed
    )


BOTH_HOOKS = pytest.mark.parametrize(
    ("make_hook", "hook_id"),
    [(_keyboard, WH_KEYBOARD_LL), (_mouse, WH_MOUSE_LL)],
    ids=["keyboard", "mouse"],
)


@BOTH_HOOKS
def test_null_install_is_logged_with_os_error_and_reported(
    make_hook: HookFactory, hook_id: int, caplog: pytest.LogCaptureFixture
) -> None:
    failures: list[int] = []
    hook = make_hook(failures.append)
    with (
        patch.object(win32_ll_hook.user32, "SetWindowsHookExW", return_value=None) as s,
        patch.object(win32_ll_hook, "_last_error", return_value=ERROR_ACCESS_DENIED),
        caplog.at_level(logging.ERROR),
    ):
        hook.install()
        hook.uninstall()  # joins the (already exiting) hook thread

    assert s.call_args.args[0] == hook_id
    assert failures == [ERROR_ACCESS_DENIED]
    assert "SetWindowsHookExW" in caplog.text
    assert f"OS error {ERROR_ACCESS_DENIED}" in caplog.text
    assert not hook.is_running()


@BOTH_HOOKS
def test_failure_callback_error_is_contained(
    make_hook: HookFactory, hook_id: int
) -> None:
    hook = make_hook(MagicMock(side_effect=RuntimeError("boom")))
    with (
        patch.object(win32_ll_hook.user32, "SetWindowsHookExW", return_value=None),
        patch.object(win32_ll_hook, "_last_error", return_value=ERROR_ACCESS_DENIED),
    ):
        hook.install()
        hook.uninstall()
    assert not hook.is_running()


@BOTH_HOOKS
def test_uninstall_exits_the_hook_thread_and_unhooks(
    make_hook: HookFactory, hook_id: int
) -> None:
    failures: list[int] = []
    hook = make_hook(failures.append)
    with (
        patch.object(win32_ll_hook.user32, "SetWindowsHookExW", return_value=0xBEEF),
        patch.object(
            win32_ll_hook.user32, "UnhookWindowsHookEx", return_value=1
        ) as unhook,
    ):
        hook.install()
        assert hook.is_running()
        hook.uninstall()

    assert not hook.is_running()
    unhook.assert_called_once_with(0xBEEF)
    assert failures == []


@BOTH_HOOKS
def test_uninstall_without_install_is_a_noop(
    make_hook: HookFactory, hook_id: int
) -> None:
    hook = make_hook(None)
    hook.uninstall()
    assert not hook.is_running()


def test_set_windows_hook_returns_a_pointer_sized_handle() -> None:
    # A c_int restype truncates a 64-bit HHOOK; NULL must come back as None.
    import ctypes

    assert win32_ll_hook.user32.SetWindowsHookExW.restype is ctypes.c_void_p
    assert win32_ll_hook.user32.UnhookWindowsHookEx.argtypes == [ctypes.c_void_p]


@BOTH_HOOKS
def test_proc_chains_with_a_null_handle_so_there_is_no_first_event_race(
    make_hook: HookFactory, hook_id: int
) -> None:
    # The proc must not depend on a handle the installing thread may not have
    # stored yet; CallNextHookEx ignores hhk, so NULL is always correct.
    hook = make_hook(None)
    with patch.object(win32_ll_hook.user32, "CallNextHookEx", return_value=0) as nxt:
        hook._ll_callback(-1, 0, 0)  # n_code < 0: chain without processing
    nxt.assert_called_once_with(None, -1, 0, 0)
