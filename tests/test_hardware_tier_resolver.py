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
        assert resolved.transform_model == "gemma4:e2b"


class TestGpuMidTier:
    """CUDA present with 3-6 GB VRAM -> mid tier (small / int8_float16)."""

    def test_resolves_small_int8_float16(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=True, total_vram_mb=4096)
        resolved = resolver.resolve(profile)
        assert resolved.model == "small"
        assert resolved.device == "cuda"
        assert resolved.compute_type == "int8_float16"
        assert resolved.transform_model == "gemma4:e2b"


class TestGpuLowTier:
    """CUDA present with < 3 GB VRAM -> low tier (base / int8_float16)."""

    def test_resolves_base_int8_float16(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=True, total_vram_mb=2048)
        resolved = resolver.resolve(profile)
        assert resolved.model == "base"
        assert resolved.device == "cuda"
        assert resolved.compute_type == "int8_float16"
        assert resolved.transform_model == "gemma4:e2b"


class TestCpuTier:
    """No CUDA -> CPU tier; the app must still start and transcribe."""

    def test_resolves_base_cpu_int8(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=False, total_vram_mb=None)
        resolved = resolver.resolve(profile)
        assert resolved.model == "base"
        assert resolved.device == "cpu"
        assert resolved.compute_type == "int8"
        assert resolved.transform_model == "gemma4:e2b"

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


# Profiles reused by the reconcile tests below.
NO_CUDA_PROFILE = HardwareProfile(cuda_available=False, total_vram_mb=None)
CUDA_PROFILE = HardwareProfile(cuda_available=True, total_vram_mb=8192)


class TestReconcileFallsBackWhenGpuAbsent:
    """A cuda-pinned config on a CPU-only machine falls back for the session.

    faster-whisper raises at model load if asked for cuda on a machine with no
    CUDA, so reconcile adopts the WHOLE CPU row (base/cpu/int8) — flipping just
    the device would leave a float16 compute_type that also can't run on CPU.
    The config file is never touched (see ADR-0009). #39
    """

    def test_cuda_config_no_cuda_profile_falls_back_to_cpu_tier(self) -> None:
        resolver = HardwareTierResolver()
        resolved, did_fall_back = resolver.reconcile(
            device="cuda",
            model="large-v3-turbo",
            compute_type="float16",
            profile=NO_CUDA_PROFILE,
        )
        assert did_fall_back is True
        assert resolved.tier == "CPU"
        assert resolved.model == "base"
        assert resolved.device == "cpu"
        assert resolved.compute_type == "int8"


class TestReconcileKeepsPinnedValuesWhenHardwarePresent:
    """A config whose requested hardware is present is returned unchanged."""

    def test_cuda_config_cuda_profile_returns_unchanged(self) -> None:
        resolver = HardwareTierResolver()
        resolved, did_fall_back = resolver.reconcile(
            device="cuda",
            model="large-v3-turbo",
            compute_type="float16",
            profile=CUDA_PROFILE,
        )
        assert did_fall_back is False
        assert resolved.model == "large-v3-turbo"
        assert resolved.device == "cuda"
        assert resolved.compute_type == "float16"


class TestReconcileNeverTouchesCpuConfig:
    """A cpu-pinned config never falls back — there is no GPU to lose."""

    def test_cpu_config_no_cuda_profile_unchanged(self) -> None:
        resolver = HardwareTierResolver()
        resolved, did_fall_back = resolver.reconcile(
            device="cpu",
            model="base",
            compute_type="int8",
            profile=NO_CUDA_PROFILE,
        )
        assert did_fall_back is False
        assert resolved.device == "cpu"
        assert resolved.model == "base"
        assert resolved.compute_type == "int8"

    def test_cpu_config_cuda_profile_not_upgraded(self) -> None:
        # We never upgrade a cpu config to cuda just because a GPU is present;
        # the user's pinned config is authoritative (ADR-0007).
        resolver = HardwareTierResolver()
        resolved, did_fall_back = resolver.reconcile(
            device="cpu",
            model="base",
            compute_type="int8",
            profile=CUDA_PROFILE,
        )
        assert did_fall_back is False
        assert resolved.device == "cpu"


class TestReconcileIsPure:
    """reconcile makes no I/O and mutates neither inputs nor the resolver."""

    def test_inputs_and_profile_not_mutated(self) -> None:
        resolver = HardwareTierResolver()
        profile = HardwareProfile(cuda_available=False, total_vram_mb=None)
        resolver.reconcile(
            device="cuda",
            model="large-v3-turbo",
            compute_type="float16",
            profile=profile,
        )
        # HardwareProfile is frozen; assert its fields are intact regardless.
        assert profile.cuda_available is False
        assert profile.total_vram_mb is None

    def test_does_not_share_the_cpu_tier_table_entry(self) -> None:
        # Returning the table entry by reference is fine because ResolvedHardware
        # is frozen, but the CPU tier row itself must be unchanged for the next
        # caller (resolve() relies on it).
        resolver = HardwareTierResolver()
        resolved, _ = resolver.reconcile(
            device="cuda",
            model="large-v3-turbo",
            compute_type="float16",
            profile=NO_CUDA_PROFILE,
        )
        baseline = resolver.resolve(NO_CUDA_PROFILE)
        assert resolved == baseline
