"""Skeleton daemon — dependency injection wiring and platform gate."""

from __future__ import annotations

import sys

from dictatem.exceptions import PlatformNotSupportedError


def main() -> None:
    """Entry point for the Dictatem daemon.

    On Linux, raises PlatformNotSupportedError immediately.
    On Windows, wires adapters via Protocols and starts the event loop.
    """
    if sys.platform != "win32":
        raise PlatformNotSupportedError(
            "Dictatem is Windows-only. "
            f"Current platform: {sys.platform}"
        )

    # Windows-only startup (replaced in subsequent slices)
    _start_windows_daemon()


def _start_windows_daemon() -> None:
    """Wire Windows adapters and start the Qt event loop.

    Stub for Slice 0 — real implementation arrives in later slices.
    """
