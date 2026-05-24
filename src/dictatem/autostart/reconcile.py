"""Pure autostart reconcile decision (#55 / ADR-0012).

Given the desired ``config.startup.autostart`` flag and whether the OS autostart
entry currently exists, decide the action to apply: register it, remove it, or
leave it alone. No registry, no I/O — every input arrives as a bool, so the full
decision table is unit-testable on any OS. Mirrors
``HardwareTierResolver.reconcile``: the daemon applies the returned action via an
``AutostartRegistrar`` adapter on launch.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictatem.interfaces import AutostartRegistrar


class AutostartAction(enum.Enum):
    """What the daemon should do to the OS autostart entry on reconcile."""

    ENABLE = "enable"
    DISABLE = "disable"
    NOOP = "noop"


def reconcile_autostart(*, desired: bool, currently_enabled: bool) -> AutostartAction:
    """Return the action that drives the OS entry to match *desired*.

    Idempotent: when the entry already matches the flag the action is
    ``NOOP``. Pure — no registry access, no I/O.
    """
    if desired and not currently_enabled:
        return AutostartAction.ENABLE
    if not desired and currently_enabled:
        return AutostartAction.DISABLE
    return AutostartAction.NOOP


def apply_autostart(
    *, desired: bool, registrar: AutostartRegistrar
) -> AutostartAction:
    """Reconcile the OS autostart entry to *desired* via *registrar*.

    Reads the current entry, runs the pure :func:`reconcile_autostart` decision,
    and applies it through the registrar. The only I/O is delegated to the
    registrar adapter; the decision stays pure. Returns the action taken so the
    caller can log it. This is the glue the daemon runs on launch and the tray
    "Start at login" toggle runs after flipping the flag.
    """
    action = reconcile_autostart(
        desired=desired, currently_enabled=registrar.is_enabled()
    )
    if action is AutostartAction.ENABLE:
        registrar.enable()
    elif action is AutostartAction.DISABLE:
        registrar.disable()
    return action
