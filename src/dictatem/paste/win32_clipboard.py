"""Win32 clipboard adapter — requires pywin32."""

from __future__ import annotations

import win32clipboard  # type: ignore[import-untyped]


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

    def restore(self, saved: str | None) -> None:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            if saved is not None:
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, saved)
        finally:
            win32clipboard.CloseClipboard()
