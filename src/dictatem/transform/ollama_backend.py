"""OllamaBackend — TransformBackend implemented via stdlib urllib.

POSTs JSON to ``<base_url>/api/generate`` with ``stream: false`` and
maps every failure mode (connection refused, timeout, non-200,
malformed JSON, missing ``response`` field) to ``TransformFailedError``.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from dictatem.exceptions import TransformFailedError

logger = logging.getLogger(__name__)


class OllamaBackend:
    def __init__(
        self,
        *,
        model_name: str,
        base_url: str,
        timeout_s: float,
    ) -> None:
        self._model_name = model_name
        # Tolerate trailing slash in the configured URL.
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def transform(self, text: str, system_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self._model_name,
            "prompt": text,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        body = json.dumps(payload).encode("utf-8")
        url = f"{self._base_url}/api/generate"
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                status = resp.status
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            logger.warning("Ollama HTTP %d at %s: %s", exc.code, url, exc)
            raise TransformFailedError(
                f"Ollama returned HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            # ConnectionRefusedError, socket.timeout, DNS failures, etc.
            logger.warning("Ollama unreachable at %s: %s", url, exc)
            raise TransformFailedError(
                f"Ollama unreachable at {url}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            logger.warning("Ollama timed out after %.1fs", self._timeout_s)
            raise TransformFailedError(
                f"Ollama timed out after {self._timeout_s}s"
            ) from exc

        if status != 200:
            raise TransformFailedError(f"Ollama returned HTTP {status}")

        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TransformFailedError(
                "Ollama response was not valid JSON"
            ) from exc

        if not isinstance(data, dict) or "response" not in data:
            raise TransformFailedError(
                "Ollama response missing 'response' field"
            )
        result = data["response"]
        if not isinstance(result, str):
            raise TransformFailedError(
                "Ollama 'response' field was not a string"
            )
        return result
