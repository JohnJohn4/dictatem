"""Fake foreground window tracker for testing paste pipeline logic."""

from __future__ import annotations


class FakeForegroundTracker:
    def __init__(self, target_id: int = 1234) -> None:
        self._target_id: int = target_id
        self.captured: list[int] = []
        self.restored: list[int] = []

    def capture(self) -> int:
        self.captured.append(self._target_id)
        return self._target_id

    def restore(self, target_id: int) -> None:
        self.restored.append(target_id)

    def set_target(self, target_id: int) -> None:
        """Test affordance: simulate the foreground changing (focus drift, #97).

        After this, ``capture()`` returns the new ``target_id`` — modelling the
        user clicking into another window between record-start and paste.
        """
        self._target_id = target_id
