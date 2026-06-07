"""macOS TCC permission check — the native half behind the pure mapper (#57).

This module requires PyObjC (Quartz) and only works on macOS. It is NOT
imported at module level by any pure-core module; the darwin starter imports
it lazily, which is how the macOS CI leg proves the CoreGraphics symbols
resolve. Like the other native adapters it is manual-QA only and excluded
from pyright; the missing-permissions → guidance decision is pure and
unit-tested (``permissions.mapper``).

Probing uses the CoreGraphics preflight pair (ADR-0014) — *not*
``AXIsProcessTrusted()``, which lives in ApplicationServices and would add a
whole pyobjc framework for no behavioural gain:

- ``CGPreflightPostEventAccess`` — may this process post synthetic events?
  That is exactly Dictatem's Accessibility need (``CGEventPost`` in
  ``paste.mac_keystroke``).
- ``CGPreflightListenEventAccess`` — may it observe keyboard events? That is
  the Input Monitoring need (the ``CGEventTap`` in ``hotkey.mac_hook``, whose
  tap-creation failure remains the runtime backstop signal).

For anything missing, the matching ``CGRequest*`` call asks macOS to register
Dictatem in the System Settings pane (toggle ready — no manual "+" hunt) and
show its native one-time prompt; TCC remembers a denial, so this never
re-prompts on every launch. Requesting is not granting (ADR-0014): only the
user can flip the toggle, and the guided dialog built from the returned
guidance explains that plus the one-time relaunch.
"""

from __future__ import annotations

import logging
import sys

if sys.platform != "darwin":
    raise ImportError("mac_tcc requires macOS")

from Quartz import (
    CGPreflightListenEventAccess,
    CGPreflightPostEventAccess,
    CGRequestListenEventAccess,
    CGRequestPostEventAccess,
)

from dictatem.permissions.mapper import (
    MacPermission,
    PermissionGuidance,
    map_missing_permissions,
)

logger = logging.getLogger(__name__)


def check_permissions() -> tuple[PermissionGuidance, ...]:
    """Probe TCC, request registration for anything missing, return guidance.

    The empty tuple is the all-granted case — the caller shows no dialog.
    Microphone is deliberately not probed: macOS shows its standard automatic
    TCC prompt on first capture (see ``permissions.mapper``).
    """
    missing: set[MacPermission] = set()
    if not CGPreflightPostEventAccess():
        missing.add(MacPermission.ACCESSIBILITY)
        CGRequestPostEventAccess()
    if not CGPreflightListenEventAccess():
        missing.add(MacPermission.INPUT_MONITORING)
        CGRequestListenEventAccess()
    if missing:
        logger.info(
            "Missing macOS permissions: %s",
            ", ".join(sorted(p.name for p in missing)),
        )
    return map_missing_permissions(missing)
