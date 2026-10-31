"""Dictatem-specific exception types."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictatem.transcribe.load_failure import ModelLoadDiagnosis
    from dictatem.transform.failure import OllamaFailure


class PlatformNotSupportedError(Exception):
    """Raised when Dictatem is run on an unsupported platform."""


class ClipboardContentionError(Exception):
    """Raised when the clipboard cannot be opened after all retry attempts."""


class AudioCaptureError(Exception):
    """Raised when audio capture fails (mic disconnected, permission denied, etc.)."""


class GPUOutOfMemoryError(Exception):
    """Raised when the GPU runs out of memory during transcription."""


class TranscriptionFailedError(Exception):
    """Raised when transcription fails after retries."""


class ModelLoadError(Exception):
    """Raised when the transcription model fails to load.

    Corrupt download, missing CUDA libs, etc. ``TranscribeLifecycle`` wraps
    every load exception in one, keeping the original as ``__cause__`` and
    attaching the pure classifier's ``diagnosis`` (reason + user-facing title
    and message, #241). ``diagnosis`` is ``None`` only when raised elsewhere
    (e.g. by a test fake).
    """

    def __init__(self, message: str, *, diagnosis: ModelLoadDiagnosis | None = None) -> None:
        super().__init__(message)
        self.diagnosis = diagnosis


class TransformFailedError(Exception):
    """Raised when a Transform call fails (Ollama unreachable, timeout, non-200, bad JSON).

    Carries an optional structured ``failure`` signal so the pure
    ``failure_classifier`` can distinguish not-installed / not-running /
    model-missing without re-probing anything. ``failure`` is ``None`` only
    for failures raised outside the Ollama backend (e.g. in tests).
    """

    def __init__(self, message: str, *, failure: OllamaFailure | None = None) -> None:
        super().__init__(message)
        self.failure = failure
