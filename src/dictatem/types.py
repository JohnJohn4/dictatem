"""Shared types used across Dictatem modules."""

from __future__ import annotations

import enum

import numpy as np
import numpy.typing as npt

SAMPLE_RATE: int = 16000

AudioChunk = npt.NDArray[np.float32]


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
