"""macOS clipboard adapter — NSPasteboard via PyObjC (manual QA only).

This module requires pyobjc-framework-Cocoa and only works on macOS; it is
never imported at module level by any pure-core module, and the paste
pipeline is exercised against an in-memory fake in tests. Excluded from
pyright (see ``pyproject.toml`` ``[tool.pyright] exclude``) because AppKit
is unresolvable off-macOS.

Unlike the Win32 clipboard, NSPasteboard has no open/close handshake — any
process can read or write it at any time, so the ``ClipboardIO`` open/close
contract is satisfied with honest no-ops (the pipeline's ``_open_with_retry``
then trivially succeeds on the first attempt).
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac_clipboard requires macOS")

from AppKit import NSPasteboard, NSPasteboardTypeString

from dictatem.paste.clipboard_snapshot import ClipboardSnapshot


class MacClipboardIO:
    def open(self) -> None:
        # NSPasteboard has no exclusive-acquire handshake (unlike Win32
        # OpenClipboard), so there is nothing to acquire and no contention
        # to raise on — an honest no-op.
        pass

    def close(self) -> None:
        # No handshake to release — see open().
        pass

    def save(self) -> ClipboardSnapshot:
        # Text-only for now: the full-format pasteboard snapshot is #244. The
        # snapshot is opaque to the pipeline, so this keeps today's behaviour
        # (non-text content is not preserved on macOS yet; see README).
        pasteboard = NSPasteboard.generalPasteboard()
        value = pasteboard.stringForType_(NSPasteboardTypeString)
        if not value:
            # Empty, or image/file-only content: nothing to restore.
            return ClipboardSnapshot.empty()
        return ClipboardSnapshot(
            entries=((str(NSPasteboardTypeString), str(value).encode("utf-8")),)
        )

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
        for _type, data in saved.entries:
            ok = pasteboard.setString_forType_(
                data.decode("utf-8"), NSPasteboardTypeString
            )
            if not ok:
                logger.warning(
                    "NSPasteboard setString:forType: failed; user's clipboard not restored"
                )
