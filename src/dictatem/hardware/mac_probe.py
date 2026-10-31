"""MacHardwareProbe — pure HardwareProbe for macOS (#54, #233).

Macs have no CUDA, so the probe reports a no-CUDA profile. It also reports:

- ``apple_silicon``: the interpreter is arm64. An x86_64 Python under Rosetta
  reports x86_64 and gets the CPU tier, the safe choice for an emulated
  interpreter.
- ``mlx_available``: Apple Silicon, macOS 14 or later, and the mlx-whisper
  package installed (the apple-gpu extra). Package presence is a spec lookup by
  name; MLX is never imported and Metal is never touched here, so probing stays
  cheap and cannot crash. A broken MLX install is caught later by the runtime
  fallback (#232).
- ``unified_memory_mb``: total physical memory, or ``None`` if unreadable. The
  resolver splits the Apple-GPU tiers on it.

Every input is injectable, so the module stays pyright-checked and unit-tested
on any OS, unlike the native
:class:`~dictatem.hardware.nvidia_probe.NvidiaHardwareProbe`.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import platform
import sys
from typing import TYPE_CHECKING

from dictatem.types import HardwareProfile

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# MLX's oldest supported macOS (mlx >= 0.30 wheels target macOS 14).
MLX_MIN_MACOS_MAJOR = 14
# The import name of the mlx-whisper engine shipped by the apple-gpu extra.
MLX_WHISPER_PACKAGE = "mlx_whisper"


def _package_present(name: str) -> bool:
    """True if a top-level package *name* is installed, without importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _read_total_memory_mb() -> int | None:
    """Total physical memory in MB, or ``None`` when it can't be read."""
    if sys.platform == "win32":
        return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        return None
    if pages <= 0 or page_size <= 0:
        return None
    return pages * page_size // (1024 * 1024)


def _macos_major(version: str) -> int | None:
    """The major version of a ``platform.mac_ver()`` string, or ``None``."""
    head = version.strip().split(".", 1)[0]
    return int(head) if head.isdigit() else None


class MacHardwareProbe:
    """HardwareProbe implementation for macOS — always a no-CUDA profile."""

    def __init__(
        self,
        machine: str | None = None,
        *,
        macos_version: str | None = None,
        package_present: Callable[[str], bool] | None = None,
        total_memory_mb: Callable[[], int | None] | None = None,
    ) -> None:
        # All injectable for tests; the defaults read the running interpreter.
        self._machine = machine if machine is not None else platform.machine()
        self._macos_version = (
            macos_version if macos_version is not None else platform.mac_ver()[0]
        )
        self._package_present = package_present or _package_present
        self._total_memory_mb = total_memory_mb or _read_total_memory_mb

    def probe(self) -> HardwareProfile:
        apple_silicon = self._machine == "arm64"
        major = _macos_major(self._macos_version)
        mlx_available = (
            apple_silicon
            and major is not None
            and major >= MLX_MIN_MACOS_MAJOR
            and self._package_present(MLX_WHISPER_PACKAGE)
        )
        memory_mb = self._total_memory_mb()
        logger.info(
            "macOS %s: no CUDA by construction; arch=%s apple_silicon=%s "
            "mlx_available=%s unified_memory=%s",
            self._macos_version or "unknown",
            self._machine,
            apple_silicon,
            mlx_available,
            "unknown" if memory_mb is None else f"{memory_mb} MB",
        )
        return HardwareProfile(
            cuda_available=False,
            total_vram_mb=None,
            apple_silicon=apple_silicon,
            mlx_available=mlx_available,
            unified_memory_mb=memory_mb,
        )
