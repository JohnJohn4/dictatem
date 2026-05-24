"""Unit tests for the pure Transform-failure classifier.

The classifier maps a structured failure signal — whether the ``ollama``
binary is on PATH plus the kind of failure the backend hit — onto exactly
one actionable reason + user-facing message. It is pure: no network, no
filesystem, no Qt/win32. The single OS touch (probing PATH) is injected as
a plain ``bool``.

See ``CONTEXT.md#transform`` and ADR-0008.
"""

from __future__ import annotations

from dictatem.transform.failure import OllamaFailure
from dictatem.transform.failure_classifier import (
    FailureReason,
    classify_transform_failure,
)


class TestNotInstalled:
    def test_binary_absent_is_not_installed_regardless_of_failure_kind(self) -> None:
        reason, _msg = classify_transform_failure(
            binary_present=False,
            failure=OllamaFailure.connection_refused(),
            model_name="gemma4:e4b",
        )
        assert reason is FailureReason.NOT_INSTALLED

    def test_not_installed_message_points_to_readme_setup(self) -> None:
        _reason, msg = classify_transform_failure(
            binary_present=False,
            failure=OllamaFailure.connection_refused(),
            model_name="gemma4:e4b",
        )
        assert "README" in msg

    def test_binary_absent_wins_even_when_http_404(self) -> None:
        # If the binary isn't on PATH we can't have legitimately reached a
        # server; absence dominates whatever HTTP-shaped signal arrived.
        reason, _msg = classify_transform_failure(
            binary_present=False,
            failure=OllamaFailure.http_status(404),
            model_name="gemma4:e4b",
        )
        assert reason is FailureReason.NOT_INSTALLED


class TestNotRunning:
    def test_connection_refused_with_binary_present_is_not_running(self) -> None:
        reason, _msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.connection_refused(),
            model_name="gemma4:e4b",
        )
        assert reason is FailureReason.NOT_RUNNING

    def test_not_running_message_tells_user_to_start_ollama(self) -> None:
        _reason, msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.connection_refused(),
            model_name="gemma4:e4b",
        )
        lowered = msg.lower()
        assert "start" in lowered
        assert "ollama" in lowered

    def test_url_error_with_binary_present_is_not_running(self) -> None:
        reason, _msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.url_error("Name or service not known"),
            model_name="gemma4:e4b",
        )
        assert reason is FailureReason.NOT_RUNNING


class TestModelMissing:
    def test_http_404_with_binary_present_is_model_missing(self) -> None:
        reason, _msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.http_status(404),
            model_name="gemma4:e4b",
        )
        assert reason is FailureReason.MODEL_MISSING

    def test_model_missing_message_names_model_and_pull_command(self) -> None:
        _reason, msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.http_status(404),
            model_name="gemma4:e4b",
        )
        assert "gemma4:e4b" in msg
        assert "ollama pull gemma4:e4b" in msg

    def test_model_missing_names_whatever_model_is_configured(self) -> None:
        _reason, msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.http_status(404),
            model_name="llama3.2:1b",
        )
        assert "ollama pull llama3.2:1b" in msg


class TestUnknown:
    def test_http_500_is_unknown(self) -> None:
        reason, _msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.http_status(500),
            model_name="gemma4:e4b",
        )
        assert reason is FailureReason.UNKNOWN

    def test_timeout_is_unknown(self) -> None:
        reason, _msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.timeout(),
            model_name="gemma4:e4b",
        )
        assert reason is FailureReason.UNKNOWN

    def test_malformed_response_is_unknown(self) -> None:
        reason, _msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.malformed(),
            model_name="gemma4:e4b",
        )
        assert reason is FailureReason.UNKNOWN

    def test_unknown_message_is_non_empty(self) -> None:
        _reason, msg = classify_transform_failure(
            binary_present=True,
            failure=OllamaFailure.http_status(500),
            model_name="gemma4:e4b",
        )
        assert msg.strip() != ""
