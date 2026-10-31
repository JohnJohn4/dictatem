"""Smoke test for the Win32 clutter-proof clipboard write (Windows CI only).

The pure marker decision is unit-tested in ``test_clipboard_markers``; this
proves the real pywin32 binding actually works on Windows — ``SetClipboardData``
with a DWORD payload does not raise, the dictation text still round-trips (Ctrl+V
would see it), the user's original is still restored, and both exclusion formats
are present after a dictation-style write. Whether Win+V history *actually* skips
the entry is human manual-QA (ADR-0023 / #138 QA handoff).

Self-cleaning: the runner's real clipboard is saved and restored (best-effort)
around each test via the ``preserve_clipboard`` fixture — so running the suite
does not clobber it, except in the rare case where ~0.8s of sustained clipboard
contention defeats even the teardown restore.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import struct
import sys
import time
from ctypes import wintypes
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

if sys.platform != "win32":
    pytest.skip("win32 clipboard adapter is Windows-only", allow_module_level=True)

import pywintypes  # type: ignore[import-untyped]  # noqa: E402
import win32clipboard  # type: ignore[import-untyped]  # noqa: E402

from dictatem.paste.clipboard_markers import (  # noqa: E402
    CLIPBOARD_EXCLUSION_FORMATS,
)
from dictatem.paste.clipboard_snapshot import ClipboardSnapshot  # noqa: E402
from dictatem.paste.win32_clipboard import Win32ClipboardIO  # noqa: E402


def _open_with_retry() -> None:
    # The Win+V clipboard-history monitor opens the clipboard to read each new
    # write, so an immediate read-back races it and OpenClipboard raises
    # ``Access is denied`` (a pywintypes.error, NOT an OSError). Retry briefly,
    # like the production paste path does.
    for attempt in range(40):
        try:
            win32clipboard.OpenClipboard()
            return
        except pywintypes.error:
            if attempt == 39:
                raise
            time.sleep(0.02)


def _retry_clipboard_op(op: Callable[[], None]) -> None:
    # The adapter's own OpenClipboard (in restore, set_text, etc.) races the same
    # history monitor — retry the whole mutation on contention. The adapter now
    # translates that contention to OSError (#145), so catch OSError here; the raw
    # pywintypes.error is only seen by the raw-win32 `_open_with_retry` above.
    for attempt in range(40):
        try:
            op()
            return
        except OSError:
            if attempt == 39:
                raise
            time.sleep(0.02)


def _read_text() -> str | None:
    _open_with_retry()
    try:
        try:
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            # Collapse empty → None, matching Win32ClipboardIO.save() so the
            # fixture round-trips the runner's clipboard with the same semantics.
            return str(data) if data else None
        except TypeError:
            return None
    finally:
        win32clipboard.CloseClipboard()


def _exclusion_formats_present() -> dict[str, bool]:
    present: dict[str, bool] = {}
    _open_with_retry()
    try:
        for name in CLIPBOARD_EXCLUSION_FORMATS:
            fmt = win32clipboard.RegisterClipboardFormat(name)
            present[name] = bool(win32clipboard.IsClipboardFormatAvailable(fmt))
    finally:
        win32clipboard.CloseClipboard()
    return present


def _put_text(text: str) -> None:
    def write() -> None:
        _open_with_retry()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()

    _retry_clipboard_op(write)


def _save() -> ClipboardSnapshot:
    clip = Win32ClipboardIO()
    result: list[ClipboardSnapshot] = []
    _retry_clipboard_op(lambda: result.append(clip.save()))
    return result[0]


@pytest.fixture
def preserve_clipboard() -> Iterator[None]:
    # The adapter's own full-format snapshot (#243), so a runner's screenshot
    # or file copy survives the suite too.
    saved = _save()
    try:
        yield
    finally:
        # Put the runner's clipboard back exactly as it was. Best-effort: never
        # fail teardown over clipboard contention (the give-up case leaves test
        # text on the clipboard, which the docstring flags).
        clip = Win32ClipboardIO()
        with contextlib.suppress(OSError):
            _retry_clipboard_op(lambda: clip.restore(saved))


class TestClutterProofSetText:
    def test_set_text_round_trips_and_marks(self, preserve_clipboard: None) -> None:
        clip = Win32ClipboardIO()

        def write() -> None:
            clip.open()
            try:
                clip.set_text("dictatem clutter-proof smoke ")
            finally:
                clip.close()

        _retry_clipboard_op(write)
        # Ctrl+V would still paste our text — the markers don't break the write.
        assert _read_text() == "dictatem clutter-proof smoke "
        # Both exclusion markers are present, so Win+V/cloud skip this write.
        present = _exclusion_formats_present()
        assert len(present) == len(CLIPBOARD_EXCLUSION_FORMATS)  # not vacuous
        assert all(present.values()), f"missing exclusion markers: {present}"


class TestClutterProofRestore:
    def test_restore_round_trips_and_marks(self, preserve_clipboard: None) -> None:
        clip = Win32ClipboardIO()
        _put_text("user original text")
        saved = _save()
        _put_text("something else")
        _retry_clipboard_op(lambda: clip.restore(saved))
        # The restored original is readable...
        assert _read_text() == "user original text"
        # ...and itself history/cloud-excluded, so the restore adds no Win+V
        # duplicate of the user's original (the second half of the clutter fix).
        present = _exclusion_formats_present()
        assert len(present) == len(CLIPBOARD_EXCLUSION_FORMATS)  # not vacuous
        assert all(present.values()), f"missing exclusion markers: {present}"

    def test_restore_none_leaves_clipboard_empty(self, preserve_clipboard: None) -> None:
        clip = Win32ClipboardIO()
        _retry_clipboard_op(lambda: clip.restore(ClipboardSnapshot.empty()))
        assert _read_text() is None


# --- Full-format Clipboard Snapshot (#243) ---------------------------------
# Raw clipboard I/O via kernel32 so the test's own writes and reads don't go
# through the adapter under test (or pywin32's bytes-vs-handle guessing).

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_k32.GlobalAlloc.restype = wintypes.HGLOBAL
_k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_k32.GlobalLock.restype = ctypes.c_void_p
_k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_k32.GlobalSize.argtypes = [wintypes.HGLOBAL]
_k32.GlobalSize.restype = ctypes.c_size_t
_GMEM_MOVEABLE = 0x0002


def _put_raw(entries: list[tuple[int, bytes]]) -> None:
    def write() -> None:
        _open_with_retry()
        try:
            win32clipboard.EmptyClipboard()
            for fid, data in entries:
                handle = _k32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
                ptr = _k32.GlobalLock(handle)
                ctypes.memmove(ptr, data, len(data))
                _k32.GlobalUnlock(handle)
                win32clipboard.SetClipboardData(fid, handle)
        finally:
            win32clipboard.CloseClipboard()

    _retry_clipboard_op(write)


def _read_raw(fid: int) -> bytes | None:
    _open_with_retry()
    try:
        if not win32clipboard.IsClipboardFormatAvailable(fid):
            return None
        handle = win32clipboard.GetClipboardDataHandle(fid)
        size = _k32.GlobalSize(handle)
        ptr = _k32.GlobalLock(handle)
        try:
            return ctypes.string_at(ptr, size)
        finally:
            _k32.GlobalUnlock(handle)
    finally:
        win32clipboard.CloseClipboard()


def _formats() -> list[int]:
    _open_with_retry()
    try:
        out: list[int] = []
        fid = 0
        while fid := win32clipboard.EnumClipboardFormats(fid):
            out.append(fid)
        return out
    finally:
        win32clipboard.CloseClipboard()


def _dictate_over(saved: ClipboardSnapshot) -> None:
    """What the paste pipeline does: put dictation text on, then restore."""
    clip = Win32ClipboardIO()

    def write() -> None:
        clip.open()
        try:
            clip.set_text("dictated words ")
        finally:
            clip.close()

    _retry_clipboard_op(write)
    assert _read_text() == "dictated words "
    _retry_clipboard_op(lambda: clip.restore(saved))


def _tiny_dib() -> bytes:
    # BITMAPINFOHEADER (40 bytes) for a 2x2 32-bpp BI_RGB image + 16 pixel bytes.
    header = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 32, 0, 16, 2835, 2835, 0, 0)
    return header + bytes(range(16))


def _dropfiles(paths: list[str]) -> bytes:
    # DROPFILES: pFiles=20, pt=(0,0), fNC=0, fWide=1; then double-NUL wide list.
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    body = "".join(p + "\0" for p in paths) + "\0"
    return header + body.encode("utf-16-le")


class TestFullFormatSnapshot:
    def test_screenshot_dib_survives_a_dictation(self, preserve_clipboard: None) -> None:
        dib = _tiny_dib()
        _put_raw([(win32clipboard.CF_DIB, dib)])
        saved = _save()
        _dictate_over(saved)
        restored = _read_raw(win32clipboard.CF_DIB)
        assert restored is not None
        assert restored[: len(dib)] == dib
        assert all(_exclusion_formats_present().values())

    def test_explorer_file_copy_survives_a_dictation(
        self, preserve_clipboard: None
    ) -> None:
        paths = [r"C:\Windows\notepad.exe", r"C:\Windows\win.ini"]
        _put_raw([(win32clipboard.CF_HDROP, _dropfiles(paths))])
        saved = _save()
        _dictate_over(saved)
        _open_with_retry()
        try:
            files = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
        finally:
            win32clipboard.CloseClipboard()
        assert list(files) == paths

    def test_rich_text_survives_with_formats_in_order(
        self, preserve_clipboard: None
    ) -> None:
        html_fmt = win32clipboard.RegisterClipboardFormat("HTML Format")
        rtf_fmt = win32clipboard.RegisterClipboardFormat("Rich Text Format")
        html = b"Version:0.9\r\nStartHTML:0\r\n<b>bold 12345</b>\0"
        rtf = b"{\rtf1 {\b bold}}\0"
        text = "bold 12345\0".encode("utf-16-le")
        _put_raw([(html_fmt, html), (rtf_fmt, rtf), (win32clipboard.CF_UNICODETEXT, text)])
        saved = _save()
        _dictate_over(saved)
        assert (_read_raw(html_fmt) or b"")[: len(html)] == html
        assert (_read_raw(rtf_fmt) or b"")[: len(rtf)] == rtf
        assert _read_text() == "bold 12345"
        order = [f for f in _formats() if f in (html_fmt, rtf_fmt, win32clipboard.CF_UNICODETEXT)]
        assert order == [html_fmt, rtf_fmt, win32clipboard.CF_UNICODETEXT]

    def test_digit_like_bytes_are_written_as_data_not_a_handle(
        self, preserve_clipboard: None
    ) -> None:
        # pywin32's SetClipboardData reads bytes like b"12345" as a HANDLE; the
        # adapter must write snapshot bytes as data whatever they look like.
        fmt = win32clipboard.RegisterClipboardFormat("dictatem smoke digits")
        _put_raw([(fmt, b"12345")])
        saved = _save()
        _dictate_over(saved)
        assert (_read_raw(fmt) or b"")[:5] == b"12345"

    def test_over_cap_keeps_text_only_and_logs_names_not_content(
        self,
        preserve_clipboard: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        small = Win32ClipboardIO(snapshot_cap_bytes=64)
        html_fmt = win32clipboard.RegisterClipboardFormat("HTML Format")
        secret = b"<p>" + b"top secret html " * 8 + b"</p>\0"
        text = "keep me\0".encode("utf-16-le")
        _put_raw([(html_fmt, secret), (win32clipboard.CF_UNICODETEXT, text)])
        result: list[ClipboardSnapshot] = []
        with caplog.at_level(logging.WARNING):
            _retry_clipboard_op(lambda: result.append(small.save()))
        _dictate_over(result[0])
        assert _read_text() == "keep me"
        assert _read_raw(html_fmt) is None
        assert "HTML Format" in caplog.text
        assert "top secret" not in caplog.text

    def test_stops_measuring_non_text_once_over_cap(
        self,
        preserve_clipboard: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Like the mac adapter: once the bytes measured pass the cap, later
        # non-text formats are not read (no needless delayed renders).
        small = Win32ClipboardIO(snapshot_cap_bytes=64)
        big_fmt = win32clipboard.RegisterClipboardFormat("dictatem smoke big")
        late_fmt = win32clipboard.RegisterClipboardFormat("dictatem smoke late")
        text = "keep me\0".encode("utf-16-le")
        _put_raw([
            (big_fmt, b"x" * 200),
            (late_fmt, b"late"),
            (win32clipboard.CF_UNICODETEXT, text),
        ])
        result: list[ClipboardSnapshot] = []
        with caplog.at_level(logging.WARNING):
            _retry_clipboard_op(lambda: result.append(small.save()))
        assert "dictatem smoke late=unmeasured" in caplog.text
        _dictate_over(result[0])
        assert _read_text() == "keep me"
        assert _read_raw(late_fmt) is None

    def test_empty_clipboard_round_trips_empty(self, preserve_clipboard: None) -> None:
        _put_raw([])
        saved = _save()
        assert saved.is_empty
        _dictate_over(saved)
        assert _formats() == []
