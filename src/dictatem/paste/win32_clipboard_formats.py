"""Win32 clipboard-format classification — pure, no pywin32 (#243).

Turns the format ids ``EnumClipboardFormats`` reports into ``FormatKind``s for
the Clipboard Capture Plan (``clipboard_snapshot.plan_capture``). Lives apart
from the adapter so it is unit-testable on every platform.

Rules (Win32 "Standard Clipboard Formats" + "Synthesized Clipboard Formats"):

* Registered formats (``0xC000``–``0xFFFF``: HTML Format, Rich Text Format, PNG,
  Shell IDList Array, …) are HGLOBAL memory by convention → ``MEMORY``.
* Memory-backed standard formats (text, DIBs, ``CF_HDROP``, ``CF_LOCALE``,
  ``CF_TIFF``/``CF_WAVE``/… ) → ``MEMORY``.
* GDI-handle formats (``CF_BITMAP``, ``CF_PALETTE``, the metafiles, the
  ``CF_GDIOBJ`` range) and the app-private ``CF_PRIVATE`` range (the system
  doesn't even know what those handles are) → ``HANDLE``.
* Owner-display formats (``CF_OWNERDISPLAY``, ``CF_DSP*``) → ``DELAYED``.
* Windows synthesizes the rest of a family from whichever member an app placed,
  and enumerates the placed one *first*. So within the text family
  (``CF_UNICODETEXT``/``CF_TEXT``/``CF_OEMTEXT``) and the DIB family
  (``CF_DIB``/``CF_DIBV5``) the first one enumerated is ``MEMORY`` and later
  members are ``SYNTHESIZED`` — restoring the first lets Windows regenerate them.
* OLE's own bookkeeping formats (``DataObject``, ``Ole Private Data``) describe
  the source app's live ``IDataObject``; once it is gone they are stale and OLE
  rebuilds them from the real formats → ``SYNTHESIZED``. Needs *names*, since
  registered ids differ per session.
* Anything unrecognised is ``HANDLE``: skipped rather than risk misreading it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dictatem.paste.clipboard_snapshot import FormatKind

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

CF_TEXT = 1
CF_BITMAP = 2
CF_METAFILEPICT = 3
CF_SYLK = 4
CF_DIF = 5
CF_TIFF = 6
CF_OEMTEXT = 7
CF_DIB = 8
CF_PALETTE = 9
CF_PENDATA = 10
CF_RIFF = 11
CF_WAVE = 12
CF_UNICODETEXT = 13
CF_ENHMETAFILE = 14
CF_HDROP = 15
CF_LOCALE = 16
CF_DIBV5 = 17
CF_OWNERDISPLAY = 0x0080
CF_DSPTEXT = 0x0081
CF_DSPBITMAP = 0x0082
CF_DSPMETAFILEPICT = 0x0083
CF_DSPENHMETAFILE = 0x008E
_CF_PRIVATEFIRST, _CF_PRIVATELAST = 0x0200, 0x02FF
_CF_GDIOBJFIRST, _CF_GDIOBJLAST = 0x0300, 0x03FF
_REGISTERED_FIRST, _REGISTERED_LAST = 0xC000, 0xFFFF

STANDARD_FORMAT_NAMES: dict[int, str] = {
    CF_TEXT: "CF_TEXT",
    CF_BITMAP: "CF_BITMAP",
    CF_METAFILEPICT: "CF_METAFILEPICT",
    CF_SYLK: "CF_SYLK",
    CF_DIF: "CF_DIF",
    CF_TIFF: "CF_TIFF",
    CF_OEMTEXT: "CF_OEMTEXT",
    CF_DIB: "CF_DIB",
    CF_PALETTE: "CF_PALETTE",
    CF_PENDATA: "CF_PENDATA",
    CF_RIFF: "CF_RIFF",
    CF_WAVE: "CF_WAVE",
    CF_UNICODETEXT: "CF_UNICODETEXT",
    CF_ENHMETAFILE: "CF_ENHMETAFILE",
    CF_HDROP: "CF_HDROP",
    CF_LOCALE: "CF_LOCALE",
    CF_DIBV5: "CF_DIBV5",
    CF_OWNERDISPLAY: "CF_OWNERDISPLAY",
    CF_DSPTEXT: "CF_DSPTEXT",
    CF_DSPBITMAP: "CF_DSPBITMAP",
    CF_DSPMETAFILEPICT: "CF_DSPMETAFILEPICT",
    CF_DSPENHMETAFILE: "CF_DSPENHMETAFILE",
}

_MEMORY_STANDARD = frozenset(
    {
        CF_TEXT,
        CF_SYLK,
        CF_DIF,
        CF_TIFF,
        CF_OEMTEXT,
        CF_DIB,
        CF_PENDATA,
        CF_RIFF,
        CF_WAVE,
        CF_UNICODETEXT,
        CF_HDROP,
        CF_LOCALE,
        CF_DIBV5,
    }
)
_HANDLE_STANDARD = frozenset({CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_ENHMETAFILE})
_OWNER_DISPLAY = frozenset(
    {CF_OWNERDISPLAY, CF_DSPTEXT, CF_DSPBITMAP, CF_DSPMETAFILEPICT, CF_DSPENHMETAFILE}
)
_TEXT_FAMILY = frozenset({CF_UNICODETEXT, CF_TEXT, CF_OEMTEXT})
_DIB_FAMILY = frozenset({CF_DIB, CF_DIBV5})
_OLE_INTERNAL_NAMES = frozenset({"DataObject", "Ole Private Data"})


def is_text_format(format_id: int) -> bool:
    """True for the plain-text formats kept when a snapshot falls back."""
    return format_id in _TEXT_FAMILY


def _base_kind(format_id: int) -> FormatKind:
    if format_id in _MEMORY_STANDARD:
        return FormatKind.MEMORY
    if format_id in _OWNER_DISPLAY:
        return FormatKind.DELAYED
    if format_id in _HANDLE_STANDARD:
        return FormatKind.HANDLE
    if _CF_PRIVATEFIRST <= format_id <= _CF_PRIVATELAST:
        return FormatKind.HANDLE
    if _CF_GDIOBJFIRST <= format_id <= _CF_GDIOBJLAST:
        return FormatKind.HANDLE
    if _REGISTERED_FIRST <= format_id <= _REGISTERED_LAST:
        return FormatKind.MEMORY
    return FormatKind.HANDLE


def classify_win32_formats(
    format_ids: Iterable[int], *, names: Mapping[int, str] | None = None
) -> list[tuple[int, FormatKind]]:
    """Classify enumerated clipboard formats, in enumeration order.

    *names* maps registered format ids to their names (``GetClipboardFormatName``).
    """
    names = names or {}
    seen_text = False
    seen_dib = False
    out: list[tuple[int, FormatKind]] = []
    for fid in format_ids:
        kind = _base_kind(fid)
        if names.get(fid) in _OLE_INTERNAL_NAMES:
            kind = FormatKind.SYNTHESIZED
        elif fid in _TEXT_FAMILY:
            kind = FormatKind.SYNTHESIZED if seen_text else kind
            seen_text = True
        elif fid in _DIB_FAMILY:
            kind = FormatKind.SYNTHESIZED if seen_dib else kind
            seen_dib = True
        out.append((fid, kind))
    return out
