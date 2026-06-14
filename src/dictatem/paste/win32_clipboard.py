"""Win32 clipboard adapter — requires pywin32."""

from __future__ import annotations

import win32clipboard  # type: ignore[import-untyped]

from dictatem.paste.clipboard_markers import apply_exclusion_markers


class Win32ClipboardIO:
    def open(self) -> None:
        win32clipboard.OpenClipboard()

    def close(self) -> None:
        win32clipboard.CloseClipboard()

    def save(self) -> str | None:
        win32clipboard.OpenClipboard()
        try:
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            return str(data) if data else None
        except TypeError:
            return None
        finally:
            win32clipboard.CloseClipboard()

    def set_text(self, text: str) -> None:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        # Clutter-proof the transient dictation write: Ctrl+V still pastes it,
        # but it never lands in Win+V history or syncs to the cloud clipboard
        # (ADR-0023 / #138). The caller already holds the clipboard open.
        self._apply_exclusion_markers()

    def restore(self, saved: str | None) -> None:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            if saved is not None:
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, saved)
                # Mark the restore too: re-writing the user's original would
                # otherwise leave a duplicate entry in Win+V — the second half
                # of the clutter the markers fix (ADR-0023 / #138).
                self._apply_exclusion_markers()
        finally:
            win32clipboard.CloseClipboard()

    def _apply_exclusion_markers(self) -> None:
        apply_exclusion_markers(
            win32clipboard.RegisterClipboardFormat,
            win32clipboard.SetClipboardData,
        )
