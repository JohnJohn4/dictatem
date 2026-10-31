"""macOS pasteboard-type classification — pure, no AppKit (#244).

Turns the types an ``NSPasteboardItem`` offers into ``FormatKind``s for the
Clipboard Capture Plan (``clipboard_snapshot.plan_capture``), and regroups a
snapshot's entries into pasteboard items for restore. Lives apart from the
adapter (``mac_clipboard``) so it is unit-testable on every platform. Snapshot
format ids on macOS are ``(item_index, type)`` pairs.

Rules, per item:

* File-promise types (``com.apple.pasteboard.promised-*``,
  ``com.apple.NSFilePromiseItemMetaData``) only make sense while the source app
  is around to fulfil the promise → ``DELAYED``.
* Legacy aliases — ``dyn.*`` dynamic UTIs and the old dotless names
  (``NSStringPboardType``, ``Apple PNG pasteboard type``,
  ``CorePasteboardFlavorType 0x…``) — are bridged by the pasteboard from the
  real UTIs beside them → ``SYNTHESIZED``. If an item offers *only* legacy
  types, they are all it has, so they are ``MEMORY``.
* Every other (reverse-DNS) UTI is plain ``NSData`` → ``MEMORY``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dictatem.paste.clipboard_snapshot import FormatKind

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterable

_TEXT_TYPES = frozenset(
    {
        "public.utf8-plain-text",  # NSPasteboardTypeString
        "public.utf16-plain-text",
        "public.utf16-external-plain-text",
        "public.plain-text",
    }
)
_PROMISE_PREFIX = "com.apple.pasteboard.promised-"
_PROMISE_TYPES = frozenset({"com.apple.NSFilePromiseItemMetaData"})


def is_text_type(pb_type: str) -> bool:
    """True for the plain-text types kept when a snapshot falls back."""
    return pb_type in _TEXT_TYPES


def _is_promise(pb_type: str) -> bool:
    return pb_type.startswith(_PROMISE_PREFIX) or pb_type in _PROMISE_TYPES


def _is_legacy_alias(pb_type: str) -> bool:
    return pb_type.startswith("dyn.") or "." not in pb_type


def classify_pasteboard_item(types: Iterable[str]) -> list[tuple[str, FormatKind]]:
    """Classify one pasteboard item's types, in the order the item offers them."""
    types = list(types)
    has_real_uti = any(not _is_legacy_alias(t) and not _is_promise(t) for t in types)
    out: list[tuple[str, FormatKind]] = []
    for t in types:
        if _is_promise(t):
            kind = FormatKind.DELAYED
        elif _is_legacy_alias(t) and has_real_uti:
            kind = FormatKind.SYNTHESIZED
        else:
            kind = FormatKind.MEMORY
        out.append((t, kind))
    return out


def items_for_restore(
    entries: Iterable[tuple[Hashable, bytes]],
) -> list[list[tuple[str, bytes]]]:
    """Regroup snapshot entries (``((item_index, type), data)``) into items.

    Items come back in first-seen order, each with its types in snapshot order;
    an item the plan dropped entirely produces no (empty) item.
    """
    groups: dict[object, list[tuple[str, bytes]]] = {}
    for format_id, data in entries:
        index, pb_type = format_id  # type: ignore[misc]
        groups.setdefault(index, []).append((str(pb_type), data))
    return list(groups.values())
