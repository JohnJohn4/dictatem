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


def normalize_pasted_text(text: str) -> str:
    """Return *text* as it will actually be placed on the clipboard.

    Public because the daemon snapshots the post-normalisation form into
    ``LastPaste`` so backspace counts line up with what the user sees.
    """
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
    replace_chars: int = 0,
) -> None:
    """Paste *text* into the focused window.

    If *replace_chars* is non-zero, *replace_chars* backspaces are sent
    after restoring the foreground window and before the paste itself.
    This is the Trigger Fire path described in ADR-0001: the previously
    pasted text is deleted in place, then the rewritten text takes its
    place.
    """
    hwnd = foreground.capture()
    logger.info(
        "Paste: captured foreground hwnd=%s, text length=%d, replace_chars=%d",
        hwnd,
        len(text),
        replace_chars,
    )
    saved = clipboard.save()

    try:
        _open_with_retry(clipboard)
        clipboard.set_text(normalize_pasted_text(text))
        clipboard.close()
        logger.info("Paste: clipboard set, restoring foreground and sending Ctrl+V")

        foreground.restore(hwnd)
        if replace_chars > 0:
            keystroke.send_backspaces(replace_chars)
        keystroke.send_paste()
        time.sleep(_POST_PASTE_SETTLE_S)
        logger.info("Paste: complete")
    finally:
        clipboard.restore(saved)
