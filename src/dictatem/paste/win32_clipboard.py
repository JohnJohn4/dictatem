"""Win32 clipboard adapter — requires pywin32."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pywintypes  # type: ignore[import-untyped]
import win32clipboard  # type: ignore[import-untyped]

from dictatem.paste.clipboard_markers import apply_exclusion_markers

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)


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


class Win32ClipboardIO:
    def open(self) -> None:
        with _contention_as_oserror():
            win32clipboard.OpenClipboard()

    def close(self) -> None:
        with _contention_as_oserror():
            win32clipboard.CloseClipboard()

    def save(self) -> str | None:
        with _contention_as_oserror():
            win32clipboard.OpenClipboard()
            try:
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return str(data) if data else None
            except TypeError:
                return None
            finally:
                win32clipboard.CloseClipboard()

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

    def restore(self, saved: str | None) -> None:
        with _contention_as_oserror():
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
