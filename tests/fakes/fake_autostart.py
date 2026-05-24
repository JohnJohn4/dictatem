"""In-memory fake AutostartRegistrar for testing the daemon's reconcile wiring.

Holds the autostart "entry" as a single bool and records each call so tests can
assert the daemon applied the right action without touching the registry.
"""

from __future__ import annotations


class FakeAutostartRegistrar:
    def __init__(self, *, enabled: bool = False) -> None:
        self._enabled = enabled
        self.enable_calls = 0
        self.disable_calls = 0

    def enable(self) -> None:
        self.enable_calls += 1
        self._enabled = True

    def disable(self) -> None:
        self.disable_calls += 1
        self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled
