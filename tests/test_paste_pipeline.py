"""Tests for the paste pipeline — pure logic with fake adapters."""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING

import pytest

from dictatem.exceptions import ClipboardContentionError
from dictatem.paste.pipeline import _RETRY_DELAY_S, paste
from tests.fakes import FakeClipboardIO, FakeForegroundTracker, FakeKeystrokeSender

if TYPE_CHECKING:
    from collections.abc import Callable


class TestPasteCallSequence:
    """Verify the full adapter call sequence produced by paste()."""

    def test_expected_call_ordering(self) -> None:
        clip = FakeClipboardIO()
        clip._content = "original"
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker(target_id=42)

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
        fg = FakeForegroundTracker(target_id=99)

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

        def tracking_restore(target_id: int) -> None:
            order.append("restore_fg")
            orig_restore(target_id)

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

    def test_leading_whitespace_stripped(self) -> None:
        """faster-whisper prefixes a space; consecutive pastes must not double up."""
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste(" hello world", clipboard=clip, keystroke=ks, foreground=fg)

        set_call = next(c for c in clip.calls if c[0] == "set_text")
        assert set_call[1] == "hello world "


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


class TestDeferredRestore:
    """With a scheduler, the clipboard restore is deferred off-thread (#66).

    The synchronous settle restores before the target's async Ctrl+V lands on
    slow/secured machines, pasting the OLD clipboard. Deferring the restore
    lets the target read our text first.
    """

    def test_restore_deferred_until_scheduled_callback_fires(self) -> None:
        clip = FakeClipboardIO()
        clip._content = "precious"
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()
        scheduled: list[tuple[float, Callable[[], None]]] = []

        paste(
            "new",
            clipboard=clip,
            keystroke=ks,
            foreground=fg,
            schedule_restore=lambda d, c: scheduled.append((d, c)),
        )

        # Ctrl+V was sent, but the restore is deferred — our text is still on
        # the clipboard for the target to read.
        assert ks.paste_count == 1
        assert clip._content == "new "
        assert ("restore", "precious") not in clip.calls
        assert len(scheduled) == 1
        delay_s, callback = scheduled[0]
        assert delay_s > 0

        # Firing the scheduled callback performs the restore.
        callback()
        assert clip._content == "precious"
        assert clip.calls[-1] == ("restore", "precious")

    def test_typed_path_ignores_scheduler(self) -> None:
        clip = FakeClipboardIO()
        clip._content = "precious"
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()
        scheduled: list[tuple[float, Callable[[], None]]] = []

        paste(
            "new",
            clipboard=clip,
            keystroke=ks,
            foreground=fg,
            replace_chars=4,
            schedule_restore=lambda d, c: scheduled.append((d, c)),
        )

        # The typed path never touches the clipboard, so nothing is scheduled.
        assert clip.calls == []
        assert scheduled == []
        assert ks.typed_texts == ["new "]


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
        delays: list[float] = []

        paste("hello", clipboard=clip, keystroke=ks, foreground=fg, sleep=delays.append)

        # 4 failed opens before success → 4 backoff sleeps, each the configured
        # delay. Asserting the *requested* delays (not measured wall-clock gaps)
        # keeps this deterministic on coarse CI timers — the previous wall-clock
        # assertion flaked on Windows runners where the gap rounded to 0.0s.
        assert delays == [_RETRY_DELAY_S] * 4

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

    def test_restore_oserror_is_swallowed_not_raised(self) -> None:
        # When restore() loses the race against the target's Ctrl+V
        # handler, OpenClipboard raises Access-denied. We must swallow
        # it: that outcome is *correct* (the target reads the new text
        # we put on the clipboard). Retrying would put the old text
        # back before the target reads, breaking the paste — see #23.
        clip = FakeClipboardIO(restore_failures=1)
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

        assert ks.paste_count == 1
        assert len(clip.restore_timestamps) == 1  # attempted once, no retry


class TestReplaceChars:
    """replace_chars > 0 takes the typed-replacement path: no clipboard, no Ctrl+V.

    See #23 — the clipboard+Ctrl+V path races the target window's paste handler
    when backspaces queue ahead of Ctrl+V. Typing via send_text sidesteps the
    whole clipboard mechanism for the Trigger Fire case.
    """

    def test_default_zero_uses_clipboard_paste_path(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("hello", clipboard=clip, keystroke=ks, foreground=fg)

        assert ks.total_backspaces == 0
        assert ks.paste_count == 1
        assert ks.typed_texts == []
        # Clipboard path: save + open + set + close + restore.
        assert any(c[0] == "set_text" for c in clip.calls)

    def test_positive_replace_sends_backspaces_and_types_text(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("new", clipboard=clip, keystroke=ks, foreground=fg, replace_chars=7)

        assert ks.backspace_counts == [7]
        assert ks.typed_texts == ["new "]
        assert ks.paste_count == 0  # no Ctrl+V on the typed path

    def test_positive_replace_does_not_touch_clipboard(self) -> None:
        # The whole point of the refactor: typed path leaves clipboard alone.
        clip = FakeClipboardIO()
        clip._content = "user's precious clipboard"
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("new", clipboard=clip, keystroke=ks, foreground=fg, replace_chars=4)

        assert clip.calls == []  # no save/open/set/close/restore
        assert clip._content == "user's precious clipboard"

    def test_backspaces_before_typed_text(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste("new", clipboard=clip, keystroke=ks, foreground=fg, replace_chars=3)

        assert ks.events == [("backspaces", 3), ("send_text", "new ")]

    def test_foreground_restored_before_backspaces(self) -> None:
        """Otherwise the backspaces hit whatever stole focus during transcription."""
        order: list[str] = []
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker(target_id=42)

        orig_restore = fg.restore
        orig_back = ks.send_backspaces

        def tracking_restore(target_id: int) -> None:
            order.append("restore_fg")
            orig_restore(target_id)

        def tracking_back(n: int) -> None:
            order.append("backspaces")
            orig_back(n)

        fg.restore = tracking_restore  # type: ignore[assignment]
        ks.send_backspaces = tracking_back  # type: ignore[assignment]

        paste("x", clipboard=clip, keystroke=ks, foreground=fg, replace_chars=5)

        assert order.index("restore_fg") < order.index("backspaces")

    def test_typed_text_is_normalized(self) -> None:
        # Same normalisation as the clipboard path so LastPaste char counts
        # line up across consecutive trigger fires.
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste(" line1\nline2", clipboard=clip, keystroke=ks, foreground=fg, replace_chars=5)

        assert ks.typed_texts == ["line1 line2 "]

    def test_negative_replace_treated_as_zero(self) -> None:
        clip = FakeClipboardIO()
        ks = FakeKeystrokeSender()
        fg = FakeForegroundTracker()

        paste(
            "x",
            clipboard=clip,
            keystroke=ks,
            foreground=fg,
            replace_chars=-3,
        )

        # Falls through to the regular clipboard+Ctrl+V path.
        assert ks.total_backspaces == 0
        assert ks.paste_count == 1
        assert ks.typed_texts == []


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
