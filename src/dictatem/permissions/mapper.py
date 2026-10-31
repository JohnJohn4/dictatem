"""Pure mapper from missing macOS permissions to guided-dialog content.

macOS gates Dictatem's core behaviours behind TCC permissions the user must
grant manually in System Settings: **Accessibility** (synthetic keystrokes,
backspaces, paste via CGEvent) and **Input Monitoring** (the global-hotkey
CGEventTap). Given the set of permissions the native probes found missing,
this returns one ``PermissionGuidance`` per missing permission — the System
Settings deep link to open and the user-facing copy to show — or the empty
tuple when nothing is missing, which means "show no dialog".

The copy comes in two contexts (#95): ``STARTUP`` (the launch-time probe —
"allow Dictatem to …") and ``ON_USE`` (a gated action just failed — "Dictatem
couldn't paste"), so a re-prompt explains what the user just saw happen
instead of failing silently. Both are short and action-first: one line naming
the exact pane and entry to turn on, one line on the one-time relaunch.

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


class PromptContext(Enum):
    """Why the guidance is being shown — selects the headline copy (#95)."""

    STARTUP = auto()
    """The launch-time probe found the grant missing."""

    ON_USE = auto()
    """A gated action (hotkey tap, paste) just failed for lack of the grant."""


@dataclass(frozen=True)
class PermissionGuidance:
    """How to guide the user through granting one missing permission."""

    permission: MacPermission

    settings_url: str
    """``x-apple.systempreferences:`` deep link opening the exact Privacy &
    Security pane where the user grants the permission."""

    title: str
    """Short, action-first headline (the dialog's bold line)."""

    message: str
    """The steps: which pane, which entry to turn on (the *user* grants it in
    System Settings), and the one-time relaunch."""


# The System Settings entry name when the TCC identity can't be determined.
GENERIC_TCC_ENTRY = "Python"


def tcc_entry_name(major: int, minor: int) -> str:
    """The name the Privacy & Security panes list Dictatem under.

    Until a signed bundle gives Dictatem its own identity (#91), TCC attributes
    the grant to the uv-managed interpreter the daemon runs as, which the panes
    show as ``python<major>.<minor>`` (e.g. ``python3.12``) — not "Dictatem"
    (ADR-0014 amendment). Naming the exact row saves the user hunting for a
    "Dictatem" entry that isn't there. Drop this when #91 lands.
    """
    return f"python{major}.{minor}"


_RELAUNCH = (
    "Then choose Restart from the Dictatem menu-bar menu — the change takes "
    "effect once Dictatem relaunches."
)

# Tray hotkey-hint text while the event tap is down for lack of Input
# Monitoring (#95): the hint row is where the user looks when the hotkey "does
# nothing", so it says why instead of advertising a chord that can't fire.
HOTKEY_OFF_HINT = "Hotkey off — allow Input Monitoring"


@dataclass(frozen=True)
class _Copy:
    settings_url: str
    pane: str
    startup_title: str
    on_use_title: str
    on_use_consequence: str


_COPY: dict[MacPermission, _Copy] = {
    MacPermission.ACCESSIBILITY: _Copy(
        settings_url=(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        ),
        pane="Accessibility",
        startup_title="Allow Dictatem to paste your text",
        on_use_title="Dictatem couldn't paste — allow Accessibility",
        on_use_consequence=(
            "Your text isn't lost: choose Copy last dictation from the menu-bar menu."
        ),
    ),
    MacPermission.INPUT_MONITORING: _Copy(
        settings_url=(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
        ),
        pane="Input Monitoring",
        startup_title="Allow Dictatem to hear its hotkey",
        on_use_title="Dictatem's hotkey isn't working — allow Input Monitoring",
        on_use_consequence=(
            "Meanwhile you can still record from the menu-bar menu."
        ),
    ),
}


def _guidance(
    permission: MacPermission, *, context: PromptContext, listed_as: str
) -> PermissionGuidance:
    copy = _COPY[permission]
    steps = (
        f"In System Settings › Privacy & Security › {copy.pane}, turn on "
        f"“{listed_as}” — that entry is Dictatem. {_RELAUNCH}"
    )
    if context is PromptContext.ON_USE:
        return PermissionGuidance(
            permission=permission,
            settings_url=copy.settings_url,
            title=copy.on_use_title,
            message=f"{steps}\n\n{copy.on_use_consequence}",
        )
    return PermissionGuidance(
        permission=permission,
        settings_url=copy.settings_url,
        title=copy.startup_title,
        message=steps,
    )


def map_missing_permissions(
    missing: AbstractSet[MacPermission],
    *,
    context: PromptContext = PromptContext.STARTUP,
    listed_as: str = GENERIC_TCC_ENTRY,
) -> tuple[PermissionGuidance, ...]:
    """Map *missing* onto per-permission guidance, one entry per permission.

    ``missing`` is whatever the native probes (the ``CGPreflight*`` pair,
    tap-creation failure, a blocked paste) reported absent. The empty set is
    the explicit all-granted case and maps to the empty tuple — the caller
    shows no dialog (blind iteration naturally shows none). Guidance comes
    back in stable ``MacPermission`` declaration order regardless of the set's
    iteration order. *context* picks the startup vs on-use headline;
    *listed_as* is the System Settings entry name (see :func:`tcc_entry_name`).
    """
    return tuple(
        _guidance(p, context=context, listed_as=listed_as)
        for p in MacPermission
        if p in missing
    )


def reprompt_notification(
    permission: MacPermission, *, listed_as: str = GENERIC_TCC_ENTRY
) -> tuple[str, str]:
    """``(title, body)`` for the throttled tray note on a repeat failed use (#95).

    Shown instead of the dialog inside its cool-down, so a repeat failure is
    never silent but never a modal nag either.
    """
    copy = _COPY[permission]
    return (
        copy.on_use_title,
        f"{copy.on_use_consequence} To fix: turn on “{listed_as}” in Privacy & "
        f"Security › {copy.pane}, then choose Restart.",
    )
