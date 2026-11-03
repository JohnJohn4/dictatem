"""Pure CUDA-presence decision for :class:`NvidiaHardwareProbe` (no native imports).

The probe runs on every launch, before the tray exists. Its old CUDA check,
``import ctranslate2; get_cuda_device_count()``, loads the whole CTranslate2 DLL
tree, which costs 7-15 s on a cold launch under an endpoint scanner (work-laptop
QA, 2026-11-02) versus <1 s for NVML. So NVML answers first, and the
CTranslate2 check runs only when NVML can't *positively* confirm a usable GPU.

The shortcut is deliberately conservative. Every case where NVML and
``cudaGetDeviceCount`` could disagree takes the old path:

- NVML unavailable or erroring (no NVIDIA driver, driver/library mismatch,
  containers) -> CTranslate2 decides, exactly as before.
- NVML sees zero devices -> CTranslate2 decides.
- The driver's CUDA version is older than the CUDA 12 runtime the
  ``nvidia-*-cu12`` wheels and CTranslate2 need -> CTranslate2 decides (and
  will report 0, as before).
- ``CUDA_VISIBLE_DEVICES`` is set: CUDA honours it, NVML does not ->
  CTranslate2 decides.

There is no runtime CPU fallback for ``cuda`` (ADR-0009 is a launch-time
fallback), so the shortcut must never claim a GPU CTranslate2 would reject.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

# The CUDA 12 runtime needs a driver that reports CUDA >= 12.0 (minor-version
# compatibility). NVML encodes it as 1000 * major + 10 * minor. Raise this if the
# CUDA wheels in pyproject's ``runtime-gpu`` extra ever move to a newer major.
MIN_CUDA_DRIVER_VERSION = 12000


@dataclass(frozen=True)
class NvmlReport:
    """What NVML could tell us; ``None`` fields are unreadable values."""

    device_count: int
    cuda_driver_version: int | None
    total_vram_mb: int | None


@dataclass(frozen=True)
class CudaPresence:
    available: bool
    total_vram_mb: int | None
    # "nvml" when the shortcut decided, "ctranslate2" when the old check did.
    decided_by: str


def nvml_confirms_cuda(nvml: NvmlReport | None, env: Mapping[str, str]) -> bool:
    """True only when NVML alone is enough to say CUDA will work."""
    if nvml is None or "CUDA_VISIBLE_DEVICES" in env:
        return False
    return (
        nvml.device_count > 0
        and nvml.cuda_driver_version is not None
        and nvml.cuda_driver_version >= MIN_CUDA_DRIVER_VERSION
    )


def decide_cuda_presence(
    nvml: NvmlReport | None,
    *,
    ctranslate2_device_count: Callable[[], int],
    env: Mapping[str, str],
) -> CudaPresence:
    """Decide CUDA presence, importing CTranslate2 only when NVML can't."""
    if nvml_confirms_cuda(nvml, env):
        assert nvml is not None
        return CudaPresence(True, nvml.total_vram_mb, decided_by="nvml")
    available = ctranslate2_device_count() > 0
    vram = nvml.total_vram_mb if (available and nvml is not None) else None
    return CudaPresence(available, vram, decided_by="ctranslate2")
