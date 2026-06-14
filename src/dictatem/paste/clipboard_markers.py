"""Clutter-proof clipboard markers — pure logic (ADR-0023 / #138).

Regular dictation pastes via the clipboard + Ctrl+V (ADR-0004). To keep that
automatic juggling out of the Win+V **history** and off the **cloud
clipboard**, every dictation-path write carries two Windows exclusion markers,
each a DWORD ``0``:

* ``CanIncludeInClipboardHistory`` → excluded from Win+V history;
* ``CanUploadToCloudClipboard`` → never synced to other devices.

Registering the formats and the actual ``SetClipboardData`` are Windows-only
I/O; the *decision* of which formats to write and what payload each carries is
pure and unit-tested here. The win32 adapter injects
``RegisterClipboardFormat`` and ``SetClipboardData``; tests inject fakes. See
``CONTEXT.md#clutter-proof-clipboard-write``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# The two Windows clipboard formats whose presence (as a DWORD 0) opts a write
# OUT of Win+V history and cloud-clipboard sync. Registered by name via
# RegisterClipboardFormat at write time.
CLIPBOARD_EXCLUSION_FORMATS: tuple[str, ...] = (
    "CanIncludeInClipboardHistory",
    "CanUploadToCloudClipboard",
)

# The payload both markers carry: a single DWORD 0 (four little-endian zero
# bytes) — the value Windows reads to exclude the write.
EXCLUSION_MARKER_PAYLOAD: bytes = (0).to_bytes(4, "little")


def apply_exclusion_markers(
    register: Callable[[str], int],
    set_data: Callable[[int, bytes], object],
) -> None:
    """Write the history/cloud exclusion markers onto the open clipboard.

    *register* maps a format name to its registered clipboard-format id;
    *set_data* writes the DWORD payload under that id. The caller must already
    hold the clipboard open with its real content set — the markers annotate
    that content. Both primitives are injected so this stays pure: the win32
    adapter passes ``win32clipboard.RegisterClipboardFormat`` and
    ``win32clipboard.SetClipboardData``; tests pass fakes that record the calls.
    """
    for name in CLIPBOARD_EXCLUSION_FORMATS:
        set_data(register(name), EXCLUSION_MARKER_PAYLOAD)
