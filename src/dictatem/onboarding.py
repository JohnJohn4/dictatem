"""First-run onboarding gate for the Usage Guide auto-open (ADR-0021).

The [Usage Guide](../CONTEXT.md#usage-guide) auto-opens once the first time
Dictatem runs, so a new user meets it without hunting through the tray menu.
"Has the user seen it?" is persisted as a **sentinel marker file**
(``~/.dictatem/.usage_guide_seen``) — never a flag in ``config.toml``, which the
app never rewrites (ADR-0009/0022). The marker is written **only after the guide
is actually shown**, so a launch that defers the guide (e.g. mid macOS
permission flow, which relaunches the daemon on grant) leaves the marker absent
and the next clean launch re-attempts.

The gate decision and the marker path/write live here as pure, unit-tested logic
(filesystem only, no Qt); the daemon does the Qt open and calls
:func:`mark_usage_guide_seen` on show — that wiring is manual-QA.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def usage_guide_seen_marker(home: Path) -> Path:
    """Path to the "user has seen the Usage Guide" sentinel under ``~/.dictatem``."""
    return home / ".dictatem" / ".usage_guide_seen"


def should_auto_open_usage_guide(
    *, marker_path: Path, permissions_pending: bool
) -> bool:
    """Whether to auto-open the Usage Guide on this launch (ADR-0021).

    ``True`` iff the user has not already seen it (marker absent) **and** no
    first-run permission flow is still pending. On macOS, granting a permission
    relaunches the daemon, so while a permission dialog is being shown we defer
    the guide to the next clean launch rather than compete with the grant on the
    most fragile launch — and because the marker stays absent, that next launch
    still shows it.
    """
    if permissions_pending:
        return False
    return not marker_path.exists()


def mark_usage_guide_seen(marker_path: Path) -> None:
    """Record that the Usage Guide has been shown (write the sentinel marker).

    Called **only after** the guide is actually shown (ADR-0021). Best-effort,
    like the other ``~/.dictatem`` writes: an unwritable home logs and degrades
    rather than crashing the daemon — the cost is only that onboarding may show
    again next launch, never a failed start.
    """
    try:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.touch()
    except OSError:
        logger.warning(
            "Could not write the Usage Guide seen-marker at %s; onboarding may "
            "re-open next launch",
            marker_path,
            exc_info=True,
        )
