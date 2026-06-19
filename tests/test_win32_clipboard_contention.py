"""Win32 clipboard contention translation (Windows-only) — #145.

``win32clipboard.OpenClipboard`` raises ``pywintypes.error`` (NOT an ``OSError``
subclass) when another process holds the clipboard — most often the Win+V history
monitor racing a write. The pure paste pipeline retries (open) and swallows
(deferred restore) on ``except OSError``, so the adapter MUST translate
``pywintypes.error`` -> ``OSError`` or the contention handling never engages.

These tests drive the REAL ``Win32ClipboardIO`` with a real ``pywintypes.error``
(monkeypatched onto ``OpenClipboard``), proving the translation that the
``OSError``-raising ``FakeClipboardIO`` cannot — and that the pure
``_open_with_retry`` actually retries real adapter contention end to end.
"""

from __future__ import annotations

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("win32 clipboard adapter is Windows-only", allow_module_level=True)

import pywintypes  # type: ignore[import-untyped]  # noqa: E402
import win32clipboard  # type: ignore[import-untyped]  # noqa: E402

from dictatem.paste.pipeline import _open_with_retry  # noqa: E402
from dictatem.paste.win32_clipboard import Win32ClipboardIO  # noqa: E402

# Exactly what win32clipboard raises on contention: winerror 5 (ERROR_ACCESS_
# DENIED), the failing funcname, and strerror. Constructed once so the tests
# assert against the real pywin32 exception type, not a stand-in.
_ACCESS_DENIED = pywintypes.error(5, "OpenClipboard", "Access is denied.")


def test_pywintypes_error_is_not_an_oserror() -> None:
    # The premise of #145: the real contention exception slips past `except
    # OSError`. If a future pywin32 makes it an OSError subclass this fails
    # loudly and the adapter translation can be reconsidered.
    assert not isinstance(_ACCESS_DENIED, OSError)


def test_open_translates_contention_to_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny() -> None:
        raise _ACCESS_DENIED

    monkeypatch.setattr(win32clipboard, "OpenClipboard", deny)
    with pytest.raises(OSError) as excinfo:
        Win32ClipboardIO().open()
    # The original pywin32 error is chained so winerror/strerror survive.
    assert excinfo.value.__cause__ is _ACCESS_DENIED


def test_restore_translates_contention_to_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny() -> None:
        raise _ACCESS_DENIED

    monkeypatch.setattr(win32clipboard, "OpenClipboard", deny)
    with pytest.raises(OSError):
        Win32ClipboardIO().restore("user original")


def test_open_with_retry_retries_real_adapter_contention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # End-to-end: the REAL adapter raises real pywintypes.error on the first few
    # OpenClipboard calls; the pure `_open_with_retry` must catch the translated
    # OSError and retry, succeeding. The stub "open" no-ops after the contended
    # attempts so no real clipboard handle is ever held.
    attempts = 0

    def flaky_open() -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise _ACCESS_DENIED

    monkeypatch.setattr(win32clipboard, "OpenClipboard", flaky_open)
    _open_with_retry(Win32ClipboardIO(), lambda _delay: None)
    assert attempts == 4  # 3 contended attempts + 1 success, within _MAX_RETRIES (5)
