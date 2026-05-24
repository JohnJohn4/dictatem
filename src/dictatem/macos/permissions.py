"""Native macOS TCC permission detection (#57 / ADR-0014) — manual QA only.

Detects whether Dictatem holds the **Accessibility** and **Input Monitoring**
grants it needs, using the OS-blessed checks:

- Accessibility: ``AXIsProcessTrusted()`` (ApplicationServices). Returns whether
  the current process may drive AXUIElement / synthetic events.
- Input Monitoring: attempt to create a listen-only ``CGEventTap``. macOS returns
  ``NULL`` when the process lacks the Input Monitoring grant, so a failed tap
  creation is the documented signal — there is no boolean API for it.

This module imports PyObjC (Quartz, ApplicationServices) and only works on macOS.
It is NEVER imported at module top level by any pure core; it is lazy-imported
inside ``daemon._start_macos_daemon`` (``tests/test_import_safety.py``). It is
excluded from pyright/tests (``pyproject.toml`` ``[tool.pyright] exclude``); the
pure decision of which pane to open for which gap lives in ``permission_map.py``
and is unit-tested. We never grant on the user's behalf — we only detect.
"""

from __future__ import annotations

import logging

from dictatem.macos.permission_map import MacPermission

logger = logging.getLogger(__name__)


def is_accessibility_trusted() -> bool:
    """Return whether this process holds the Accessibility grant.

    Uses ``AXIsProcessTrusted()`` — the non-prompting variant — so detection
    never pops a system dialog of its own; the guided dialog (with deep-links)
    is ours to show.
    """
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore[import-not-found]

        return bool(AXIsProcessTrusted())
    except Exception:  # pragma: no cover - native/PyObjC dependent
        logger.warning("AXIsProcessTrusted probe failed", exc_info=True)
        # Fail "not trusted" so the user is guided rather than silently blocked.
        return False


def is_input_monitoring_granted() -> bool:
    """Return whether this process may create a keyboard CGEventTap.

    There is no boolean Input-Monitoring API; the OS signal is that
    ``CGEventTapCreate`` returns ``NULL`` without the grant. We create a
    listen-only tap and immediately tear it down, treating a ``None`` handle as
    "not granted".
    """
    try:
        import Quartz  # type: ignore[import-not-found]

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            _noop_tap_callback,
            None,
        )
        if tap is None:
            return False
        # Tear the probe tap down immediately; the real hook creates its own.
        import CoreFoundation  # type: ignore[import-not-found]

        CoreFoundation.CFMachPortInvalidate(tap)
        return True
    except Exception:  # pragma: no cover - native/PyObjC dependent
        logger.warning("Input Monitoring (CGEventTap) probe failed", exc_info=True)
        return False


def _noop_tap_callback(proxy, type_, event, refcon):  # noqa: ANN001, ANN202, ARG001
    """Tap callback used only by the probe tap; passes the event through."""
    return event


def probe_macos_permissions() -> frozenset[MacPermission]:
    """Return the SET of permissions Dictatem still NEEDS (i.e. not granted).

    The pure ``permission_map.map_missing_permissions`` turns this set into the
    guided dialog. An empty set means everything is granted and startup proceeds
    silently.
    """
    missing: set[MacPermission] = set()
    if not is_accessibility_trusted():
        missing.add(MacPermission.ACCESSIBILITY)
    if not is_input_monitoring_granted():
        missing.add(MacPermission.INPUT_MONITORING)
    if missing:
        logger.info("Missing macOS permissions: %s", sorted(p.value for p in missing))
    return frozenset(missing)
