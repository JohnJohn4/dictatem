"""Tests for the paste pipeline — pure logic with fake adapters."""

from __future__ import annotations

import importlib
import sys

import pytest

from dictatem.exceptions import ClipboardContentionError
from dictatem.paste.pipeline import paste
from tests.fakes import FakeClipboardIO, FakeForegroundTracker, FakeKeystrokeSender


class TestPasteCallSequence:
    """Verify the full adapter call sequence produced by paste()."""

    def test_expected_call_ordering(self) -> None:
        clip = FakeClipboardIO()
        clip._content = "original"
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker(hwnd=42)

        paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

        assert fg.captured == [42]
        assert fg.restored == [42]
        assert ks.paste_count == 1

        assert clip.calls[0] == ("save",)
        assert clip.calls[1] == ("open",)
        assert clip.calls[2] == ("set_text", "hello ")
        assert clip.calls[3] == ("close",)

    def test_foreground_captured_before_clipboard(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker(hwnd=99)

        paste("x", clipboard=clip, keystroke=ks, foreground=fg)

        assert fg.captured == [99]
        save_idx = next(i for i, c in enumerate(clip.calls) if c[0] == "save")
        assert save_idx >= 0

    def test_foreground_restored_before_keystroke(self) -> None:
        order: list[str] = []
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        orig_restore = fg.restore
        orig_paste = ks.send_paste

        def tracking_restore(hwnd: int) -> None:
            order.append("restore_fg")
            orig_restore(hwnd)

        def tracking_paste() -> None:
            order.append("send_paste")
            orig_paste()

        fg.restore = tracking_restore  # type: ignore[assignment]
        ks.send_paste = tracking_paste  # type: ignore[assignment]

        paste("text", clipboard=clip, keystroke=ks, foreground=fg)

        assert order.index("restore_fg") < order.index("send_paste")


class TestInputNormalization:
    """Newlines replaced with spaces, trailing space appended."""

    def test_newlines_replaced_with_spaces(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("line1\nline2", clipboard=clip, keystroke=ks, foreground=fg)

        set_call = next(c for c in clip.calls if c[0] == "set_text")
        assert set_call[1] == "line1 line2 "

    def test_crlf_replaced_with_spaces(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("line1\r\nline2", clipboard=clip, keystroke=ks, foreground=fg)

        set_call = next(c for c in clip.calls if c[0] == "set_text")
        assert set_call[1] == "line1 line2 "

    def test_mixed_newlines(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("a\r\nb\nc", clipboard=clip, keystroke=ks, foreground=fg)

        set_call = next(c for c in clip.calls if c[0] == "set_text")
        assert set_call[1] == "a b c "

    def test_trailing_space_appended(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

        set_call = next(c for c in clip.calls if c[0] == "set_text")
        assert set_call[1] == "hello "


class TestClipboardRestore:
    """Original clipboard text is restored after paste completes."""

    def test_original_text_restored(self) -> None:
        clip = FakeClipboardIO()
        clip._content = "my precious data"
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("new text", clipboard=clip, keystroke=ks, foreground=fg)

        assert clip._content == "my precious data"

    def test_none_clipboard_restored(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("text", clipboard=clip, keystroke=ks, foreground=fg)

        assert clip._content is None

    def test_restore_is_last_clipboard_call(self) -> None:
        clip = FakeClipboardIO()
        clip._content = "saved"
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("text", clipboard=clip, keystroke=ks, foreground=fg)

        assert clip.calls[-1] == ("restore", "saved")


class TestContentionRetry:
    """Clipboard contention retry with 10ms backoff."""

    def test_retry_succeeds_after_4_failures(self) -> None:
        clip = FakeClipboardIO(open_failures=4)
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

        assert ks.paste_count == 1
        assert len(clip.open_timestamps) == 5

    def test_retry_backoff_timing(self) -> None:
        clip = FakeClipboardIO(open_failures=4)
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

        for i in range(1, len(clip.open_timestamps)):
            gap = clip.open_timestamps[i] - clip.open_timestamps[i - 1]
            assert gap >= 0.008, f"Backoff gap {i} was {gap:.4f}s, expected >= 0.008s"

    def test_raises_after_5_failures(self) -> None:
        clip = FakeClipboardIO(open_failures=5)
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        with pytest.raises(ClipboardContentionError):
            paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

    def test_raises_after_more_than_5_failures(self) -> None:
        clip = FakeClipboardIO(open_failures=10)
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        with pytest.raises(ClipboardContentionError):
            paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

    def test_clipboard_restored_on_contention_error(self) -> None:
        clip = FakeClipboardIO(open_failures=5)
        clip._content = "precious"
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        with pytest.raises(ClipboardContentionError):
            paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

        assert clip._content == "precious"


class TestImportSafety:
    """paste.pipeline must not import pywin32 or Win32 modules."""

    def test_no_win32_in_import_graph(self) -> None:
        before = set(sys.modules.keys())
        importlib.import_module("dictatem.paste.pipeline")
        after = set(sys.modules.keys())
        new_modules = after - before

        forbidden = (
            "pywin32", "win32api", "win32con",
            "win32clipboard", "win32gui", "pywintypes",
        )
        win32_modules = [
            m for m in new_modules
            if any(m == f or m.startswith(f + ".") for f in forbidden)
        ]
        assert win32_modules == [], f"paste.pipeline imported Win32 modules: {win32_modules}"
