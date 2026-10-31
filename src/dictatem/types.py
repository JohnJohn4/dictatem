"""Shared types used across Dictatem modules."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

SAMPLE_RATE: int = 16000

AudioChunk = npt.NDArray[np.float32]

# The transcription devices Dictatem can run (``[model].device``): faster-whisper
# on ``cuda`` / ``cpu``, the Apple-GPU MLX engine on ``mlx`` (spec #224). A
# config may still hold any string; backend selection maps unknown ones to CPU.
Device = Literal["cuda", "cpu", "mlx"]


@dataclass(frozen=True)
class HardwareProfile:
    """What the machine looks like to Dictatem, as seen by a HardwareProbe.

    ``total_vram_mb`` is ``None`` when CUDA is present but VRAM could not be
    queried (no nvidia-ml-py, driver error, etc.); the resolver treats this
    "CUDA but VRAM unknown" case conservatively.
    """

    cuda_available: bool
    total_vram_mb: int | None
    # An Apple-Silicon Mac (arm64): no CUDA, but its CPU runs a larger Whisper
    # model fast enough for push-to-talk, so it gets its own tier.
    apple_silicon: bool = False
    # MLX is usable here: Apple Silicon, macOS 14+, and the mlx-whisper engine
    # installed (spec #224). Safe default False; the Mac probe populates it
    # (#233). Reconcile uses it to guard a config pinning device "mlx" (#231).
    mlx_available: bool = False
    # Total unified (system) memory in MB on a Mac, or None when unknown or not
    # a Mac. Splits the Apple-GPU tiers; unknown is treated conservatively.
    unified_memory_mb: int | None = None


@dataclass(frozen=True)
class ResolvedHardware:
    """Concrete values baked into the config on first run (see ADR-0007).

    Pairs the resolved transcription settings (whisper ``model``, ``device``,
    ``compute_type``) with the tier-appropriate Transform (Ollama) model tag,
    plus the human-readable ``tier`` name for transparent logging.
    """

    tier: str
    model: str
    device: str
    compute_type: str
    transform_model: str


class RecordingMode(enum.Enum):
    PTT = "ptt"
    TOGGLE = "toggle"


class EmptyResult:
    """Sentinel indicating a suppressed or empty transcription."""

    def __repr__(self) -> str:
        return "EmptyResult()"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EmptyResult)

    def __hash__(self) -> int:
        return hash("EmptyResult")


TranscriptionResult = str | EmptyResult
