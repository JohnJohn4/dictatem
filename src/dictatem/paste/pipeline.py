"""Pure paste pipeline — depends only on Protocol contracts, no OS imports."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from dictatem.exceptions import ClipboardContentionError

if TYPE_CHECKING:
    from dictatem.interfaces import ClipboardIO, ForegroundTracker, KeystrokeSender

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_RETRY_DELAY_S = 0.010
# SendInput is asynchronous — Ctrl+V is queued, not delivered. The target
# window's message pump may not process it for tens of milliseconds. If we
# restore the saved clipboard too soon, the target reads the *old* contents
# and the paste silently fails.
_POST_PASTE_SETTLE_S = 0.100


def _normalize(text: str) -> str:
    # faster-whisper prefixes transcribed segments with a space; strip both
    # ends so we don't paste double spaces between consecutive transcriptions.
    text = text.replace("\r\n", " ").replace("\n", " ")
    return text.strip() + " "


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
    logger.info("Paste: captured foreground hwnd=%s, text length=%d", hwnd, len(text))
    saved = clipboard.save()

    try:
        _open_with_retry(clipboard)
        clipboard.set_text(_normalize(text))
        clipboard.close()
        logger.info("Paste: clipboard set, restoring foreground and sending Ctrl+V")

        foreground.restore(hwnd)
        keystroke.send_paste()
        time.sleep(_POST_PASTE_SETTLE_S)
        logger.info("Paste: complete")
    finally:
        clipboard.restore(saved)
