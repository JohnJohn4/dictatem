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

    When *replace_chars* is zero (regular dictation), the text is placed on
    the clipboard and Ctrl+V is sent. When *replace_chars* is positive
    (Trigger Fire), the previously-pasted text is deleted via backspaces
    and the new text is *typed* directly via ``send_text`` — bypassing the
    clipboard entirely. Typing avoids the race between the daemon's
    clipboard-restore and the target window's paste handler (see #23) and
    leaves the user's clipboard untouched as a bonus.
    """
    normalized = normalize_pasted_text(text)
    hwnd = foreground.capture()
    logger.info(
        "Paste: captured foreground hwnd=%s, text length=%d, replace_chars=%d",
        hwnd,
        len(normalized),
        replace_chars,
    )

    if replace_chars > 0:
        # Typed-replacement path: no clipboard, no settle, no race.
        foreground.restore(hwnd)
        keystroke.send_backspaces(replace_chars)
        keystroke.send_text(normalized)
        logger.info("Paste: typed-replacement complete")
        return

    # Regular dictation path: clipboard + Ctrl+V.
    saved = clipboard.save()
    try:
        _open_with_retry(clipboard)
        clipboard.set_text(normalized)
        clipboard.close()
        logger.info("Paste: clipboard set, restoring foreground and sending Ctrl+V")

        foreground.restore(hwnd)
        keystroke.send_paste()
        time.sleep(_POST_PASTE_SETTLE_S)
        logger.info("Paste: complete")
    finally:
        # restore() can race the target window's Ctrl+V handler — both call
        # OpenClipboard. Swallow the resulting Access-denied; losing the race
        # is the correct outcome (target reads the new text we just put on
        # the clipboard). Retrying would put the old text back before the
        # target reads it. See #23.
        try:
            clipboard.restore(saved)
        except OSError as exc:
            logger.warning(
                "Clipboard restore lost race with target's paste handler "
                "(%s); user's original clipboard not restored",
                exc,
            )
