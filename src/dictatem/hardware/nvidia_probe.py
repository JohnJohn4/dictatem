"""NvidiaHardwareProbe — native HardwareProbe adapter (manual QA only).

Detects CUDA presence via ``nvidia-ml-py`` (module ``pynvml``), falling back to
``ctranslate2.get_cuda_device_count()`` when NVML can't confirm a usable GPU,
and reads total VRAM via NVML. Degrades gracefully: any import
or driver error yields a conservative profile rather than crashing, so the
resolver can still bake a working CPU (or VRAM-unknown) tier on first run.

Excluded from pyright/tests (see ``pyproject.toml`` ``[tool.pyright] exclude``);
its behaviour is exercised through ``FakeHardwareProbe`` in the unit suite.
"""

from __future__ import annotations

import contextlib
import logging
import os

from dictatem.hardware.cuda_presence import NvmlReport, decide_cuda_presence
from dictatem.types import HardwareProfile

logger = logging.getLogger(__name__)


class NvidiaHardwareProbe:
    """HardwareProbe implementation backed by nvidia-ml-py + ctranslate2.

    NVML answers first; CTranslate2's device count runs only when NVML can't
    positively confirm a usable GPU (see :mod:`dictatem.hardware.cuda_presence`).
    """

    def probe(self) -> HardwareProfile:
        presence = decide_cuda_presence(
            self._nvml_report(),
            ctranslate2_device_count=self._cuda_device_count,
            env=os.environ,
        )
        if not presence.available:
            logger.info("No CUDA device detected; resolving a CPU profile")
            return HardwareProfile(cuda_available=False, total_vram_mb=None)
        logger.info("CUDA device detected (via %s)", presence.decided_by)
        return HardwareProfile(cuda_available=True, total_vram_mb=presence.total_vram_mb)

    @staticmethod
    def _cuda_device_count() -> int:
        try:
            import ctranslate2  # type: ignore[import-not-found]

            return int(ctranslate2.get_cuda_device_count())
        except Exception as exc:  # pragma: no cover - native/driver dependent
            logger.warning("CUDA device count probe failed: %s", exc)
            return 0

    @staticmethod
    def _nvml_report() -> NvmlReport | None:
        """Query NVML for device count, driver CUDA version and GPU 0's VRAM.

        ``None`` when NVML itself is unusable (no NVIDIA driver, mismatch, ...);
        individual unreadable values become ``None`` fields.
        """
        try:
            import pynvml  # type: ignore[import-not-found]

            pynvml.nvmlInit()
        except Exception as exc:  # pragma: no cover - native/driver dependent
            logger.info("NVML unavailable (%s); using the CTranslate2 CUDA check", exc)
            return None
        try:
            count = int(pynvml.nvmlDeviceGetCount())
            try:
                cuda_version: int | None = int(pynvml.nvmlSystemGetCudaDriverVersion())
            except Exception:  # pragma: no cover - native/driver dependent
                cuda_version = None
            vram_mb: int | None = None
            if count > 0:
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    vram_mb = int(info.total) // (1024 * 1024)
                except Exception as exc:  # pragma: no cover - native/driver dependent
                    logger.warning(
                        "VRAM probe failed (%s); tier will assume modest VRAM", exc
                    )
            return NvmlReport(
                device_count=count, cuda_driver_version=cuda_version, total_vram_mb=vram_mb
            )
        except Exception as exc:  # pragma: no cover - native/driver dependent
            logger.info("NVML query failed (%s); using the CTranslate2 CUDA check", exc)
            return None
        finally:
            with contextlib.suppress(Exception):
                pynvml.nvmlShutdown()
