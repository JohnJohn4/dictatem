"""Tests for MacHardwareProbe — pure, no-CUDA-by-construction probe (#54).

The probe is a constant (macOS has no CUDA), so the interesting assertion is
the composition: feeding its profile to HardwareTierResolver must bake the CPU
tier (``base``/``cpu``/``int8``) that first-run config baking will persist.
"""

from __future__ import annotations

from dictatem.hardware.mac_probe import MacHardwareProbe
from dictatem.hardware.resolver import HardwareTierResolver
from dictatem.interfaces import HardwareProbe


class TestMacHardwareProbe:
    def test_reports_no_cuda(self) -> None:
        profile = MacHardwareProbe().probe()
        assert profile.cuda_available is False
        assert profile.total_vram_mb is None

    def test_satisfies_hardware_probe_protocol(self) -> None:
        assert isinstance(MacHardwareProbe(), HardwareProbe)

    def test_resolves_to_cpu_tier(self) -> None:
        resolved = HardwareTierResolver().resolve(MacHardwareProbe().probe())
        assert resolved.tier == "CPU"
        assert resolved.model == "base"
        assert resolved.device == "cpu"
        assert resolved.compute_type == "int8"
