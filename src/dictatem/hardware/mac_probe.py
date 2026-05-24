"""MacHardwareProbe — native HardwareProbe adapter for macOS (manual QA only).

macOS v1 transcribes on CPU faster-whisper (ADR-0013): the CTranslate2 engine has
no Metal backend, so there is no CUDA/GPU to detect on a Mac. This probe therefore
always reports a **no-CUDA** profile, so the existing pure ``HardwareTierResolver``
bakes the CPU tier (``base``/``cpu``/``int8``) into the config on first run — the
same code path the Windows CPU-only case already uses.

There is deliberately no native inspection here (no Metal/MLX probing): the
mlx-whisper Apple-Silicon tier is a FUTURE follow-up (ADR-0013), at which point a
real Apple-Silicon probe would slot in behind the same HardwareProbe Protocol.

Excluded from pyright/tests (see ``pyproject.toml`` ``[tool.pyright] exclude``);
its CPU-profile behaviour is exercised through ``FakeHardwareProbe`` in the unit
suite, and the resolver it feeds is itself pure and unit-tested.
"""

from __future__ import annotations

import logging

from dictatem.types import HardwareProfile

logger = logging.getLogger(__name__)


class MacHardwareProbe:
    """HardwareProbe implementation for macOS — always a CPU profile (ADR-0013)."""

    def probe(self) -> HardwareProfile:
        logger.info(
            "macOS: reporting a no-CUDA profile so the CPU tier is resolved "
            "(faster-whisper on CPU, see ADR-0013)"
        )
        return HardwareProfile(cuda_available=False, total_vram_mb=None)
