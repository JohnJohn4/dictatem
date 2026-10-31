"""Clipboard Snapshot and Clipboard Capture Plan — pure, platform-neutral (#243).

Regular dictation borrows the clipboard (paste via Ctrl+V, ADR-0004), so the
user's clipboard is saved first and put back afterwards. The saved value is an
opaque **Clipboard Snapshot**: every format that could be safely captured, as
raw bytes, in the order the clipboard offered them. The paste pipeline and the
deferred restore scheduler never look inside it — only the adapter that made it
reads it back.

Which formats to capture is the **Clipboard Capture Plan**, decided here from a
description of what is on offer (id, display name, kind, size) so it is unit
-testable without a real clipboard:

* only ``MEMORY`` formats (plain bytes the adapter can copy out and write back)
  are captured; handle-based, OS-synthesized and delayed-render/owner-drawn
  formats are skipped;
* the captured total is held to ``SNAPSHOT_SIZE_CAP_BYTES``. Over the cap — or
  if any candidate could not be measured — only the text formats are kept and
  the plan carries a warning listing format names and sizes, never content.

Format ids are opaque ``Hashable`` values so the same plan and snapshot serve
the Win32 adapter (integer clipboard-format ids) and the macOS adapter (#244;
e.g. ``(item_index, uti)`` pairs). See ``CONTEXT.md#clipboard-snapshot``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterable

# Total bytes a snapshot may hold. Big enough for a 4K screenshot offered as
# both a DIB and a PNG; small enough that copying it never stalls a paste. A
# constant on purpose, not config (spec #225).
SNAPSHOT_SIZE_CAP_BYTES = 64 * 1024 * 1024


class FormatKind(Enum):
    """How a clipboard format's data is held — decides if it can be captured."""

    MEMORY = "memory"
    """Plain bytes (an HGLOBAL on Windows, NSData on macOS): capturable."""
    HANDLE = "handle"
    """A GDI/OS handle (bitmap, metafile, palette) — no bytes to copy."""
    SYNTHESIZED = "synthesized"
    """The OS regenerates it from another offered format; restoring that one is enough."""
    DELAYED = "delayed"
    """Owner-drawn or delayed-render: reading it would call back into the owner."""


@dataclass(frozen=True)
class OfferedFormat:
    """One format currently on the clipboard, as described by an adapter."""

    format_id: Hashable
    name: str
    kind: FormatKind
    # Bytes, or None when the adapter did not (or could not) measure it.
    size: int | None
    # Plain text: the representation kept when the snapshot falls back.
    is_text: bool = False


@dataclass(frozen=True)
class CapturePlan:
    """The formats to capture, in clipboard order, and whether the cap was hit."""

    capture: tuple[OfferedFormat, ...]
    over_cap: bool
    warning: str | None


def plan_capture(
    offered: Iterable[OfferedFormat], *, cap_bytes: int = SNAPSHOT_SIZE_CAP_BYTES
) -> CapturePlan:
    """Decide which of the *offered* formats a Clipboard Snapshot captures."""
    candidates = tuple(f for f in offered if f.kind is FormatKind.MEMORY)
    unmeasured = any(f.size is None for f in candidates)
    total = sum(f.size or 0 for f in candidates)
    if not unmeasured and total <= cap_bytes:
        return CapturePlan(capture=candidates, over_cap=False, warning=None)

    sizes = ", ".join(f"{f.name}={'unmeasured' if f.size is None else f.size}" for f in candidates)
    warning = (
        f"Clipboard too large to preserve in full ({total} bytes"
        f"{', some unmeasured' if unmeasured else ''}; cap {cap_bytes}); "
        f"keeping text only. Formats: {sizes}"
    )
    text_only = tuple(f for f in candidates if f.is_text)
    return CapturePlan(capture=text_only, over_cap=True, warning=warning)


@dataclass(frozen=True)
class ClipboardSnapshot:
    """Opaque saved clipboard: ``(format_id, raw bytes)`` in restore order.

    Produced by ``ClipboardIO.save`` and consumed only by the same adapter's
    ``restore``; everything in between passes it through untouched. An empty
    snapshot restores to an empty clipboard.
    """

    entries: tuple[tuple[Hashable, bytes], ...] = field(default=())

    @classmethod
    def empty(cls) -> ClipboardSnapshot:
        return cls()

    @property
    def is_empty(self) -> bool:
        return not self.entries

    def __repr__(self) -> str:
        # Never render clipboard content — only format ids and byte counts.
        parts = ", ".join(f"{fid!r}:{len(data)}B" for fid, data in self.entries)
        return f"ClipboardSnapshot([{parts}])"
