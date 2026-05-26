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
CPU           no CUDA                base             cpu      int8
============  =====================  ===============  =======  ==============

``base`` is the smallest auto-selected model; ``tiny`` is never auto-selected.
Models stay multilingual (no ``.en`` suffix). The capable tier ships the
``gemma4:e4b`` Transform tag; weaker tiers use the smaller ``gemma4:e2b`` tag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dictatem.types import ResolvedHardware

if TYPE_CHECKING:
    from dictatem.types import HardwareProfile

# VRAM thresholds in MB. Tunable, not contractual (see issue #36 / ADR-0007).
VRAM_HIGH_MB = 6 * 1024  # >= this -> GPU-high
VRAM_MID_MB = 3 * 1024  # >= this (and < HIGH) -> GPU-mid

# Transform (Ollama) tags by capability. The capable tag is `gemma4:e4b`
# (deliberately NOT "corrected" to gemma3:4b); weaker machines get a small tag.
_TRANSFORM_CAPABLE = "gemma4:e4b"
_TRANSFORM_SMALL = "gemma4:e2b"

# Resolved settings keyed by tier name. The resolver's only job is to pick a
# key; this keeps the GPU-mid and GPU-unknown rows identical-by-construction.
_TIER_TABLE: dict[str, ResolvedHardware] = {
    "GPU-high": ResolvedHardware(
        tier="GPU-high",
        model="large-v3-turbo",
        device="cuda",
        compute_type="float16",
        transform_model=_TRANSFORM_CAPABLE,
    ),
    "GPU-mid": ResolvedHardware(
        tier="GPU-mid",
        model="small",
        device="cuda",
        compute_type="int8_float16",
        transform_model=_TRANSFORM_SMALL,
    ),
    "GPU-low": ResolvedHardware(
        tier="GPU-low",
        model="base",
        device="cuda",
        compute_type="int8_float16",
        transform_model=_TRANSFORM_SMALL,
    ),
    "GPU-unknown": ResolvedHardware(
        tier="GPU-unknown",
        model="small",
        device="cuda",
        compute_type="int8_float16",
        transform_model=_TRANSFORM_SMALL,
    ),
    "CPU": ResolvedHardware(
        tier="CPU",
        model="base",
        device="cpu",
        compute_type="int8",
        transform_model=_TRANSFORM_SMALL,
    ),
}


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
    ) -> tuple[ResolvedHardware, bool]:
        """Reconcile a config's pinned transcription values against *profile*.

        Guards the absent-GPU crash (see ADR-0009): faster-whisper raises at
        model load if asked for ``cuda`` on a machine with no CUDA. When the
        config pins ``cuda`` but ``profile`` reports no CUDA, fall back to the
        whole CPU tier (``base``/``cpu``/``int8``) for THIS session — flipping
        only the device would leave a cuda compute_type (``float16`` /
        ``int8_float16``) that also won't run on CPU. Returns
        ``(resolved, did_fall_back=True)``.

        Otherwise the pinned values are authoritative (ADR-0007): they are
        returned unchanged as a ``"configured"`` ResolvedHardware with
        ``did_fall_back=False``. This deliberately does NOT re-tier on VRAM —
        only the crash is guarded, never a silent downgrade of a present GPU.
        Pure: no I/O, no native imports; the config object/file is never
        mutated.

        Scope is the transcription hardware only. The returned CPU-tier
        ``transform_model`` in the fallback case must NOT be applied — the
        Transform/Ollama model is independent of CUDA (see ADR-0009).
        """
        if device == "cuda" and not profile.cuda_available:
            return _TIER_TABLE["CPU"], True
        return (
            ResolvedHardware(
                tier="configured",
                model=model,
                device=device,
                compute_type=compute_type,
                transform_model="",
            ),
            False,
        )

    @staticmethod
    def _classify(profile: HardwareProfile) -> str:
        """Return the tier name for *profile*. Pure, total over all profiles."""
        if not profile.cuda_available:
            return "CPU"
        vram = profile.total_vram_mb
        if vram is None:
            # CUDA present but VRAM unreadable: assume a modest card.
            return "GPU-unknown"
        if vram >= VRAM_HIGH_MB:
            return "GPU-high"
        if vram >= VRAM_MID_MB:
            return "GPU-mid"
        return "GPU-low"
