"""Fake hardware probe for testing the tier resolver and first-run baking."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictatem.types import HardwareProfile


class FakeHardwareProbe:
    """Returns a fabricated HardwareProfile and records how often it was asked.

    The ``probe_count`` lets tests assert that the probe is consulted exactly
    once on first run and never on later launches (see ADR-0007).
    """

    def __init__(self, profile: HardwareProfile) -> None:
        self._profile = profile
        self.probe_count: int = 0

    def probe(self) -> HardwareProfile:
        self.probe_count += 1
        return self._profile
