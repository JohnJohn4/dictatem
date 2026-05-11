"""Skeleton daemon — dependency injection wiring and platform gate."""

from __future__ import annotations

import sys

from dictatem.exceptions import PlatformNotSupportedError


def main() -> None:
    """Entry point for the Dictatem daemon."""
    if sys.platform != "win32":
        raise PlatformNotSupportedError(
            "Dictatem is Windows-only. "
            f"Current platform: {sys.platform}"
        )

    # Windows-only startup (replaced in subsequent slices)
    _start_windows_daemon()


def _start_windows_daemon() -> None:
    """Wire Windows adapters and start the Qt event loop."""
