"""Startup phase timing — one greppable ``Startup timing:`` log line per launch.

Cold-launch cost on AV-heavy managed machines (Defender for Endpoint scanning
every freshly-installed DLL on first load) is invisible in the ordinary log
timestamps, which only start once logging is configured. ``StartupTimer``
records named phase boundaries from ``main()`` entry so the daemon can log a
single summary such as::

    Startup timing: interpreter 0.41s | adapters 0.08s | imports 0.52s | ... | total 3.10s

Pure apart from :func:`process_age_s`, a best-effort Windows-only reading of
how long the process existed before ``main()`` ran (interpreter + stdlib +
site-packages DLL load, which is where an AV scan of python*.dll lands).
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class StartupTimer:
    """Collects ``(phase, seconds)`` pairs between successive :meth:`mark` calls."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self._start = clock()
        self._last = self._start
        self._phases: list[tuple[str, float]] = []

    def mark(self, phase: str) -> None:
        """Close the phase that began at the previous mark (or construction)."""
        now = self._clock()
        self._phases.append((phase, now - self._last))
        self._last = now

    def summary(self, *, interpreter_s: float | None = None) -> str:
        parts: list[str] = []
        if interpreter_s is not None:
            parts.append(f"interpreter {interpreter_s:.2f}s")
        parts.extend(f"{name} {secs:.2f}s" for name, secs in self._phases)
        total = self._last - self._start + (interpreter_s or 0.0)
        parts.append(f"total {total:.2f}s")
        return "Startup timing: " + " | ".join(parts)


def process_age_s() -> float | None:
    """Seconds since this process was created, or ``None`` if unavailable.

    Windows only (``GetProcessTimes``); anything else, or any failure, is None —
    this is diagnostics and must never affect startup.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        # A private WinDLL, not the shared ctypes.windll: setting argtypes on the
        # shared kernel32 would leak into every other caller in the process.
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        filetime_p = ctypes.POINTER(wintypes.FILETIME)
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [filetime_p] * 4
        creation, exit_, kernel, user = (wintypes.FILETIME() for _ in range(4))
        ok = kernel32.GetProcessTimes(
            kernel32.GetCurrentProcess(),
            ctypes.byref(creation),
            ctypes.byref(exit_),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        # FILETIME: 100 ns ticks since 1601-01-01 (UTC).
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        created_unix = ticks / 10_000_000 - 11_644_473_600
        age = time.time() - created_unix
        return age if 0.0 <= age < 3600.0 else None
    except Exception:
        return None
