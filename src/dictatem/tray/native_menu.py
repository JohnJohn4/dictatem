"""Pure model for the Windows-native tray menu (no Qt or Win32 imports).

On Windows the tray menu is shown with the OS's own ``TrackPopupMenuEx``
rather than a Qt ``QMenu``. Native notification-area menus are what the shell
expects: the hidden-icons flyout stays open behind them, an outside click
dismisses them, and keyboard navigation is the system's. A Qt popup is just
another window to the shell, so the flyout closed as soon as the mouse left
it (owner QA, 2026-11-04).

The Qt ``QAction``s stay the single source of truth for labels, visibility,
enablement and checks. This module turns a snapshot of them into a tidy,
numbered plan, and the Win32 adapter in ``qt_tray`` renders the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ItemKind = Literal["action", "separator", "submenu"]


@dataclass(frozen=True)
class NativeItem:
    kind: ItemKind
    text: str = ""
    enabled: bool = True
    checked: bool = False
    children: tuple[NativeItem, ...] = ()
    # Opaque handle back to the source (a QAction); not used by the plan logic.
    key: object = field(default=None, compare=False)


def tidy(items: list[NativeItem] | tuple[NativeItem, ...]) -> list[NativeItem]:
    """Drop leading, trailing and doubled separators, at every level.

    Hidden items can leave separators next to each other (for example, the
    hidden hotkey header and its separator), which a native menu would draw
    as empty bands.
    """
    out: list[NativeItem] = []
    for item in items:
        if item.kind == "separator":
            if out and out[-1].kind != "separator":
                out.append(item)
            continue
        if item.kind == "submenu":
            item = NativeItem(
                "submenu",
                item.text,
                item.enabled,
                item.checked,
                tuple(tidy(item.children)),
                item.key,
            )
        out.append(item)
    while out and out[-1].kind == "separator":
        out.pop()
    return out


def native_label(text: str) -> str:
    """Escape ``&`` so Windows doesn't treat it as a mnemonic marker."""
    return text.replace("&", "&&")


def number_actions(items: list[NativeItem], start: int = 1) -> dict[int, NativeItem]:
    """Assign command ids (1, 2, …) to every action, depth-first, in menu order.

    ``TrackPopupMenuEx(TPM_RETURNCMD)`` returns the chosen id; 0 means
    "dismissed", so ids start at 1.
    """
    ids: dict[int, NativeItem] = {}

    def walk(level: list[NativeItem] | tuple[NativeItem, ...]) -> None:
        for item in level:
            if item.kind == "action":
                ids[start + len(ids)] = item
            elif item.kind == "submenu":
                walk(item.children)

    walk(items)
    return ids
