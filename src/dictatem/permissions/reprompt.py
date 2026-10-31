"""Re-prompt-on-use throttle for missing macOS permissions (#95) — pure.

Before #95 a missing grant failed *silently* after the one launch-time dialog:
the hotkey tap never came up, or a paste's synthetic Cmd+V was dropped by
macOS, and nothing told the user. Now every gated failure is *reported*, and
this module decides how loudly to surface each report:

- ``DIALOG`` — the guided, deep-linking dialog. Shown the first time a
  permission is reported, then again only after a cool-down, so it never nags
  on every dictation.
- ``NOTIFY`` — a one-line tray notification for a report inside the dialog's
  cool-down, so a repeat failure is still never silent. Itself rate-limited.
- ``NONE`` — the dialog for that permission is open right now, or a
  notification just went out.

The launch-time probe goes through the same throttle (:meth:`on_startup`), so
a permission the event-tap failure already surfaced is not shown twice when
the startup probe runs a moment later.

PURE: no Qt, no clock, no I/O — callers pass ``now`` (seconds on a monotonic
clock) and report back when a dialog closes. The Qt wiring in ``daemon`` is
manual-QA; every decision here is unit-tested.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from dictatem.permissions.mapper import MacPermission

# Re-show the guided dialog for a still-missing permission at most this often.
DEFAULT_DIALOG_COOLDOWN_S = 300.0
# Between dialogs, a failed use gets at most one notification this often.
DEFAULT_NOTIFY_COOLDOWN_S = 30.0


class RepromptAction(Enum):
    DIALOG = auto()
    NOTIFY = auto()
    NONE = auto()


class PermissionRepromptThrottle:
    """Decides, per permission, whether a report shows a dialog, a note, or nothing.

    A ``DIALOG`` decision marks that permission's dialog as *open* (the caller
    is about to show it); the caller must call :meth:`dialog_closed` when the
    user dismisses it — the cool-down runs from the close, so dismissing with
    "Later" buys the user a quiet window rather than an instant re-prompt.
    """

    def __init__(
        self,
        *,
        dialog_cooldown_s: float = DEFAULT_DIALOG_COOLDOWN_S,
        notify_cooldown_s: float = DEFAULT_NOTIFY_COOLDOWN_S,
    ) -> None:
        self._dialog_cooldown_s = dialog_cooldown_s
        self._notify_cooldown_s = notify_cooldown_s
        self._open: set[MacPermission] = set()
        self._last_dialog_at: dict[MacPermission, float] = {}
        self._last_notify_at: dict[MacPermission, float] = {}

    def is_dialog_open(self, permission: MacPermission) -> bool:
        return permission in self._open

    def _dialog_due(self, permission: MacPermission, now: float) -> bool:
        last = self._last_dialog_at.get(permission)
        return last is None or now - last >= self._dialog_cooldown_s

    def _open_dialog(self, permission: MacPermission, now: float) -> None:
        self._open.add(permission)
        self._last_dialog_at[permission] = now

    def on_use(self, permission: MacPermission, now: float) -> RepromptAction:
        """A gated action just failed for lack of *permission*; decide and record."""
        if permission in self._open:
            return RepromptAction.NONE
        if self._dialog_due(permission, now):
            self._open_dialog(permission, now)
            return RepromptAction.DIALOG
        last_note = self._last_notify_at.get(permission)
        if last_note is None or now - last_note >= self._notify_cooldown_s:
            self._last_notify_at[permission] = now
            return RepromptAction.NOTIFY
        return RepromptAction.NONE

    def on_startup(
        self, missing: AbstractSet[MacPermission], now: float
    ) -> frozenset[MacPermission]:
        """The launch-time probe found *missing*; return those to show a dialog for.

        Skips any permission whose dialog is open or was shown within the
        cool-down (e.g. the event-tap failure beat the probe to it). Never
        returns a notification — the startup probe is not a failed use.
        """
        due = frozenset(
            p for p in missing if p not in self._open and self._dialog_due(p, now)
        )
        for p in due:
            self._open_dialog(p, now)
        return due

    def dialog_closed(self, permission: MacPermission, now: float) -> None:
        """The dialog for *permission* was dismissed; start its cool-downs now.

        The dialog also counts as the latest notification, so a failure the
        user triggers right after dismissing it (e.g. the event-tap report
        that queued up behind the startup dialog) doesn't immediately follow
        it up with a redundant tray note.
        """
        self._open.discard(permission)
        self._last_dialog_at[permission] = now
        self._last_notify_at[permission] = now
