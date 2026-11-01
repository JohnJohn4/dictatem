"""macOS clipboard adapter — NSPasteboard via PyObjC (manual QA only).

This module requires pyobjc-framework-Cocoa and only works on macOS; it is
never imported at module level by any pure-core module, and the paste
pipeline is exercised against an in-memory fake in tests. Excluded from
pyright (see ``pyproject.toml`` ``[tool.pyright] exclude``) because AppKit
is unresolvable off-macOS.

``save``/``restore`` round-trip a full Clipboard Snapshot (#244): every
pasteboard item's types are classified (``mac_pasteboard_types``), read and
sized, run through the shared Clipboard Capture Plan (``clipboard_snapshot``),
and the planned ``(item_index, type)`` entries are kept as raw bytes. Restore
rebuilds one ``NSPasteboardItem`` per saved item, in order, and writes them
back together — so a multi-file Finder copy comes back as the same files.

Unlike the Win32 clipboard, NSPasteboard has no open/close handshake — any
process can read or write it at any time, so the ``ClipboardIO`` open/close
contract is satisfied with honest no-ops (the pipeline's ``_open_with_retry``
then trivially succeeds on the first attempt).
"""

from __future__ import annotations

import logging
import sys
import time
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac_clipboard requires macOS")

from AppKit import NSPasteboard, NSPasteboardItem, NSPasteboardTypeString
from Foundation import NSData

from dictatem.paste.clipboard_snapshot import (
    SNAPSHOT_SIZE_CAP_BYTES,
    ClipboardSnapshot,
    FormatKind,
    OfferedFormat,
    plan_capture,
)
from dictatem.paste.mac_pasteboard_types import (
    classify_pasteboard_item,
    is_text_type,
    items_for_restore,
)

if TYPE_CHECKING:
    from collections.abc import Hashable

# There is no NSPasteboard size query: measuring a type means reading it, and a
# lazy data provider renders on that read. Past this budget (or once the bytes
# read pass the cap) the remaining non-text types go unmeasured, and the Capture
# Plan falls back to text-only rather than stall the paste. Mirrors win32.
_PROBE_BUDGET_S = 0.5


class MacClipboardIO:
    def __init__(self, *, snapshot_cap_bytes: int = SNAPSHOT_SIZE_CAP_BYTES) -> None:
        self._snapshot_cap_bytes = snapshot_cap_bytes

    def open(self) -> None:
        # NSPasteboard has no exclusive-acquire handshake (unlike Win32
        # OpenClipboard), so there is nothing to acquire and no contention
        # to raise on — an honest no-op.
        pass

    def close(self) -> None:
        # No handshake to release — see open().
        pass

    def save(self) -> ClipboardSnapshot:
        # Classify -> read/size -> plan -> keep the planned bytes.
        pasteboard = NSPasteboard.generalPasteboard()
        deadline = time.monotonic() + _PROBE_BUDGET_S
        offered: list[OfferedFormat] = []
        read: dict[Hashable, bytes] = {}
        total = 0
        for index, item in enumerate(pasteboard.pasteboardItems() or ()):
            types = [str(t) for t in (item.types() or ())]
            for pb_type, base_kind in classify_pasteboard_item(types):
                fid = (index, pb_type)
                kind = base_kind
                size: int | None = None
                text = is_text_type(pb_type)
                in_budget = time.monotonic() < deadline and total <= self._snapshot_cap_bytes
                if kind is FormatKind.MEMORY and (text or in_budget):
                    data = item.dataForType_(pb_type)
                    if data is None:
                        # Offered but nothing behind it (e.g. a provider that
                        # failed to render): not capturable.
                        kind = FormatKind.DELAYED
                    else:
                        read[fid] = bytes(data)
                        size = len(read[fid])
                        total += size
                offered.append(OfferedFormat(fid, pb_type, kind, size, text))

        plan = plan_capture(offered, cap_bytes=self._snapshot_cap_bytes)
        if plan.warning:
            logger.warning(plan.warning)
        entries = tuple((f.format_id, read[f.format_id]) for f in plan.capture)
        return ClipboardSnapshot(entries=entries)

    def set_text(self, text: str) -> None:
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        ok = pasteboard.setString_forType_(text, NSPasteboardTypeString)
        if not ok:
            # setString:forType: returns NO when the write is rejected
            # (e.g. another writer bumped the change count mid-write).
            # Log-and-continue mirrors the Win32 adapters' posture of
            # logging SendInput shortfalls instead of raising.
            logger.warning("NSPasteboard setString:forType: failed; clipboard not set")

    def copy(self, text: str) -> None:
        # A normal, persistent copy for the tray "Copy last dictation" item
        # (ADR-0023 / #119). NSPasteboard has no Win+V/cloud-clipboard notion,
        # so this is just a plain pasteboard write — there is nothing to
        # clutter-proof and nothing to exclude. Mirrors set_text without the
        # transient-juggling framing.
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        ok = pasteboard.setString_forType_(text, NSPasteboardTypeString)
        if not ok:
            logger.warning(
                "NSPasteboard setString:forType: failed; last dictation not copied"
            )

    def restore(self, saved: ClipboardSnapshot) -> None:
        pasteboard = NSPasteboard.generalPasteboard()
        # Always clear: an empty snapshot leaves the clipboard empty, matching
        # the Win32 adapter (the user's clipboard was empty before we used it).
        pasteboard.clearContents()
        items = []
        for types in items_for_restore(saved.entries):
            item = NSPasteboardItem.alloc().init()
            for pb_type, data in types:
                blob = NSData.dataWithBytes_length_(data, len(data))
                if not item.setData_forType_(blob, pb_type):
                    # One bad type must not cost the user the rest.
                    logger.warning(
                        "Could not restore pasteboard type %s (%d bytes)", pb_type, len(data)
                    )
            items.append(item)
        if items and not pasteboard.writeObjects_(items):
            logger.warning("NSPasteboard writeObjects: failed; user's clipboard not restored")
