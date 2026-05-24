"""macOS NSPasteboard clipboard adapter (#59 / ADR-0014) — manual QA only.

The macOS analogue of ``win32_clipboard.py``: implements the ``ClipboardIO``
Protocol (save / set / restore) over ``NSPasteboard``. The paste pipeline saves
the user's clipboard, sets the dictated text, sends Cmd+V, then restores — so the
user's clipboard is preserved (CONTEXT.md / ADR-0004).

NSPasteboard has no exclusive open/close lock the way Win32 does, so ``open`` and
``close`` are no-ops; the pipeline's retry-around-contention is a Windows concern.

This module imports PyObjC (AppKit) and only works on macOS. It is NEVER imported
at module top level (lazy-imported in ``daemon._start_macos_daemon``;
``tests/test_import_safety.py``) and is excluded from pyright/tests
(``pyproject.toml`` ``[tool.pyright] exclude``).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NSPasteboardClipboardIO:
    """ClipboardIO backed by the general NSPasteboard."""

    def _pasteboard(self):  # noqa: ANN202
        from AppKit import NSPasteboard  # type: ignore[import-not-found]

        return NSPasteboard.generalPasteboard()

    def open(self) -> None:
        # NSPasteboard needs no exclusive lock; nothing to acquire.
        pass

    def close(self) -> None:
        pass

    def save(self) -> str | None:
        from AppKit import NSPasteboardTypeString  # type: ignore[import-not-found]

        value = self._pasteboard().stringForType_(NSPasteboardTypeString)
        return str(value) if value is not None else None

    def set_text(self, text: str) -> None:
        from AppKit import NSPasteboardTypeString  # type: ignore[import-not-found]

        pb = self._pasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)

    def restore(self, saved: str | None) -> None:
        from AppKit import NSPasteboardTypeString  # type: ignore[import-not-found]

        pb = self._pasteboard()
        pb.clearContents()
        if saved is not None:
            pb.setString_forType_(saved, NSPasteboardTypeString)
