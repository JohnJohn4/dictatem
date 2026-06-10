"""Unit tests for the pure Transform-failure classifier.

The classifier maps a structured failure signal onto exactly one actionable
reason + user-facing message. It is pure: no network, no filesystem, no
Qt/win32. It classifies on the network response, never on whether an
``ollama`` binary is on PATH (which can't see WSL/remote Ollama).

See ``CONTEXT.md#transform`` and ADR-0008.
"""

from __future__ import annotations

from dictatem.transform.failure import OllamaFailure
from dictatem.transform.failure_classifier import (
    FailureReason,
    classify_transform_failure,
)

_BASE_URL = "http://localhost:11434"


class TestNotRunning:
    def test_connection_refused_is_not_running(self) -> None:
        reason, _msg = classify_transform_failure(
            failure=OllamaFailure.connection_refused(),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert reason is FailureReason.NOT_RUNNING

    def test_url_error_is_not_running(self) -> None:
        reason, _msg = classify_transform_failure(
            failure=OllamaFailure.url_error("Name or service not known"),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert reason is FailureReason.NOT_RUNNING

    def test_not_running_message_mentions_running_and_ollama(self) -> None:
        _reason, msg = classify_transform_failure(
            failure=OllamaFailure.connection_refused(),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        lowered = msg.lower()
        assert "running" in lowered
        assert "ollama" in lowered

    def test_not_running_message_names_base_url(self) -> None:
        # A WSL/remote user needs to see *where* Dictatem looked.
        _reason, msg = classify_transform_failure(
            failure=OllamaFailure.connection_refused(),
            model_name="gemma4:e4b",
            base_url="http://192.168.1.50:11434",
        )
        assert "http://192.168.1.50:11434" in msg

    def test_not_running_message_keeps_install_hint(self) -> None:
        # Fresh users (no Ollama at all) still get pointed to setup, since an
        # unreachable server can't be distinguished from a missing install.
        _reason, msg = classify_transform_failure(
            failure=OllamaFailure.connection_refused(),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert "README" in msg


class TestModelMissing:
    def test_http_404_is_model_missing(self) -> None:
        reason, _msg = classify_transform_failure(
            failure=OllamaFailure.http_status(404),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert reason is FailureReason.MODEL_MISSING

    def test_model_missing_message_names_model_and_pull_command(self) -> None:
        _reason, msg = classify_transform_failure(
            failure=OllamaFailure.http_status(404),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert "gemma4:e4b" in msg
        assert "ollama pull gemma4:e4b" in msg

    def test_model_missing_names_whatever_model_is_configured(self) -> None:
        _reason, msg = classify_transform_failure(
            failure=OllamaFailure.http_status(404),
            model_name="llama3.2:1b",
            base_url=_BASE_URL,
        )
        assert "ollama pull llama3.2:1b" in msg


class TestServerError:
    def test_http_500_is_server_error(self) -> None:
        # A crashed llama-server answers 500 (e.g. the multi-GPU AMD/Vulkan
        # path). This is distinct from a missing model (404) — the model is
        # fine, the server died — so it gets its own actionable reason.
        reason, _msg = classify_transform_failure(
            failure=OllamaFailure.http_status(500),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert reason is FailureReason.SERVER_ERROR

    def test_server_error_message_names_the_status(self) -> None:
        _reason, msg = classify_transform_failure(
            failure=OllamaFailure.http_status(500),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert "500" in msg

    def test_server_error_message_points_to_readme(self) -> None:
        # The actionable fix (multi-GPU env-var workaround) lives in the README
        # troubleshooting section — the message must send the user there.
        _reason, msg = classify_transform_failure(
            failure=OllamaFailure.http_status(500),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert "README" in msg

    def test_other_5xx_stays_unknown(self) -> None:
        # Only 500 (the llama-server crash signature) gets the dedicated
        # branch; a 503 from a proxy is still the generic unknown path.
        reason, _msg = classify_transform_failure(
            failure=OllamaFailure.http_status(503),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert reason is FailureReason.UNKNOWN


class TestUnknown:
    def test_timeout_is_unknown(self) -> None:
        reason, _msg = classify_transform_failure(
            failure=OllamaFailure.timeout(),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert reason is FailureReason.UNKNOWN

    def test_malformed_response_is_unknown(self) -> None:
        reason, _msg = classify_transform_failure(
            failure=OllamaFailure.malformed(),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert reason is FailureReason.UNKNOWN

    def test_unknown_message_is_non_empty(self) -> None:
        _reason, msg = classify_transform_failure(
            failure=OllamaFailure.timeout(),
            model_name="gemma4:e4b",
            base_url=_BASE_URL,
        )
        assert msg.strip() != ""
