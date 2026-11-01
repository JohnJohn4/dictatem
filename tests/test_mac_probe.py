"""Tests for MacHardwareProbe — pure, no-CUDA-by-construction probe (#54, #233).

macOS has no CUDA, so the interesting assertions are whether MLX is usable
(Apple Silicon + macOS 14+ + the mlx-whisper package, checked without importing
MLX) and the reported unified memory, and how the resulting profile composes
with HardwareTierResolver into the tier first-run baking will persist.

Every MLX test injects the package lookup: CI's macOS leg installs the
apple-gpu extra, so the real lookup would flip results there.
"""

from __future__ import annotations

import sys

from dictatem.hardware.mac_probe import MacHardwareProbe
from dictatem.hardware.resolver import HardwareTierResolver
from dictatem.interfaces import HardwareProbe

GB = 1024


def _probe(
    *,
    machine: str = "arm64",
    macos_version: str = "14.5",
    installed: frozenset[str] = frozenset({"mlx", "mlx_whisper"}),
    memory_mb: int | None = 16 * GB,
) -> MacHardwareProbe:
    return MacHardwareProbe(
        machine=machine,
        macos_version=macos_version,
        package_present=lambda name: name in installed,
        total_memory_mb=lambda: memory_mb,
    )


class TestMacHardwareProbe:
    def test_reports_no_cuda(self) -> None:
        profile = MacHardwareProbe().probe()
        assert profile.cuda_available is False
        assert profile.total_vram_mb is None

    def test_satisfies_hardware_probe_protocol(self) -> None:
        assert isinstance(MacHardwareProbe(), HardwareProbe)

    def test_intel_mac_resolves_to_cpu_tier(self) -> None:
        resolved = HardwareTierResolver().resolve(_probe(machine="x86_64").probe())
        assert resolved.tier == "CPU"
        assert resolved.model == "base"
        assert resolved.device == "cpu"
        assert resolved.compute_type == "int8"

    def test_apple_silicon_without_mlx_resolves_to_small_on_cpu(self) -> None:
        profile = _probe(installed=frozenset()).probe()
        assert profile.apple_silicon is True
        resolved = HardwareTierResolver().resolve(profile)
        assert resolved.tier == "Apple-Silicon"
        assert resolved.model == "small"
        assert resolved.device == "cpu"
        assert resolved.compute_type == "int8"

    def test_defaults_to_the_running_arch(self) -> None:
        import platform

        profile = MacHardwareProbe().probe()
        assert profile.apple_silicon is (platform.machine() == "arm64")


class TestMlxAvailability:
    """MLX is usable only for arm64 + macOS >= 14 + the package installed."""

    def test_arm64_macos_14_with_package_is_usable(self) -> None:
        assert _probe().probe().mlx_available is True

    def test_newer_macos_is_usable(self) -> None:
        assert _probe(macos_version="15.1.1").probe().mlx_available is True

    def test_macos_13_is_not_usable(self) -> None:
        assert _probe(macos_version="13.6.7").probe().mlx_available is False

    def test_package_absent_is_not_usable(self) -> None:
        assert _probe(installed=frozenset({"mlx"})).probe().mlx_available is False

    def test_rosetta_x86_64_is_not_apple_silicon_or_usable(self) -> None:
        # An x86_64 interpreter under Rosetta reports x86_64 even on an M-series
        # Mac: the safe choice is the plain CPU tier.
        profile = _probe(machine="x86_64").probe()
        assert profile.apple_silicon is False
        assert profile.mlx_available is False

    def test_unparsable_version_is_not_usable(self) -> None:
        for version in ("", "unknown", ".5"):
            assert _probe(macos_version=version).probe().mlx_available is False

    def test_package_lookup_is_by_name_not_import(self) -> None:
        asked: list[str] = []

        def lookup(name: str) -> bool:
            asked.append(name)
            return True

        MacHardwareProbe(
            machine="arm64",
            macos_version="14.0",
            package_present=lookup,
            total_memory_mb=lambda: None,
        ).probe()
        assert "mlx_whisper" in asked

    def test_default_lookup_never_imports_mlx(self) -> None:
        before = set(sys.modules)
        MacHardwareProbe(machine="arm64", macos_version="14.0").probe()
        imported = set(sys.modules) - before
        assert not {m for m in imported if m.split(".")[0] in {"mlx", "mlx_whisper"}}


class TestUnifiedMemory:
    def test_memory_is_reported(self) -> None:
        assert _probe(memory_mb=8 * GB).probe().unified_memory_mb == 8 * GB

    def test_unknown_memory_is_none(self) -> None:
        assert _probe(memory_mb=None).probe().unified_memory_mb is None

    def test_default_memory_reader_returns_an_int_or_none(self) -> None:
        memory = MacHardwareProbe().probe().unified_memory_mb
        assert memory is None or memory > 0


class TestProbeComposesWithResolver:
    def test_16gb_mlx_mac_resolves_to_apple_gpu(self) -> None:
        resolved = HardwareTierResolver().resolve(_probe(memory_mb=16 * GB).probe())
        assert resolved.tier == "Apple-GPU"
        assert resolved.device == "mlx"

    def test_8gb_mlx_mac_resolves_to_apple_gpu_low(self) -> None:
        resolved = HardwareTierResolver().resolve(_probe(memory_mb=8 * GB).probe())
        assert resolved.tier == "Apple-GPU-low"
