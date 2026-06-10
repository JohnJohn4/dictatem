"""Fake DaemonStopper for testing the uninstall/upgrade stop wiring."""

from __future__ import annotations


class FakeDaemonStopper:
    """Records that a stop was requested and returns a configurable PID list."""

    def __init__(self, stopped: list[int] | None = None) -> None:
        self._stopped = stopped if stopped is not None else []
        self.call_count = 0

    def stop_running_daemons(self) -> list[int]:
        self.call_count += 1
        return list(self._stopped)
