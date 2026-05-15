"""Dictatem-specific exception types."""


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
    """Raised when the transcription model fails to load (corrupt download, missing CUDA libs, etc.)."""


class TransformFailedError(Exception):
    """Raised when a Transform call fails (Ollama unreachable, timeout, non-200, bad JSON)."""
