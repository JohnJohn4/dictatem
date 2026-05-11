"""Dictatem-specific exception types."""


class PlatformNotSupportedError(Exception):
    """Raised when Dictatem is run on an unsupported platform."""


class GPUOutOfMemoryError(Exception):
    """Raised when the GPU runs out of memory during transcription."""


class TranscriptionFailedError(Exception):
    """Raised when transcription fails after retries."""
