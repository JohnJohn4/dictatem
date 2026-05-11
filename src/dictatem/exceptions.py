"""Dictatem-specific exception types."""


class PlatformNotSupportedError(Exception):
    """Raised when Dictatem is run on an unsupported platform."""


class ClipboardContentionError(Exception):
    """Raised when the clipboard cannot be opened after all retry attempts."""
