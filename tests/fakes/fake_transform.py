"""Fake transform backend for testing lifecycle and daemon trigger fire logic."""

from __future__ import annotations


class FakeTransformBackend:
    def __init__(self, result: str = "fake transform output") -> None:
        self._default_result = result
        self.calls: list[tuple[str, str]] = []
        self._results: list[str] = []
        self._errors: list[Exception] = []
        self.warm_calls: int = 0
        self.availability_checks: int = 0
        self._warm_result: bool = True
        self._available: bool = True

    def transform(self, text: str, system_prompt: str) -> str:
        self.calls.append((text, system_prompt))
        if self._errors:
            raise self._errors.pop(0)
        if self._results:
            return self._results.pop(0)
        return self._default_result

    def warm(self) -> bool:
        self.warm_calls += 1
        return self._warm_result

    def is_model_available(self) -> bool:
        self.availability_checks += 1
        return self._available

    # --- Test helpers ---

    def set_warm_result(self, ok: bool) -> None:
        """Control what warm() returns on the next call."""
        self._warm_result = ok

    def set_available(self, available: bool) -> None:
        """Control what is_model_available() returns on the next call."""
        self._available = available

    def queue_result(self, result: str) -> None:
        """Queue a result to return on the next transform() call."""
        self._results.append(result)

    def queue_error(self, error: Exception) -> None:
        """Queue an exception to raise on the next transform() call."""
        self._errors.append(error)
