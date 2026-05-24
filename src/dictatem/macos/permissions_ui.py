"""Guided first-run permission dialog for macOS (#57 / ADR-0014) — manual QA only.

Shows the user a dialog explaining the missing **Accessibility** / **Input
Monitoring** grants, with a button per missing permission that deep-links into
the exact System Settings pane (the URLs come from the pure
``permission_map``), and copy about the one-time relaunch. It never grants on
the user's behalf — it only opens the right pane.

This module imports PySide6 (Qt) and ``AppKit`` (NSWorkspace, to open the
``x-apple.systempreferences:`` URL) and only runs on macOS. It is lazy-imported
inside ``daemon._start_macos_daemon`` — never at module top level
(``tests/test_import_safety.py``) — and is excluded from pyright/tests
(``pyproject.toml`` ``[tool.pyright] exclude``). The decision of which pane to
open for which gap is the pure, unit-tested ``map_missing_permissions``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dictatem.macos.permission_map import (
    PermissionGuidance,
    map_missing_permissions,
)

if TYPE_CHECKING:
    from dictatem.macos.permission_map import MacPermission

logger = logging.getLogger(__name__)


def open_settings_pane(url: str) -> None:
    """Open the System Settings pane addressed by *url* (deep-link).

    Uses ``NSWorkspace.openURL_`` so the ``x-apple.systempreferences:`` scheme is
    handled by System Settings. Best-effort: a failure is logged, never raised,
    so a broken deep-link can't crash startup.
    """
    try:
        from AppKit import NSURL, NSWorkspace  # type: ignore[import-not-found]

        ns_url = NSURL.URLWithString_(url)
        NSWorkspace.sharedWorkspace().openURL_(ns_url)
    except Exception:  # pragma: no cover - native/PyObjC dependent
        logger.warning("Failed to open Settings pane %s", url, exc_info=True)


def guide_missing_permissions(missing: frozenset[MacPermission]) -> bool:
    """Show the guided dialog for the *missing* permissions; return False if any.

    When nothing is missing this is a silent no-op returning ``True`` (startup
    proceeds). Otherwise a modal dialog is shown with one deep-link button per
    missing pane and the relaunch instructions; it returns ``False`` so the
    caller knows the daemon is running under-permissioned until the user grants
    and relaunches. Wrapped so a UI hiccup can never crash startup.
    """
    prompt = map_missing_permissions(missing)
    if prompt.all_granted:
        return True

    try:
        _show_dialog(prompt.title, prompt.message, prompt.steps)
    except Exception:  # pragma: no cover - native/PyObjC dependent
        logger.error("Failed to show permission dialog", exc_info=True)
        # Fall back to logging the exact panes so a headless launch still guides.
        for step in prompt.steps:
            logger.warning(
                "Grant %s in System Settings: %s (%s)",
                step.pane,
                step.url,
                step.reason,
            )
    return False


def _show_dialog(
    title: str, message: str, steps: tuple[PermissionGuidance, ...]
) -> None:
    """Render the modal Qt dialog with one deep-link button per missing pane."""
    from PySide6.QtWidgets import (  # type: ignore[import-not-found]
        QDialog,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    dialog = QDialog()
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)

    label = QLabel(message)
    label.setWordWrap(True)
    layout.addWidget(label)

    for step in steps:
        button = QPushButton(f"Open {step.pane} settings")
        button.setToolTip(f"Needed to {step.reason}")
        # Bind the URL per-button (default-arg avoids the late-binding closure
        # bug where every button would open the last URL).
        button.clicked.connect(lambda _checked=False, url=step.url: open_settings_pane(url))
        layout.addWidget(button)

    done = QPushButton("I've granted these — I'll relaunch")
    done.clicked.connect(dialog.accept)
    layout.addWidget(done)

    dialog.exec()
