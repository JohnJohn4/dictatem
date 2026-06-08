"""macOS activation/process-type — PyObjC + Carbon via ctypes (manual QA only).

This module only works on macOS; it is imported lazily from
``daemon._run_daemon`` (and ``permissions.qt_dialog``) behind a ``sys.platform``
guard, never at module level by any pure-core module. Excluded from pyright
(see ``pyproject.toml`` ``[tool.pyright] exclude``) because AppKit /
ApplicationServices are unresolvable off-macOS.

Why this exists: the generated ``.app``'s ``Info.plist`` sets ``LSUIElement``,
but real-Mac QA (#61) showed the daemon runs as the uv-managed ``python3.12``
the shim execs into — not as the bundle — so ``LSUIElement`` never applies.
We make the *running process* a menu-bar accessory instead.

The first attempt, ``NSApplication.setActivationPolicy_(Accessory)``, removed
the Dock icon but the menu-bar **status item still did not appear** under a
LaunchServices/``.app`` launch (it did from a foreground Terminal launch). The
policy is set, but a process launched via LaunchServices is not *transformed*
to a UI-element process, and that transform is what registers it with the
status bar. The documented fix for Qt system-tray apps in this exact situation
is the Carbon ``TransformProcessType(..., kProcessTransformToUIElementApplication)``
(ApplicationServices), which both drops the Dock icon and performs the
transform — so the status item appears. None of this fixes the TCC identity
label, which still needs a signed bundle (#91).
"""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac activation policy requires macOS")

from AppKit import NSApplication

# Carbon ProcessManager constants (ApplicationServices). kCurrentProcess goes in
# the low long of the PSN; UIElement == 4 (the menu-bar accessory transform).
_K_CURRENT_PROCESS = 2
_K_PROCESS_TRANSFORM_TO_UI_ELEMENT_APPLICATION = 4


class _ProcessSerialNumber(ctypes.Structure):
    _fields_ = [
        ("highLongOfPSN", ctypes.c_uint32),
        ("lowLongOfPSN", ctypes.c_uint32),
    ]


def set_accessory_activation_policy() -> None:
    """Transform the running process into a menu-bar accessory (no Dock icon).

    Called once right after the ``QApplication`` exists and before the tray
    icon is shown. Uses ``TransformProcessType`` so a LaunchServices-launched
    process registers with the status bar (a plain ``setActivationPolicy_``
    does not — QA #54/#61). Best-effort: a failure must never kill startup,
    the daemon is still usable via the hotkey.
    """
    try:
        app_services = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework"
            "/ApplicationServices"
        )
        app_services.TransformProcessType.argtypes = [
            ctypes.POINTER(_ProcessSerialNumber),
            ctypes.c_uint32,
        ]
        psn = _ProcessSerialNumber(0, _K_CURRENT_PROCESS)
        app_services.TransformProcessType(
            ctypes.byref(psn),
            ctypes.c_uint32(_K_PROCESS_TRANSFORM_TO_UI_ELEMENT_APPLICATION),
        )
    except Exception:
        logger.warning(
            "Could not transform process to a menu-bar accessory", exc_info=True
        )


def activate_app() -> None:
    """Bring the accessory app to the front so a modal dialog grabs focus.

    Accessory apps are never auto-activated, so a ``QMessageBox`` — our guided
    permission prompts — can open behind the frontmost app and be dismissed on
    the first click elsewhere (observed in QA, #57). Call this right before
    showing one. Best-effort. ``activateIgnoringOtherApps_`` is soft-deprecated
    but remains the working way to front an accessory app on current macOS.
    """
    try:
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        logger.warning("Could not bring the app to the front", exc_info=True)
