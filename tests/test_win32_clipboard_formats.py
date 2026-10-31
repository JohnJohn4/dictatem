"""Win32 clipboard-format classification — pure, runs on every platform.

Maps the ids ``EnumClipboardFormats`` reports to a ``FormatKind`` so the
Clipboard Capture Plan can decide what to save. Enumeration lists the formats an
app actually placed first and the ones Windows synthesizes from them after.
"""

from __future__ import annotations

from dictatem.paste.clipboard_snapshot import FormatKind
from dictatem.paste.win32_clipboard_formats import (
    CF_BITMAP,
    CF_DIB,
    CF_DIBV5,
    CF_DSPTEXT,
    CF_ENHMETAFILE,
    CF_HDROP,
    CF_LOCALE,
    CF_OEMTEXT,
    CF_OWNERDISPLAY,
    CF_TEXT,
    CF_UNICODETEXT,
    classify_win32_formats,
    is_text_format,
)

_REGISTERED_HTML = 0xC0A1
_PRIVATE = 0x0200
_GDIOBJ = 0x0300


def _kinds(ids: list[int]) -> list[FormatKind]:
    return [kind for _, kind in classify_win32_formats(ids)]


class TestClassifyWin32Formats:
    def test_text_copy_keeps_unicode_and_skips_synthesized_ansi(self) -> None:
        # What a Notepad copy enumerates as (observed on Windows 11).
        ids = [CF_UNICODETEXT, CF_LOCALE, CF_TEXT, CF_OEMTEXT]
        assert _kinds(ids) == [
            FormatKind.MEMORY,
            FormatKind.MEMORY,
            FormatKind.SYNTHESIZED,
            FormatKind.SYNTHESIZED,
        ]

    def test_ansi_only_text_is_real_when_no_unicode(self) -> None:
        assert _kinds([CF_TEXT, CF_LOCALE]) == [FormatKind.MEMORY, FormatKind.MEMORY]

    def test_screenshot_keeps_first_dib_and_skips_bitmap_handle(self) -> None:
        ids = [_REGISTERED_HTML, CF_DIB, CF_BITMAP, CF_DIBV5]
        assert _kinds(ids) == [
            FormatKind.MEMORY,
            FormatKind.MEMORY,
            FormatKind.HANDLE,
            FormatKind.SYNTHESIZED,
        ]

    def test_dibv5_first_means_dib_is_synthesized(self) -> None:
        assert _kinds([CF_DIBV5, CF_DIB]) == [
            FormatKind.MEMORY,
            FormatKind.SYNTHESIZED,
        ]

    def test_bitmap_only_copy_keeps_the_synthesized_dib(self) -> None:
        # An app that placed only CF_BITMAP: Windows offers CF_DIB/CF_DIBV5
        # synthesized after it. The handle can't be captured, so the first DIB
        # is the bytes we keep — restoring it lets Windows re-synthesize the rest.
        assert _kinds([CF_BITMAP, CF_DIB, CF_DIBV5]) == [
            FormatKind.HANDLE,
            FormatKind.MEMORY,
            FormatKind.SYNTHESIZED,
        ]

    def test_explorer_file_drop_is_memory(self) -> None:
        assert _kinds([CF_HDROP]) == [FormatKind.MEMORY]

    def test_handle_based_standard_formats_are_skipped(self) -> None:
        assert _kinds([CF_ENHMETAFILE, _GDIOBJ, _PRIVATE]) == [
            FormatKind.HANDLE,
            FormatKind.HANDLE,
            FormatKind.HANDLE,
        ]

    def test_owner_display_formats_are_delayed(self) -> None:
        assert _kinds([CF_OWNERDISPLAY, CF_DSPTEXT]) == [
            FormatKind.DELAYED,
            FormatKind.DELAYED,
        ]

    def test_registered_formats_are_memory(self) -> None:
        assert _kinds([_REGISTERED_HTML]) == [FormatKind.MEMORY]

    def test_ole_internal_formats_are_synthesized(self) -> None:
        # OLE writes these to describe the source app's live IDataObject. Once
        # that app's object is gone they are stale; OLE re-creates them from the
        # real formats, so restoring them would only mislead OLE readers.
        ole_marker, ole_private, html = 0xC009, 0xC013, 0xC0A1
        names = {ole_marker: "DataObject", ole_private: "Ole Private Data", html: "HTML Format"}
        ids = [ole_marker, html, ole_private]
        kinds = [k for _, k in classify_win32_formats(ids, names=names)]
        assert kinds == [FormatKind.SYNTHESIZED, FormatKind.MEMORY, FormatKind.SYNTHESIZED]

    def test_ids_are_preserved_in_order(self) -> None:
        ids = [_REGISTERED_HTML, CF_UNICODETEXT, CF_HDROP]
        assert [fid for fid, _ in classify_win32_formats(ids)] == ids


class TestIsTextFormat:
    def test_text_formats(self) -> None:
        assert is_text_format(CF_UNICODETEXT)
        assert is_text_format(CF_TEXT)
        assert is_text_format(CF_OEMTEXT)

    def test_non_text_formats(self) -> None:
        assert not is_text_format(CF_DIB)
        assert not is_text_format(CF_LOCALE)
        assert not is_text_format(_REGISTERED_HTML)
