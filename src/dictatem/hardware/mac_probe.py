"""MacHardwareProbe — pure HardwareProbe for macOS (#54).

Apple-Silicon Macs have no CUDA, so the probe is a constant: report a no-CUDA
profile and let :class:`~dictatem.hardware.resolver.HardwareTierResolver` bake
the CPU tier (``base``/``cpu``/``int8``, see ADR-0013) on first run. Unlike
:class:`~dictatem.hardware.nvidia_probe.NvidiaHardwareProbe` there is nothing
native to query, so this module stays pyright-checked and unit-tested.

A Metal-backed (mlx-whisper) tier is an explicit ADR-0013 follow-up; when it
lands, this probe is where Apple-GPU detection would go.
"""

from __future__ import annotations

import logging

from dictatem.types import HardwareProfile

logger = logging.getLogger(__name__)


class MacHardwareProbe:
    """HardwareProbe implementation for macOS — always a no-CUDA profile."""

    def probe(self) -> HardwareProfile:
        logger.info("macOS: no CUDA by construction; resolving a CPU profile")
        return HardwareProfile(cuda_available=False, total_vram_mb=None)
