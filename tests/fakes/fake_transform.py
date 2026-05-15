"""Fake transform backend for testing lifecycle and daemon trigger fire logic."""

from __future__ import annotations


class FakeTransformBackend:
    def __init__(self, result: str = "fake transform output") -> None:
        self._default_result = result
        self.calls: list[tuple[str, str]] = []
        self._results: list[str] = []
        self._errors: list[Exception] = []

    def transform(self, text: str, system_prompt: str) -> str:
        self.calls.append((text, system_prompt))
        if self._errors:
            raise self._errors.pop(0)
        if self._results:
            return self._results.pop(0)
        return self._default_result

    # --- Test helpers ---

    def queue_result(self, result: str) -> None:
        """Queue a result to return on the next transform() call."""
        self._results.append(result)

    def queue_error(self, error: Exception) -> None:
        """Queue an exception to raise on the next transform() call."""
        self._errors.append(error)
