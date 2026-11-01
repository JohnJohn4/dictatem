"""Win32 keystroke adapter: Ctrl+V batch, replay timeline, diagnostics (#269).

SendInput is patched out — nothing is ever injected into the real desktop, and
no thread is ever attached (the thread-key read is patched too).
"""

from __future__ import annotations

import logging
import sys
from typing import Any
from unittest.mock import patch

import pytest

if sys.platform != "win32":
    pytest.skip("win32_keystroke is Windows-only", allow_module_level=True)

from dictatem.hotkey.win32_keymap import DICTATEM_INJECTION_TAG, VK_MENU_MASK
from dictatem.paste import win32_keystroke as wk

_MOD = "dictatem.paste.win32_keystroke"


def _layout(inputs: Any) -> list[tuple[int, bool]]:
    return [(i.ki.wVk, bool(i.ki.dwFlags & wk.KEYEVENTF_KEYUP)) for i in inputs]


class _SyncThread:
    """Stand-in for threading.Thread that runs the target inline on start()."""

    def __init__(self, target: Any, args: tuple[Any, ...], **_kw: Any) -> None:
        self._target, self._args = target, args

    def start(self) -> None:
        self._target(*self._args)


def test_paste_batch_leads_with_the_signed_no_op_key() -> None:
    batch = wk.paste_batch()
    assert _layout(batch) == [
        (VK_MENU_MASK, False),
        (VK_MENU_MASK, True),
        (wk.VK_CONTROL, False),
        (wk.VK_V, False),
        (wk.VK_V, True),
        (wk.VK_CONTROL, True),
    ]
    for inp in batch:
        assert wk.ctypes.cast(inp.ki.dwExtraInfo, wk.ctypes.c_void_p).value == (
            DICTATEM_INJECTION_TAG
        )


def test_send_paste_dispatches_one_six_event_batch() -> None:
    ks = wk.Win32KeystrokeSender()
    batches: list[list[tuple[int, bool]]] = []

    def fake_send(inputs: Any) -> int:
        batches.append(_layout(inputs))
        return len(inputs)

    with patch(f"{_MOD}._send_input", side_effect=fake_send):
        ks.send_paste()
    assert len(batches) == 1 and len(batches[0]) == 6
    assert ks._sends == [(6, 6)]


def test_masked_release_marks_replay_pending_and_failure_clears_it() -> None:
    ks = wk.Win32KeystrokeSender()
    with patch(f"{_MOD}._send_input", return_value=3):
        assert ks.send_masked_release(0xA4, 0x38, 0) is True
    assert ks.timeline.view().replay_pending
    ks.observe_hook_key(0xA4, False, True)  # the replayed key-up comes back
    assert not ks.timeline.view().replay_pending

    with patch(f"{_MOD}._send_input", return_value=1):
        assert ks.send_masked_release(0x5B, 0x5B, 1) is False
    assert not ks.timeline.view().replay_pending


def test_report_injection_logs_one_line_without_text(caplog: pytest.LogCaptureFixture) -> None:
    ks = wk.Win32KeystrokeSender()
    ks._sends = [(6, 6)]
    with (
        patch(f"{_MOD}.threading.Thread", _SyncThread),
        patch(f"{_MOD}.THREAD_KEYS_DELAY_S", 0),
        patch(f"{_MOD}._read_thread_keys", return_value=("alt",)),
        caplog.at_level(logging.INFO, logger=_MOD),
    ):
        ks.report_injection(wk._user32.GetForegroundWindow() or 0, "paste")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Paste diag")]
    assert len(lines) == 1
    assert " thread_keys(+0ms)=alt " in lines[0]
    assert lines[0].endswith(" sendinput=6/6")
    assert ks._sends == []


def test_report_injection_never_raises(caplog: pytest.LogCaptureFixture) -> None:
    ks = wk.Win32KeystrokeSender()
    with (
        patch(f"{_MOD}._gui_thread_info", side_effect=OSError("boom")),
        caplog.at_level(logging.DEBUG, logger=_MOD),
    ):
        ks.report_injection(123, "paste")
    assert any(
        r.levelno == logging.DEBUG and "diagnostics" in r.getMessage() for r in caplog.records
    )


def test_thread_read_failure_still_logs_the_line(caplog: pytest.LogCaptureFixture) -> None:
    ks = wk.Win32KeystrokeSender()
    with (
        patch(f"{_MOD}.threading.Thread", _SyncThread),
        patch(f"{_MOD}.THREAD_KEYS_DELAY_S", 0),
        patch(f"{_MOD}._read_thread_keys", side_effect=OSError("attach")),
        caplog.at_level(logging.INFO, logger=_MOD),
    ):
        ks.report_injection(0, "trigger-fire")
    assert any(" thread_keys(+0ms)=? " in r.getMessage() for r in caplog.records)


def test_thread_read_refuses_own_or_missing_thread() -> None:
    assert wk._read_thread_keys(0) is None
    assert wk._read_thread_keys(wk._kernel32.GetCurrentThreadId()) is None


def test_clipboard_format_names_reads_without_opening() -> None:
    names = wk._clipboard_format_names()
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)
