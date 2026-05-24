"""Shared types used across Dictatem modules."""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

SAMPLE_RATE: int = 16000

AudioChunk = npt.NDArray[np.float32]


@dataclass(frozen=True)
class HardwareProfile:
    """What the machine looks like to Dictatem, as seen by a HardwareProbe.

    ``total_vram_mb`` is ``None`` when CUDA is present but VRAM could not be
    queried (no nvidia-ml-py, driver error, etc.); the resolver treats this
    "CUDA but VRAM unknown" case conservatively.
    """

    cuda_available: bool
    total_vram_mb: int | None


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
