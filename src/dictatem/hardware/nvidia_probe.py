"""NvidiaHardwareProbe — native HardwareProbe adapter (manual QA only).

Detects CUDA presence via ``ctranslate2.get_cuda_device_count()`` and total
VRAM via ``nvidia-ml-py`` (module ``pynvml``). Degrades gracefully: any import
or driver error yields a conservative profile rather than crashing, so the
resolver can still bake a working CPU (or VRAM-unknown) tier on first run.

Excluded from pyright/tests (see ``pyproject.toml`` ``[tool.pyright] exclude``);
its behaviour is exercised through ``FakeHardwareProbe`` in the unit suite.
"""

from __future__ import annotations

import logging

from dictatem.types import HardwareProfile

logger = logging.getLogger(__name__)


class NvidiaHardwareProbe:
    """HardwareProbe implementation backed by ctranslate2 + nvidia-ml-py."""

    def probe(self) -> HardwareProfile:
        cuda_available = self._cuda_device_count() > 0
        if not cuda_available:
            logger.info("No CUDA device detected; resolving a CPU profile")
            return HardwareProfile(cuda_available=False, total_vram_mb=None)

        vram_mb = self._total_vram_mb()
        return HardwareProfile(cuda_available=True, total_vram_mb=vram_mb)

    @staticmethod
    def _cuda_device_count() -> int:
        try:
            import ctranslate2  # type: ignore[import-not-found]

            return int(ctranslate2.get_cuda_device_count())
        except Exception as exc:  # pragma: no cover - native/driver dependent
            logger.warning("CUDA device count probe failed: %s", exc)
            return 0

    @staticmethod
    def _total_vram_mb() -> int | None:
        """Return total VRAM in MB for the first GPU, or None if unreadable."""
        try:
            import pynvml  # type: ignore[import-not-found]

            pynvml.nvmlInit()
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                return int(info.total) // (1024 * 1024)
            finally:
                pynvml.nvmlShutdown()
        except Exception as exc:  # pragma: no cover - native/driver dependent
            logger.warning("VRAM probe failed (%s); tier will assume modest VRAM", exc)
            return None
