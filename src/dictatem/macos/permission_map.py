"""Pure mapper: missing macOS permissions -> Settings deep-links + copy (#57).

macOS gates Dictatem behind privacy permissions (ADR-0014): **Accessibility**
(synthetic keystrokes / focus control via CGEvent + AXUIElement) and **Input
Monitoring** (the global hotkey via CGEventTap). Both must be granted manually in
System Settings and require a one-time relaunch. Microphone is the familiar
automatic TCC prompt and is deliberately NOT handled here.

Given the SET of missing permissions, this returns the exact System Settings
deep-link targets and the user-facing copy to show in the guided dialog. It is
PURE: no PyObjC, no I/O, no AX calls — every branch (including the nothing-missing
case) is trivially unit-testable, mirroring ``failure_classifier``. The native
TCC detection that produces the missing-set lives in ``permissions.py`` (manual
QA only); the *decision* of which pane to open for which gap is pure and tested.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

# System Settings (formerly System Preferences) privacy deep-link URLs. These
# x-apple.systempreferences anchors open the named pane directly (ADR-0014).
ACCESSIBILITY_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)
INPUT_MONITORING_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
)


class MacPermission(enum.Enum):
    """A macOS privacy permission Dictatem needs and must guide the user to grant.

    Microphone is intentionally absent: it is granted via the automatic TCC
    prompt on first capture, not a manual Settings visit (ADR-0014).
    """

    ACCESSIBILITY = "accessibility"
    INPUT_MONITORING = "input_monitoring"


# Human-facing pane name + what each grant unlocks. Kept here (not in the UI
# adapter) so the copy is asserted by the pure tests.
_PANE_NAME: dict[MacPermission, str] = {
    MacPermission.ACCESSIBILITY: "Accessibility",
    MacPermission.INPUT_MONITORING: "Input Monitoring",
}
_PANE_URL: dict[MacPermission, str] = {
    MacPermission.ACCESSIBILITY: ACCESSIBILITY_URL,
    MacPermission.INPUT_MONITORING: INPUT_MONITORING_URL,
}
_PANE_REASON: dict[MacPermission, str] = {
    MacPermission.ACCESSIBILITY: (
        "type transcribed text into the focused app and replace text for "
        "Trigger Words"
    ),
    MacPermission.INPUT_MONITORING: "detect the global dictation hotkey",
}


@dataclass(frozen=True)
class PermissionGuidance:
    """One pane to open for one missing permission.

    Ordered, copy-pasteable guidance: ``pane`` is the human name shown in the
    dialog, ``url`` is the deep-link that opens that exact Settings pane, and
    ``reason`` explains why Dictatem needs it.
    """

    permission: MacPermission
    pane: str
    url: str
    reason: str


@dataclass(frozen=True)
class PermissionPrompt:
    """The full guided-dialog payload for the current set of missing grants.

    ``all_granted`` is the nothing-missing case: ``steps`` is empty and the
    daemon proceeds without showing a dialog. Otherwise ``steps`` lists one
    :class:`PermissionGuidance` per missing permission (stable order) and
    ``message`` explains the one-time relaunch.
    """

    all_granted: bool
    steps: tuple[PermissionGuidance, ...]
    title: str
    message: str


# Stable display order: Input Monitoring (hotkey, the first thing the user hits)
# before Accessibility (paste). Deterministic so the tests and dialog agree.
_ORDER: tuple[MacPermission, ...] = (
    MacPermission.INPUT_MONITORING,
    MacPermission.ACCESSIBILITY,
)

_RELAUNCH_NOTE = (
    "After granting each permission, fully quit and relaunch Dictatem — macOS "
    "only applies a new grant to a freshly launched process."
)


def map_missing_permissions(
    missing: frozenset[MacPermission],
) -> PermissionPrompt:
    """Map the SET of *missing* permissions to a guided-dialog payload.

    Pure and total: the empty set yields ``all_granted=True`` with no steps; any
    non-empty set yields one ordered :class:`PermissionGuidance` per missing
    permission, each carrying the exact deep-link URL and copy. Never returns a
    step for a permission that is not missing.
    """
    if not missing:
        return PermissionPrompt(
            all_granted=True,
            steps=(),
            title="Dictatem is ready",
            message="All required macOS permissions are granted.",
        )

    steps = tuple(
        PermissionGuidance(
            permission=perm,
            pane=_PANE_NAME[perm],
            url=_PANE_URL[perm],
            reason=_PANE_REASON[perm],
        )
        for perm in _ORDER
        if perm in missing
    )

    pane_list = " and ".join(step.pane for step in steps)
    message = (
        f"Dictatem needs {pane_list} access. Open each pane below, enable "
        f"Dictatem, then relaunch.\n\n{_RELAUNCH_NOTE}"
    )

    return PermissionPrompt(
        all_granted=False,
        steps=steps,
        title="Grant Dictatem permissions",
        message=message,
    )
