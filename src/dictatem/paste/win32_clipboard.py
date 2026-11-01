"""Win32 clipboard adapter — requires pywin32.

``save``/``restore`` round-trip a full-format Clipboard Snapshot (#243): every
format ``EnumClipboardFormats`` offers is classified
(``win32_clipboard_formats``), sized, run through the pure Clipboard Capture
Plan (``clipboard_snapshot``), and the planned ones are copied out as raw
HGLOBAL bytes. Restore writes the bytes back in the same order through fresh
``GlobalAlloc`` blocks — never through pywin32's ``SetClipboardData(fmt,
bytes)``, which mistakes digit-like bytes such as ``b"12345"`` for a handle.
"""

from __future__ import annotations

import ctypes
import logging
import time
from contextlib import contextmanager
from ctypes import wintypes
from typing import TYPE_CHECKING

import pywintypes  # type: ignore[import-untyped]
import win32clipboard  # type: ignore[import-untyped]

from dictatem.paste.clipboard_markers import apply_exclusion_markers
from dictatem.paste.clipboard_snapshot import (
    SNAPSHOT_SIZE_CAP_BYTES,
    ClipboardSnapshot,
    FormatKind,
    OfferedFormat,
    plan_capture,
)
from dictatem.paste.win32_clipboard_formats import (
    STANDARD_FORMAT_NAMES,
    classify_win32_formats,
    is_text_format,
)

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterator

logger = logging.getLogger(__name__)

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalSize.restype = ctypes.c_size_t
_GMEM_MOVEABLE = 0x0002

# Sizing a format makes a delayed-render owner (e.g. Excel) render it, which can
# be slow. Past this budget the remaining non-text formats go unmeasured, and the
# Capture Plan falls back to text-only rather than stall the paste.
_PROBE_BUDGET_S = 0.5


@contextmanager
def _contention_as_oserror() -> Iterator[None]:
    """Re-raise pywin32's ``pywintypes.error`` as ``OSError`` (#145).

    ``win32clipboard.OpenClipboard`` raises ``pywintypes.error`` (e.g. winerror 5,
    "Access is denied") when another process holds the clipboard — most often the
    Win+V history monitor racing us right after a write. ``pywintypes.error`` is
    **not** an ``OSError`` subclass, so the pure paste pipeline's ``except OSError``
    retry (``open``) and swallow (deferred ``restore``) would never engage.
    Translating at this adapter boundary keeps pywin32 out of the pure pipeline and
    lets the ``OSError``-raising ``FakeClipboardIO`` stay a faithful stand-in.

    Applied to *every* clipboard op, not only the two the pipeline guards, so the
    adapter never leaks a ``pywintypes.error`` — a uniform contract that also lets
    the Windows smoke test retry a single exception type. The original pywin32
    error is chained (``from exc``) and its repr embedded in the message, so the
    winerror/strerror stay available for diagnosis (on ``__cause__`` and in the
    string) even though a plain ``OSError`` carries no ``.winerror`` of its own.
    """
    try:
        yield
    except pywintypes.error as exc:
        raise OSError(f"win32 clipboard contention: {exc}") from exc


def _format_name(fid: int) -> str:
    name = STANDARD_FORMAT_NAMES.get(fid)
    if name is not None:
        return name
    try:
        return str(win32clipboard.GetClipboardFormatName(fid))
    except pywintypes.error:
        return f"format {fid}"


def _enumerate_formats() -> list[int]:
    ids: list[int] = []
    fid = 0
    while fid := win32clipboard.EnumClipboardFormats(fid):
        ids.append(fid)
    return ids


def _global_handle(fid: int) -> int | None:
    """The format's HGLOBAL, or None if it has none to read."""
    try:
        handle = int(win32clipboard.GetClipboardDataHandle(fid))
    except pywintypes.error:
        return None  # e.g. a delayed-render owner that failed to render
    return handle or None


def _read_global(handle: int, size: int) -> bytes | None:
    ptr = _kernel32.GlobalLock(handle)
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        _kernel32.GlobalUnlock(handle)


def _write_global(fid: int, data: bytes) -> None:
    """``SetClipboardData`` *data* as a fresh HGLOBAL (clipboard must be open)."""
    handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, max(len(data), 1))
    if not handle:
        msg = f"GlobalAlloc failed for {len(data)} bytes"
        raise MemoryError(msg)
    ptr = _kernel32.GlobalLock(handle)
    if not ptr:
        _kernel32.GlobalFree(handle)
        msg = "GlobalLock failed"
        raise MemoryError(msg)
    ctypes.memmove(ptr, data, len(data))
    _kernel32.GlobalUnlock(handle)
    try:
        win32clipboard.SetClipboardData(fid, handle)
    except pywintypes.error:
        # The system takes ownership of the block only on success.
        _kernel32.GlobalFree(handle)
        raise


class Win32ClipboardIO:
    def __init__(self, *, snapshot_cap_bytes: int = SNAPSHOT_SIZE_CAP_BYTES) -> None:
        self._snapshot_cap_bytes = snapshot_cap_bytes

    def open(self) -> None:
        with _contention_as_oserror():
            win32clipboard.OpenClipboard()

    def close(self) -> None:
        with _contention_as_oserror():
            win32clipboard.CloseClipboard()

    def save(self) -> ClipboardSnapshot:
        with _contention_as_oserror():
            win32clipboard.OpenClipboard()
            try:
                return self._capture()
            finally:
                win32clipboard.CloseClipboard()

    def _capture(self) -> ClipboardSnapshot:
        # Clipboard is open. Classify -> size -> plan -> copy the planned bytes.
        deadline = time.monotonic() + _PROBE_BUDGET_S
        offered: list[OfferedFormat] = []
        blocks: dict[Hashable, tuple[int, int]] = {}
        ids = _enumerate_formats()
        names = {fid: _format_name(fid) for fid in ids}
        total = 0
        for fid, base_kind in classify_win32_formats(ids, names=names):
            kind = base_kind
            size: int | None = None
            # Like mac_clipboard: once the bytes measured pass the cap (or the
            # budget runs out) later non-text formats go unmeasured, so the plan
            # falls back to text-only. Known limitation: a true delayed-render
            # format can't be told apart before GetClipboardDataHandle makes its
            # owner render it, so one slow render may overrun the probe budget.
            in_budget = time.monotonic() < deadline and total <= self._snapshot_cap_bytes
            if kind is FormatKind.MEMORY and (is_text_format(fid) or in_budget):
                handle = _global_handle(fid)
                size = int(_kernel32.GlobalSize(handle)) if handle else 0
                if handle and size:
                    blocks[fid] = (handle, size)
                    total += size
                else:
                    # No memory block behind it after all: not capturable.
                    kind, size = FormatKind.HANDLE, None
            offered.append(OfferedFormat(fid, names[fid], kind, size, is_text_format(fid)))

        plan = plan_capture(offered, cap_bytes=self._snapshot_cap_bytes)
        if plan.warning:
            logger.warning(plan.warning)

        entries: list[tuple[Hashable, bytes]] = []
        for fmt in plan.capture:
            handle, size = blocks[fmt.format_id]
            data = _read_global(handle, size)
            if data is None:
                logger.warning("Could not read clipboard format %s; not preserved", fmt.name)
                continue
            entries.append((fmt.format_id, data))
        return ClipboardSnapshot(entries=tuple(entries))

    def copy(self, text: str) -> None:
        # A normal, persistent copy for the tray "Copy last dictation" item: it
        # SHOULD appear in Win+V — the user explicitly asked for the text on
        # their clipboard. It is therefore deliberately kept SEPARATE from the
        # automatic dictation paste and must NOT pick up the clutter-proof
        # exclusion markers that keep that automatic write out of Win+V history
        # (ADR-0023 / #138). Self-contained open/empty/set/close.
        with _contention_as_oserror():
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()

    def set_text(self, text: str) -> None:
        with _contention_as_oserror():
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        # Clutter-proof the transient dictation write: Ctrl+V still pastes it,
        # but it never lands in Win+V history or syncs to the cloud clipboard
        # (ADR-0023 / #138). The caller already holds the clipboard open.
        self._apply_exclusion_markers()

    def restore(self, saved: ClipboardSnapshot) -> None:
        with _contention_as_oserror():
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                for fid, data in saved.entries:
                    # This adapter's own snapshots only ever hold int format ids.
                    fmt = int(fid)  # type: ignore[call-overload]
                    try:
                        _write_global(fmt, data)
                    except (pywintypes.error, MemoryError):
                        # One bad format must not cost the user the rest.
                        logger.warning(
                            "Could not restore clipboard format %s (%d bytes)",
                            _format_name(fmt),
                            len(data),
                            exc_info=True,
                        )
                if not saved.is_empty:
                    # Mark the restore too: re-writing the user's original would
                    # otherwise leave a duplicate entry in Win+V — the second half
                    # of the clutter the markers fix (ADR-0023 / #138).
                    self._apply_exclusion_markers()
            finally:
                win32clipboard.CloseClipboard()

    def _apply_exclusion_markers(self) -> None:
        # Best-effort: the markers only keep the write out of Win+V history and
        # cloud sync — they are advisory, and the text is already on the
        # clipboard. A marker failure must never break the paste/restore;
        # log-and-continue mirrors the adapters' posture (see
        # ``mac_clipboard.set_text``).
        try:
            apply_exclusion_markers(
                win32clipboard.RegisterClipboardFormat,
                win32clipboard.SetClipboardData,
            )
        except Exception:
            logger.warning(
                "Could not apply clutter-proof clipboard markers; the write "
                "succeeded but may appear in Win+V history",
                exc_info=True,
            )
