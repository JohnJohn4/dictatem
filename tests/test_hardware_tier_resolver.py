"""Tests for HardwareTierResolver — pure, table-driven tier selection (#36).

Covers every tier boundary: no CUDA; CUDA with VRAM <3 / 3-6 / >=6 GB; and
CUDA with unknown VRAM. The resolver maps a HardwareProfile to a resolved
(whisper model, device, compute_type) plus a Transform (Ollama) model tag.
"""

from __future__ import annotations

from dictatem.hardware.resolver import HardwareTierResolver
from dictatem.types import HardwareProfile


class TestGpuHighTier:
    """CUDA present with >= 6 GB VRAM -> the most capable tier."""

    def test_resolves_large_turbo_float16(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=True, total_vram_mb=8192)
        resolved = resolver.resolve(profile)
        assert resolved.model == "large-v3-turbo"
        assert resolved.device == "cuda"
        assert resolved.compute_type == "float16"
        assert resolved.transform_model == "gemma4:e4b"


class TestGpuMidTier:
    """CUDA present with 3-6 GB VRAM -> mid tier (small / int8_float16)."""

    def test_resolves_small_int8_float16(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=True, total_vram_mb=4096)
        resolved = resolver.resolve(profile)
        assert resolved.model == "small"
        assert resolved.device == "cuda"
        assert resolved.compute_type == "int8_float16"
        assert resolved.transform_model == "llama3.2:1b"


class TestGpuLowTier:
    """CUDA present with < 3 GB VRAM -> low tier (base / int8_float16)."""

    def test_resolves_base_int8_float16(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=True, total_vram_mb=2048)
        resolved = resolver.resolve(profile)
        assert resolved.model == "base"
        assert resolved.device == "cuda"
        assert resolved.compute_type == "int8_float16"
        assert resolved.transform_model == "llama3.2:1b"


class TestCpuTier:
    """No CUDA -> CPU tier; the app must still start and transcribe."""

    def test_resolves_base_cpu_int8(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=False, total_vram_mb=None)
        resolved = resolver.resolve(profile)
        assert resolved.model == "base"
        assert resolved.device == "cpu"
        assert resolved.compute_type == "int8"
        assert resolved.transform_model == "llama3.2:1b"

    def test_cpu_even_when_vram_reported(self) -> None:
        # A profile could in principle carry VRAM with cuda_available False;
        # absence of CUDA dominates — never select a cuda device.
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=False, total_vram_mb=16384)
        resolved = resolver.resolve(profile)
        assert resolved.device == "cpu"


class TestGpuUnknownVramTier:
    """CUDA present but VRAM unreadable -> conservative GPU tier, never crash."""

    def test_resolves_conservatively(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=True, total_vram_mb=None)
        resolved = resolver.resolve(profile)
        assert resolved.device == "cuda"
        assert resolved.model == "small"
        assert resolved.compute_type == "int8_float16"


class TestTierBoundaries:
    """Threshold edges resolve to the higher tier (>= is inclusive)."""

    def test_exactly_6gb_is_high(self) -> None:
        resolver = HardwareTierResolver()
        resolved = resolver.resolve(
            HardwareProfile(cuda_available=True, total_vram_mb=6 * 1024)
        )
        assert resolved.model == "large-v3-turbo"

    def test_just_below_6gb_is_mid(self) -> None:
        resolver = HardwareTierResolver()
        resolved = resolver.resolve(
            HardwareProfile(cuda_available=True, total_vram_mb=6 * 1024 - 1)
        )
        assert resolved.model == "small"

    def test_exactly_3gb_is_mid(self) -> None:
        resolver = HardwareTierResolver()
        resolved = resolver.resolve(
            HardwareProfile(cuda_available=True, total_vram_mb=3 * 1024)
        )
        assert resolved.model == "small"

    def test_just_below_3gb_is_low(self) -> None:
        resolver = HardwareTierResolver()
        resolved = resolver.resolve(
            HardwareProfile(cuda_available=True, total_vram_mb=3 * 1024 - 1)
        )
        assert resolved.model == "base"


class TestAutoSelectionInvariants:
    """Invariants that hold across every tier the resolver can produce."""

    PROFILES = [
        HardwareProfile(cuda_available=True, total_vram_mb=24576),
        HardwareProfile(cuda_available=True, total_vram_mb=8192),
        HardwareProfile(cuda_available=True, total_vram_mb=4096),
        HardwareProfile(cuda_available=True, total_vram_mb=2048),
        HardwareProfile(cuda_available=True, total_vram_mb=None),
        HardwareProfile(cuda_available=False, total_vram_mb=None),
    ]

    def test_tiny_is_never_auto_selected(self) -> None:
        resolver = HardwareTierResolver()
        for profile in self.PROFILES:
            assert resolver.resolve(profile).model != "tiny"

    def test_smallest_auto_model_is_base(self) -> None:
        resolver = HardwareTierResolver()
        allowed = {"base", "small", "large-v3-turbo"}
        for profile in self.PROFILES:
            assert resolver.resolve(profile).model in allowed

    def test_models_stay_multilingual(self) -> None:
        # No `.en` English-only variants are ever auto-selected.
        resolver = HardwareTierResolver()
        for profile in self.PROFILES:
            assert not resolver.resolve(profile).model.endswith(".en")
