"""Dictatem-specific exception types."""


class PlatformNotSupportedError(Exception):
    """Raised when Dictatem is run on an unsupported platform."""


class AudioCaptureError(Exception):
    """Raised when audio capture fails (mic disconnected, permission denied, etc.)."""
