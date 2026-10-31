"""MacHardwareProbe — pure HardwareProbe for macOS (#54).

Macs have no CUDA, so the probe reports a no-CUDA profile, flagging Apple
Silicon (arm64) so :class:`~dictatem.hardware.resolver.HardwareTierResolver`
bakes the Apple-Silicon tier (``small``/``cpu``/``int8``) rather than the plain
CPU tier (``base``, ADR-0013) on first run. Intel Macs keep the CPU tier. Unlike
:class:`~dictatem.hardware.nvidia_probe.NvidiaHardwareProbe` there is nothing
native to query, so this module stays pyright-checked and unit-tested.

A Metal-backed (mlx-whisper) tier is an explicit ADR-0013 follow-up; when it
lands, this probe is where Apple-GPU detection would go.
"""

from __future__ import annotations

import logging
import platform

from dictatem.types import HardwareProfile

logger = logging.getLogger(__name__)


class MacHardwareProbe:
    """HardwareProbe implementation for macOS — always a no-CUDA profile."""

    def __init__(self, machine: str | None = None) -> None:
        # Injectable for tests; defaults to the running interpreter's arch. An
        # x86_64 Python under Rosetta reports x86_64 and gets the CPU tier,
        # which is the safe choice for an emulated interpreter.
        self._machine = machine if machine is not None else platform.machine()

    def probe(self) -> HardwareProfile:
        apple_silicon = self._machine == "arm64"
        logger.info(
            "macOS: no CUDA by construction; arch=%s apple_silicon=%s",
            self._machine,
            apple_silicon,
        )
        return HardwareProfile(
            cuda_available=False, total_vram_mb=None, apple_silicon=apple_silicon
        )
