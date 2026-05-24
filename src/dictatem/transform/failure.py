"""Structured Transform-failure signal.

``OllamaBackend`` collapses every failure mode into a single
``TransformFailedError``, but the *kind* of failure determines what the
user should be told (start the server vs pull a model vs install Ollama).
``OllamaFailure`` is the small, OS-free value that carries enough signal
for the pure classifier (``failure_classifier``) to distinguish cases
without re-probing anything.

Kept deliberately tiny and immutable so it can be attached to the
exception, passed around freely, and asserted on in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class FailureKind(Enum):
    """How a Transform call failed, at the granularity the classifier needs."""

    CONNECTION_REFUSED = auto()
    """Could not open a connection to the server (ConnectionRefusedError)."""

    URL_ERROR = auto()
    """Other ``urllib`` transport error (DNS failure, reset, etc.)."""

    HTTP_STATUS = auto()
    """Server answered with a non-200 status (``http_status`` is set)."""

    TIMEOUT = auto()
    """The request exceeded the configured per-request timeout."""

    MALFORMED = auto()
    """A 200 response whose body was not the expected JSON shape."""


@dataclass(frozen=True)
class OllamaFailure:
    """An immutable description of how a single Transform call failed."""

    kind: FailureKind
    status_code: int | None = None
    """The HTTP status code, set only when ``kind`` is ``HTTP_STATUS``."""

    @classmethod
    def connection_refused(cls) -> OllamaFailure:
        return cls(kind=FailureKind.CONNECTION_REFUSED)

    @classmethod
    def url_error(cls, _reason: object = None) -> OllamaFailure:
        # The reason string is useful for logs but carries no signal the
        # classifier branches on, so it is intentionally not stored.
        return cls(kind=FailureKind.URL_ERROR)

    @classmethod
    def http_status(cls, status: int) -> OllamaFailure:
        return cls(kind=FailureKind.HTTP_STATUS, status_code=status)

    @classmethod
    def timeout(cls) -> OllamaFailure:
        return cls(kind=FailureKind.TIMEOUT)

    @classmethod
    def malformed(cls) -> OllamaFailure:
        return cls(kind=FailureKind.MALFORMED)
