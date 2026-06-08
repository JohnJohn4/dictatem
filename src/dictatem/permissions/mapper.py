"""Pure mapper from missing macOS permissions to guided-dialog content.

macOS gates Dictatem's core behaviours behind TCC permissions the user must
grant manually in System Settings: **Accessibility** (synthetic keystrokes,
backspaces, paste via CGEvent) and **Input Monitoring** (the global-hotkey
CGEventTap). Given the set of permissions the native probes found missing,
this returns one ``PermissionGuidance`` per missing permission — the System
Settings deep link to open and the user-facing copy to show — or the empty
tuple when nothing is missing, which means "show no dialog".

This module is PURE: it imports nothing OS-specific, performs no I/O, and
calls no native API — every branch is trivially unit-testable on any OS.
The native half (the ``CGPreflight*`` probes in ``permissions.mac_tcc``,
tap-creation failure detection, and the dialog itself) is separate,
macOS-only, manual-QA code.

Microphone is deliberately NOT mapped here: macOS shows its standard
automatic TCC prompt on first capture, so Dictatem never needs custom
guidance for it. The copy never implies Dictatem grants anything on the
user's behalf — only the user can grant, in System Settings — and it
explains the one-time relaunch macOS requires after granting. See ADR-0014.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet


class MacPermission(Enum):
    """A macOS TCC permission that needs guided (manual) granting.

    Only permissions the user must grant by hand in System Settings belong
    here. Microphone is intentionally absent: macOS prompts for it
    automatically on first capture, so no guided dialog is ever shown.
    """

    ACCESSIBILITY = auto()
    """Needed for synthetic keystrokes/backspaces and paste (CGEvent)."""

    INPUT_MONITORING = auto()
    """Needed for the global-hotkey event tap (CGEventTap)."""


@dataclass(frozen=True)
class PermissionGuidance:
    """How to guide the user through granting one missing permission."""

    permission: MacPermission

    settings_url: str
    """``x-apple.systempreferences:`` deep link opening the exact Privacy &
    Security pane where the user grants the permission."""

    message: str
    """User-facing copy: why Dictatem needs the permission, that the *user*
    grants it in System Settings, and the required one-time relaunch."""


_RELAUNCH = (
    "After you turn it on, quit and relaunch Dictatem once — macOS applies "
    "the permission on the next launch."
)

# Until a signed bundle gives Dictatem its own identity (#91), the running
# process is the Python interpreter, so the System Settings entry is named
# "Python" (e.g. "python3.12"), not "Dictatem". Say so, or the user hunts for a
# "Dictatem" row that isn't there. Drop this note when #91 lands.
_LISTED_AS_PYTHON = ' (it appears in the list as "Python", not "Dictatem")'

_GUIDANCE: dict[MacPermission, PermissionGuidance] = {
    MacPermission.ACCESSIBILITY: PermissionGuidance(
        permission=MacPermission.ACCESSIBILITY,
        settings_url=(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        ),
        message=(
            "Dictatem needs the Accessibility permission to type and paste "
            "dictated text. macOS only lets you grant it in System Settings: "
            "open Privacy & Security > Accessibility and turn on Dictatem"
            + _LISTED_AS_PYTHON
            + ". "
            + _RELAUNCH
        ),
    ),
    MacPermission.INPUT_MONITORING: PermissionGuidance(
        permission=MacPermission.INPUT_MONITORING,
        settings_url=(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
        ),
        message=(
            "Dictatem needs the Input Monitoring permission to hear its "
            "global dictation hotkey. macOS only lets you grant it in System "
            "Settings: open Privacy & Security > Input Monitoring and turn "
            "on Dictatem" + _LISTED_AS_PYTHON + ". " + _RELAUNCH
        ),
    ),
}


def map_missing_permissions(
    missing: AbstractSet[MacPermission],
) -> tuple[PermissionGuidance, ...]:
    """Map *missing* onto per-permission guidance, one entry per permission.

    ``missing`` is whatever the native probes (the ``CGPreflight*`` pair,
    tap-creation failure) reported absent. The empty set is the explicit
    all-granted case and maps to the empty tuple — the caller shows no
    dialog (blind iteration naturally shows none). Guidance comes back in
    stable ``MacPermission`` declaration order regardless of the set's
    iteration order. Always one uniform shape, mirroring
    ``classify_transform_failure``.
    """
    return tuple(_GUIDANCE[p] for p in MacPermission if p in missing)
