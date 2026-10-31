"""HardwareTierResolver — pure, table-driven Hardware Tier selection (#36).

Maps a :class:`~dictatem.types.HardwareProfile` to a concrete
:class:`~dictatem.types.ResolvedHardware`. No I/O, no native imports — every
input arrives via the profile, so the full tier table is unit-testable on any
OS. See ADR-0007 for why this runs once on first run and the result is baked
into the config.

Tier table (VRAM thresholds in MB, tunable — see ADR-0007):

============  =====================  ===============  =======  ==============
Tier          Detected               Whisper model    device   compute_type
============  =====================  ===============  =======  ==============
GPU-high      CUDA, >= 6 GB          large-v3-turbo   cuda     float16
GPU-mid       CUDA, 3-6 GB           small            cuda     int8_float16
GPU-low       CUDA, < 3 GB           base             cuda     int8_float16
GPU-unknown   CUDA, VRAM unknown     small            cuda     int8_float16
Apple-GPU     MLX, >= 12 GB          large-v3-turbo   mlx      float16
Apple-GPU-low MLX, < 12 GB/unknown   small            mlx      float16
Apple-Silicon arm64 Mac, no MLX      small            cpu      int8
CPU           no CUDA                base             cpu      int8
============  =====================  ===============  =======  ==============

"MLX usable" means Apple Silicon, macOS 14+ and the mlx-whisper engine
installed (spec #224, ADR-0013 amendment). The 12 GB unified-memory split keeps
``large-v3-turbo`` (~1.6 GB) off 8 GB Macs, where it would compete with the
Transform model; unknown memory gets the conservative ``Apple-GPU-low`` row.
Apple-Silicon CPUs without MLX run ``small`` int8 fast enough for push-to-talk,
a clear accuracy step up from ``base``.

``base`` is the smallest auto-selected model; ``tiny`` is never auto-selected.
Models stay multilingual (no ``.en`` suffix). All tiers default to the small
``gemma4:e2b`` Transform tag: it runs on CPU-only laptops (a little slow but
fine) and co-resides with any Whisper tier on modest GPUs. Users with a capable
GPU can pin a larger tag (e.g. ``gemma4:e4b``) in config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from dictatem.types import ResolvedHardware

if TYPE_CHECKING:
    from dictatem.types import HardwareProfile

# VRAM thresholds in MB. Tunable, not contractual (see issue #36 / ADR-0007).
VRAM_HIGH_MB = 6 * 1024  # >= this -> GPU-high
VRAM_MID_MB = 3 * 1024  # >= this (and < HIGH) -> GPU-mid
# Unified-memory split for the MLX tiers in MB (#233). Tunable, not contractual.
UNIFIED_MEMORY_HIGH_MB = 12 * 1024  # >= this -> Apple-GPU, else Apple-GPU-low

# The default Transform (Ollama) tag for every tier. `gemma4:e2b` is small enough
# to run on CPU-only laptops and to co-reside with any Whisper tier on modest
# GPUs; users on a capable GPU can pin a larger tag (e.g. `gemma4:e4b`) in config.
# `gemma4:e2b` is deliberately NOT "corrected" to a standard gemma3 tag.
_TRANSFORM_MODEL = "gemma4:e2b"

# Resolved settings keyed by tier name. The resolver's only job is to pick a
# key; this keeps the GPU-mid and GPU-unknown rows identical-by-construction.
_TIER_TABLE: dict[str, ResolvedHardware] = {
    "GPU-high": ResolvedHardware(
        tier="GPU-high",
        model="large-v3-turbo",
        device="cuda",
        compute_type="float16",
        transform_model=_TRANSFORM_MODEL,
    ),
    "GPU-mid": ResolvedHardware(
        tier="GPU-mid",
        model="small",
        device="cuda",
        compute_type="int8_float16",
        transform_model=_TRANSFORM_MODEL,
    ),
    "GPU-low": ResolvedHardware(
        tier="GPU-low",
        model="base",
        device="cuda",
        compute_type="int8_float16",
        transform_model=_TRANSFORM_MODEL,
    ),
    "GPU-unknown": ResolvedHardware(
        tier="GPU-unknown",
        model="small",
        device="cuda",
        compute_type="int8_float16",
        transform_model=_TRANSFORM_MODEL,
    ),
    "Apple-GPU": ResolvedHardware(
        tier="Apple-GPU",
        model="large-v3-turbo",
        device="mlx",
        compute_type="float16",
        transform_model=_TRANSFORM_MODEL,
    ),
    "Apple-GPU-low": ResolvedHardware(
        tier="Apple-GPU-low",
        model="small",
        device="mlx",
        compute_type="float16",
        transform_model=_TRANSFORM_MODEL,
    ),
    "Apple-Silicon": ResolvedHardware(
        tier="Apple-Silicon",
        model="small",
        device="cpu",
        compute_type="int8",
        transform_model=_TRANSFORM_MODEL,
    ),
    "CPU": ResolvedHardware(
        tier="CPU",
        model="base",
        device="cpu",
        compute_type="int8",
        transform_model=_TRANSFORM_MODEL,
    ),
}


# Why a session fell back (#231): the configured device's hardware is absent.
# Machine-readable so the notification can name the cause.
FallbackReason = Literal["cuda-absent", "mlx-unavailable"]
# Why a running session switched engines (#232): the MLX engine failed to load
# or transcribe. Not a reconcile outcome, so it is kept out of FallbackReason.
RuntimeFallbackReason = Literal["mlx-load-failed"]


@dataclass(frozen=True)
class Reconciliation:
    """What :meth:`HardwareTierResolver.reconcile` decided for this session.

    ``fallback_reason`` is ``None`` when the configured values are used as-is.
    """

    resolved: ResolvedHardware
    fallback_reason: FallbackReason | None = None

    @property
    def did_fall_back(self) -> bool:
        return self.fallback_reason is not None


@dataclass(frozen=True)
class FallbackNotice:
    """Title and body of the one tray notification for a session fallback."""

    title: str
    body: str


_FALLBACK_BODIES: dict[FallbackReason | RuntimeFallbackReason, str] = {
    "cuda-absent": (
        "Configured GPU (cuda) isn't available — running on CPU this session. "
        "Your config is unchanged; restore the GPU to use it again."
    ),
    "mlx-unavailable": (
        "The Apple GPU engine (device = \"mlx\") isn't usable on this machine — "
        "running on CPU this session. Your config is unchanged; it needs an "
        "Apple-Silicon Mac on macOS 14+ with the apple-gpu engine installed "
        "(re-run the installer), or set [model].device back to \"cpu\"."
    ),
    "mlx-load-failed": (
        "The Apple GPU engine (MLX) failed to load — your dictation and the "
        "rest of this session run on CPU. Your config is unchanged; the next "
        "launch tries the GPU again. See the log for the cause."
    ),
}


def fallback_notice(reason: FallbackReason | RuntimeFallbackReason) -> FallbackNotice:
    """The tray notification naming why this session fell back to CPU. Pure."""
    return FallbackNotice(title="Running on CPU", body=_FALLBACK_BODIES[reason])


def tier_row(tier: str) -> ResolvedHardware:
    """Return the resolved row for the named *tier* (e.g. ``"CPU"``).

    Raises ``KeyError`` for an unknown tier name.
    """
    return _TIER_TABLE[tier]


class HardwareTierResolver:
    """Map a HardwareProfile to a ResolvedHardware (pure, no I/O)."""

    def resolve(self, profile: HardwareProfile) -> ResolvedHardware:
        """Return the resolved transcription + Transform settings for *profile*."""
        return _TIER_TABLE[self._classify(profile)]

    def reconcile(
        self,
        *,
        device: str,
        model: str,
        compute_type: str,
        profile: HardwareProfile,
    ) -> Reconciliation:
        """Reconcile a config's pinned transcription values against *profile*.

        Guards the absent-GPU crash (see ADR-0009): faster-whisper raises at
        model load if asked for ``cuda`` on a machine with no CUDA. When the
        config pins ``cuda`` but ``profile`` reports no CUDA, fall back to the
        whole CPU tier (``base``/``cpu``/``int8``) for THIS session — flipping
        only the device would leave a cuda compute_type (``float16`` /
        ``int8_float16``) that also won't run on CPU. The result carries
        ``fallback_reason="cuda-absent"``.

        Likewise a config pinning ``mlx`` on a profile without
        ``mlx_available`` (Intel, macOS < 14, the apple-gpu extra missing, a
        config copied to Windows) falls back to the whole ``Apple-Silicon`` CPU
        row on Apple Silicon, or the ``CPU`` row elsewhere, with
        ``fallback_reason="mlx-unavailable"`` (ADR-0013 amendment).

        Otherwise the pinned values are authoritative (ADR-0007): they are
        returned unchanged as a ``"configured"`` ResolvedHardware with no
        fallback reason. A ``cpu`` config is never upgraded to ``cuda`` or
        ``mlx``. This deliberately does NOT re-tier on VRAM —
        only the crash is guarded, never a silent downgrade of a present GPU.
        Pure: no I/O, no native imports; the config object/file is never
        mutated.

        Scope is the transcription hardware only. The returned CPU-tier
        ``transform_model`` in the fallback case must NOT be applied — the
        Transform/Ollama model is independent of CUDA (see ADR-0009).
        """
        if device == "cuda" and not profile.cuda_available:
            return Reconciliation(_TIER_TABLE["CPU"], "cuda-absent")
        if device == "mlx" and not profile.mlx_available:
            row = "Apple-Silicon" if profile.apple_silicon else "CPU"
            return Reconciliation(_TIER_TABLE[row], "mlx-unavailable")
        return Reconciliation(
            ResolvedHardware(
                tier="configured",
                model=model,
                device=device,
                compute_type=compute_type,
                transform_model="",
            )
        )

    @staticmethod
    def _classify(profile: HardwareProfile) -> str:
        """Return the tier name for *profile*. Pure, total over all profiles."""
        if not profile.cuda_available:
            if profile.mlx_available:
                memory = profile.unified_memory_mb
                if memory is not None and memory >= UNIFIED_MEMORY_HIGH_MB:
                    return "Apple-GPU"
                # Below the split, or unknown: the small model leaves headroom
                # for the Transform model sharing the same unified memory.
                return "Apple-GPU-low"
            return "Apple-Silicon" if profile.apple_silicon else "CPU"
        vram = profile.total_vram_mb
        if vram is None:
            # CUDA present but VRAM unreadable: assume a modest card.
            return "GPU-unknown"
        if vram >= VRAM_HIGH_MB:
            return "GPU-high"
        if vram >= VRAM_MID_MB:
            return "GPU-mid"
        return "GPU-low"
