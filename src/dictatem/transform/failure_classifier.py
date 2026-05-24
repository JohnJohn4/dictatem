"""Pure classifier mapping a Transform failure to an actionable message.

Given the structured ``OllamaFailure`` the backend hit plus the configured
model tag and base URL, this returns exactly one ``FailureReason`` and a
user-facing message to surface on the existing error path (overlay flash /
tray notification).

This module is PURE: it imports nothing OS-specific, performs no I/O, and
makes no network calls — every branch is trivially unit-testable.

We classify on the **network response**, not on whether an ``ollama`` binary
is on PATH. A local-binary probe cannot see an Ollama running in WSL, a
container, or on another host reachable via ``base_url`` — so "no binary on
PATH" is not evidence that Ollama is uninstalled, and must never override a
"connection refused". An unreachable server is therefore reported as
NOT_RUNNING with an install hint, rather than a false "not installed". See
ADR-0008.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictatem.transform.failure import OllamaFailure

from dictatem.transform.failure import FailureKind


class FailureReason(Enum):
    """The diagnosed cause of a Transform failure."""

    NOT_RUNNING = auto()
    """The server is unreachable at ``base_url`` (down, not installed, or the
    URL points nowhere). The message covers starting and installing it."""

    MODEL_MISSING = auto()
    """Server reachable but the configured model is not pulled (HTTP 404)."""

    UNKNOWN = auto()
    """Any other failure (5xx, timeout, malformed response, etc.)."""


def classify_transform_failure(
    *,
    failure: OllamaFailure,
    model_name: str,
    base_url: str,
) -> tuple[FailureReason, str]:
    """Diagnose *failure* into a ``(reason, message)`` pair.

    ``failure`` is the structured signal from the backend; ``model_name`` is
    the configured Ollama model tag (named verbatim in the ``MODEL_MISSING``
    message so the user can copy the ``ollama pull`` command); ``base_url`` is
    the configured Ollama endpoint, named in the ``NOT_RUNNING`` message so a
    remote/WSL user understands *where* Dictatem looked.
    """
    if failure.kind is FailureKind.HTTP_STATUS and failure.status_code == 404:
        return (
            FailureReason.MODEL_MISSING,
            f"The model '{model_name}' isn't available in Ollama. "
            f"Run `ollama pull {model_name}`, then try again.",
        )

    if failure.kind in (FailureKind.CONNECTION_REFUSED, FailureKind.URL_ERROR):
        return (
            FailureReason.NOT_RUNNING,
            f"Ollama isn't reachable at {base_url}. Make sure Ollama is "
            "running — see the README to install it if you haven't.",
        )

    return (
        FailureReason.UNKNOWN,
        "The Trigger Word transform failed; check the log for details.",
    )
