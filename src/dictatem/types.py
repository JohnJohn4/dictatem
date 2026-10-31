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
    # An Apple-Silicon Mac (arm64): no CUDA, but its CPU runs a larger Whisper
    # model fast enough for push-to-talk, so it gets its own tier.
    apple_silicon: bool = False


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


@dataclass(frozen=True)
class SegmentConfidence:
    """How sure the model was about a transcript, aggregated over its segments.

    ``avg_logprob`` is the duration-weighted mean of the segments'
    ``avg_logprob``; ``no_speech_prob`` is the worst (max) segment
    ``no_speech_prob``. Used only as a guardrail on Trigger Word recognition,
    never on dictated text (#226).
    """

    avg_logprob: float
    no_speech_prob: float


@dataclass(frozen=True)
class Transcript:
    """A transcription backend's result: the text plus what it knows about it.

    ``confidence`` and ``speech_duration_s`` (post-VAD speech, in seconds) are
    ``None`` when the backend can't report them (#246). Everything downstream of
    the Trigger Word decision receives only ``text``.
    """

    text: str
    confidence: SegmentConfidence | None = None
    speech_duration_s: float | None = None


TranscriptionResult = Transcript | EmptyResult
