"""HTTP-layer tests for OllamaBackend, driven by a stdlib http.server fixture."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from dictatem.exceptions import TransformFailedError
from dictatem.transform.failure import FailureKind
from dictatem.transform.ollama_backend import OllamaBackend

ServerBehaviour = Callable[[BaseHTTPRequestHandler, bytes], None]


def _make_handler(behaviour: ServerBehaviour, captured: list[dict[str, Any]]):
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            try:
                captured.append(json.loads(body.decode("utf-8")))
            except json.JSONDecodeError:
                captured.append({"_raw": body.decode("utf-8", "replace")})
            behaviour(self, body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Silence stderr spam during tests.
            return

    return _Handler


@pytest.fixture
def server() -> Iterator[tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]]]:
    captured: list[dict[str, Any]] = []
    state: dict[str, ServerBehaviour] = {}

    def default_behaviour(handler: BaseHTTPRequestHandler, body: bytes) -> None:
        payload = json.dumps({"response": "ok"}).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    state["behaviour"] = default_behaviour

    def dispatcher(handler: BaseHTTPRequestHandler, body: bytes) -> None:
        state["behaviour"](handler, body)

    httpd = HTTPServer(("127.0.0.1", 0), _make_handler(dispatcher, captured))
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", captured, state
    finally:
        httpd.shutdown()
        thread.join(timeout=2.0)


def _set(state: dict[str, ServerBehaviour], behaviour: ServerBehaviour) -> None:
    state["behaviour"] = behaviour


class TestRequestShape:
    def test_posts_to_generate_endpoint_with_expected_fields(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, captured, _state = server
        backend = OllamaBackend(model_name="gemma4:e4b", base_url=url, timeout_s=5.0)

        out = backend.transform("hello", "do the thing")

        assert out == "ok"
        assert len(captured) == 1
        payload = captured[0]
        assert payload["model"] == "gemma4:e4b"
        assert payload["prompt"] == "hello"
        assert payload["system"] == "do the thing"
        assert payload["stream"] is False
        assert payload["options"]["temperature"] == pytest.approx(0.2)

    def test_strips_trailing_slash_from_base_url(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, _state = server
        backend = OllamaBackend(
            model_name="m", base_url=url + "/", timeout_s=5.0
        )
        assert backend.transform("x", "y") == "ok"


class TestHappyPath:
    def test_returns_response_field(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            payload = json.dumps({"response": "condensed text"}).encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=5.0)
        assert backend.transform("hello", "sys") == "condensed text"


class TestFailureModes:
    def test_malformed_json_raises(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", "5")
            handler.end_headers()
            handler.wfile.write(b"{not}")

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=5.0)
        with pytest.raises(TransformFailedError, match="valid JSON"):
            backend.transform("x", "y")

    def test_missing_response_field_raises(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            payload = json.dumps({"other": "field"}).encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=5.0)
        with pytest.raises(TransformFailedError, match="'response' field"):
            backend.transform("x", "y")

    def test_500_raises(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            handler.send_response(500)
            handler.send_header("Content-Length", "0")
            handler.end_headers()

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=5.0)
        with pytest.raises(TransformFailedError, match="HTTP 500"):
            backend.transform("x", "y")

    def test_connection_refused_raises(self) -> None:
        # Bind/release a port to find one that's definitely free.
        httpd = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        port = httpd.server_address[1]
        httpd.server_close()

        backend = OllamaBackend(
            model_name="m",
            base_url=f"http://127.0.0.1:{port}",
            timeout_s=2.0,
        )
        with pytest.raises(TransformFailedError, match="unreachable"):
            backend.transform("x", "y")

    def test_timeout_raises(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(_handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            # Sleep past the client's timeout. We never write a response, so
            # urlopen() raises socket.timeout / URLError.
            time.sleep(0.5)

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=0.1)
        with pytest.raises(TransformFailedError):
            backend.transform("x", "y")


class TestStructuredFailureSignal:
    """The raised TransformFailedError carries an OllamaFailure so the pure
    classifier can distinguish cases downstream (see #37)."""

    def test_http_404_carries_http_status_kind_and_code(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            handler.send_response(404)
            handler.send_header("Content-Length", "0")
            handler.end_headers()

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=5.0)
        with pytest.raises(TransformFailedError) as exc_info:
            backend.transform("x", "y")
        failure = exc_info.value.failure
        assert failure.kind is FailureKind.HTTP_STATUS
        assert failure.status_code == 404

    def test_500_carries_http_status_kind_and_code(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            handler.send_response(500)
            handler.send_header("Content-Length", "0")
            handler.end_headers()

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=5.0)
        with pytest.raises(TransformFailedError) as exc_info:
            backend.transform("x", "y")
        failure = exc_info.value.failure
        assert failure.kind is FailureKind.HTTP_STATUS
        assert failure.status_code == 500

    def test_connection_refused_carries_connection_refused_kind(
        self, mocker: Any
    ) -> None:
        # A genuine connection-refused depends on the host's TCP stack
        # sending RST for a closed port; some sandboxes silently drop the
        # SYN and the client times out instead. Drive the exact transport
        # error the backend must map so the assertion is deterministic.
        mocker.patch(
            "dictatem.transform.ollama_backend.urllib.request.urlopen",
            side_effect=urllib.error.URLError(ConnectionRefusedError()),
        )
        backend = OllamaBackend(
            model_name="m",
            base_url="http://127.0.0.1:1",
            timeout_s=2.0,
        )
        with pytest.raises(TransformFailedError) as exc_info:
            backend.transform("x", "y")
        assert exc_info.value.failure.kind is FailureKind.CONNECTION_REFUSED

    def test_generic_url_error_carries_url_error_kind(self, mocker: Any) -> None:
        mocker.patch(
            "dictatem.transform.ollama_backend.urllib.request.urlopen",
            side_effect=urllib.error.URLError("Name or service not known"),
        )
        backend = OllamaBackend(
            model_name="m",
            base_url="http://nope.invalid",
            timeout_s=2.0,
        )
        with pytest.raises(TransformFailedError) as exc_info:
            backend.transform("x", "y")
        assert exc_info.value.failure.kind is FailureKind.URL_ERROR

    def test_malformed_json_carries_malformed_kind(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            handler.send_response(200)
            handler.send_header("Content-Length", "5")
            handler.end_headers()
            handler.wfile.write(b"{not}")

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=5.0)
        with pytest.raises(TransformFailedError) as exc_info:
            backend.transform("x", "y")
        assert exc_info.value.failure.kind is FailureKind.MALFORMED

    def test_timeout_carries_timeout_kind(
        self,
        server: tuple[str, list[dict[str, Any]], dict[str, ServerBehaviour]],
    ) -> None:
        url, _captured, state = server

        def behaviour(_handler: BaseHTTPRequestHandler, _body: bytes) -> None:
            time.sleep(0.5)

        _set(state, behaviour)

        backend = OllamaBackend(model_name="m", base_url=url, timeout_s=0.1)
        with pytest.raises(TransformFailedError) as exc_info:
            backend.transform("x", "y")
        assert exc_info.value.failure.kind is FailureKind.TIMEOUT
