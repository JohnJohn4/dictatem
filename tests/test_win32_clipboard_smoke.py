"""Smoke test for the Win32 clutter-proof clipboard write (Windows CI only).

The pure marker decision is unit-tested in ``test_clipboard_markers``; this
proves the real pywin32 binding actually works on Windows — ``SetClipboardData``
with a DWORD payload does not raise, the dictation text still round-trips (Ctrl+V
would see it), the user's original is still restored, and both exclusion formats
are present after a dictation-style write. Whether Win+V history *actually* skips
the entry is human manual-QA (ADR-0023 / #138 QA handoff).

Self-cleaning: the runner's real clipboard is saved and restored around each test
via the ``preserve_clipboard`` fixture, so running the suite never clobbers it.
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

if sys.platform != "win32":
    pytest.skip("win32 clipboard adapter is Windows-only", allow_module_level=True)

import pywintypes  # type: ignore[import-untyped]  # noqa: E402
import win32clipboard  # type: ignore[import-untyped]  # noqa: E402

from dictatem.paste.clipboard_markers import (  # noqa: E402
    CLIPBOARD_EXCLUSION_FORMATS,
)
from dictatem.paste.win32_clipboard import Win32ClipboardIO  # noqa: E402


def _open_with_retry() -> None:
    # The Win+V clipboard-history monitor opens the clipboard to read each new
    # write, so an immediate read-back races it and OpenClipboard raises
    # ``Access is denied`` (a pywintypes.error, NOT an OSError). Retry briefly,
    # like the production paste path does.
    for attempt in range(40):
        try:
            win32clipboard.OpenClipboard()
            return
        except pywintypes.error:
            if attempt == 39:
                raise
            time.sleep(0.02)


def _retry_clipboard_op(op: Callable[[], None]) -> None:
    # The adapter's own OpenClipboard (in restore, and the test's open()) races
    # the same history monitor — retry the whole mutation on contention.
    for attempt in range(40):
        try:
            op()
            return
        except pywintypes.error:
            if attempt == 39:
                raise
            time.sleep(0.02)


def _read_text() -> str | None:
    _open_with_retry()
    try:
        try:
            return str(win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT))
        except TypeError:
            return None
    finally:
        win32clipboard.CloseClipboard()


def _exclusion_formats_present() -> dict[str, bool]:
    present: dict[str, bool] = {}
    _open_with_retry()
    try:
        for name in CLIPBOARD_EXCLUSION_FORMATS:
            fmt = win32clipboard.RegisterClipboardFormat(name)
            present[name] = bool(win32clipboard.IsClipboardFormatAvailable(fmt))
    finally:
        win32clipboard.CloseClipboard()
    return present


@pytest.fixture
def preserve_clipboard() -> Iterator[None]:
    saved = _read_text()
    try:
        yield
    finally:
        # Put the runner's clipboard back exactly as it was.
        clip = Win32ClipboardIO()
        _retry_clipboard_op(lambda: clip.restore(saved))


class TestClutterProofSetText:
    def test_set_text_round_trips_and_marks(self, preserve_clipboard: None) -> None:
        clip = Win32ClipboardIO()

        def write() -> None:
            clip.open()
            try:
                clip.set_text("dictatem clutter-proof smoke ")
            finally:
                clip.close()

        _retry_clipboard_op(write)
        # Ctrl+V would still paste our text — the markers don't break the write.
        assert _read_text() == "dictatem clutter-proof smoke "
        # Both exclusion markers are present, so Win+V/cloud skip this write.
        present = _exclusion_formats_present()
        assert all(present.values()), f"missing exclusion markers: {present}"


class TestClutterProofRestore:
    def test_restore_round_trips_and_marks(self, preserve_clipboard: None) -> None:
        clip = Win32ClipboardIO()
        _retry_clipboard_op(lambda: clip.restore("user original text"))
        # The restored original is readable...
        assert _read_text() == "user original text"
        # ...and itself history/cloud-excluded, so the restore adds no Win+V
        # duplicate of the user's original (the second half of the clutter fix).
        present = _exclusion_formats_present()
        assert all(present.values()), f"missing exclusion markers: {present}"

    def test_restore_none_leaves_clipboard_empty(self, preserve_clipboard: None) -> None:
        clip = Win32ClipboardIO()
        _retry_clipboard_op(lambda: clip.restore(None))
        assert _read_text() is None
