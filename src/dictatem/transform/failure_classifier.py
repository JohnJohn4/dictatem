"""Pure classifier mapping a Transform failure to an actionable message.

Given two structured signals — whether the ``ollama`` binary is on PATH and
the ``OllamaFailure`` the backend hit — this returns exactly one
``FailureReason`` plus a user-facing message to surface on the existing
error path (overlay flash / tray notification).

This module is PURE: it imports nothing OS-specific, performs no I/O, and
makes no network calls. The one OS touch the feature needs (probing PATH
for the ``ollama`` binary) is done by the caller and handed in as a plain
``bool``, so every branch here is trivially unit-testable with fakes.

Per ADR-0008, the messages tell the user what to do (install / start /
pull) but Dictatem never performs those actions on their behalf.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictatem.transform.failure import OllamaFailure

from dictatem.transform.failure import FailureKind


class FailureReason(Enum):
    """The diagnosed cause of a Transform failure."""

    NOT_INSTALLED = auto()
    """No ``ollama`` binary on PATH."""

    NOT_RUNNING = auto()
    """Binary present but the server is unreachable (start ``ollama serve``)."""

    MODEL_MISSING = auto()
    """Server reachable but the configured model is not pulled (HTTP 404)."""

    UNKNOWN = auto()
    """Any other failure (5xx, timeout, malformed response, etc.)."""


def classify_transform_failure(
    *,
    binary_present: bool,
    failure: OllamaFailure,
    model_name: str,
) -> tuple[FailureReason, str]:
    """Diagnose *failure* into a ``(reason, message)`` pair.

    ``binary_present`` is the result of probing PATH for ``ollama``;
    ``failure`` is the structured signal from the backend; ``model_name``
    is the configured Ollama model tag, named verbatim in the
    ``MODEL_MISSING`` message so the user can copy the ``ollama pull``
    command.
    """
    # Binary absence dominates: without the binary on PATH there is no
    # legitimate local server, so whatever transport- or HTTP-shaped signal
    # arrived is moot — the user simply hasn't installed Ollama.
    if not binary_present:
        return (
            FailureReason.NOT_INSTALLED,
            "Trigger Words need Ollama, which isn't installed. "
            "See the Ollama / Transform setup section of the README.",
        )

    if failure.kind in (FailureKind.CONNECTION_REFUSED, FailureKind.URL_ERROR):
        return (
            FailureReason.NOT_RUNNING,
            "Ollama isn't running. Start Ollama, then try again.",
        )

    if failure.kind is FailureKind.HTTP_STATUS and failure.status_code == 404:
        return (
            FailureReason.MODEL_MISSING,
            f"The model '{model_name}' isn't available in Ollama. "
            f"Run `ollama pull {model_name}`, then try again.",
        )

    return (
        FailureReason.UNKNOWN,
        "The Trigger Word transform failed; check the log for details.",
    )
