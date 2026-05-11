"""Pure paste pipeline — depends only on Protocol contracts, no OS imports."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from dictatem.exceptions import ClipboardContentionError

if TYPE_CHECKING:
    from dictatem.interfaces import ClipboardIO, ForegroundTracker, KeystrokeSender

_MAX_RETRIES = 5
_RETRY_DELAY_S = 0.010


def _normalize(text: str) -> str:
    text = text.replace("\r\n", " ").replace("\n", " ")
    return text + " "


def _open_with_retry(clipboard: ClipboardIO) -> None:
    for attempt in range(_MAX_RETRIES):
        try:
            clipboard.open()
            return
        except OSError:
            if attempt == _MAX_RETRIES - 1:
                raise ClipboardContentionError from None
            time.sleep(_RETRY_DELAY_S)


def paste(
    text: str,
    *,
    clipboard: ClipboardIO,
    keystroke: KeystrokeSender,
    foreground: ForegroundTracker,
) -> None:
    hwnd = foreground.capture()
    saved = clipboard.save()

    try:
        _open_with_retry(clipboard)
        clipboard.set_text(_normalize(text))
        clipboard.close()

        foreground.restore(hwnd)
        keystroke.send_paste()
        time.sleep(0.005)
    finally:
        clipboard.restore(saved)
