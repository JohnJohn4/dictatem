"""Tests for TransformLifecycle — thin pass-through over TransformBackend."""

from __future__ import annotations

import pytest

from dictatem.exceptions import TransformFailedError
from dictatem.transform.lifecycle import TransformLifecycle
from tests.fakes import FakeTransformBackend


class TestPassThrough:
    def test_returns_backend_result(self) -> None:
        backend = FakeTransformBackend(result="condensed")
        lc = TransformLifecycle(backend=backend)
        assert lc.transform("verbose text", "system prompt") == "condensed"

    def test_passes_arguments_through(self) -> None:
        backend = FakeTransformBackend()
        lc = TransformLifecycle(backend=backend)
        lc.transform("verbose text", "system prompt")
        assert backend.calls == [("verbose text", "system prompt")]

    def test_queued_results_consumed_in_order(self) -> None:
        backend = FakeTransformBackend()
        backend.queue_result("first")
        backend.queue_result("second")
        lc = TransformLifecycle(backend=backend)
        assert lc.transform("a", "sys") == "first"
        assert lc.transform("b", "sys") == "second"


class TestErrorPropagation:
    def test_transform_failed_error_propagates(self) -> None:
        backend = FakeTransformBackend()
        backend.queue_error(TransformFailedError("boom"))
        lc = TransformLifecycle(backend=backend)
        with pytest.raises(TransformFailedError, match="boom"):
            lc.transform("text", "sys")

    def test_unexpected_error_propagates(self) -> None:
        """Non-TransformFailedError exceptions are not swallowed."""
        backend = FakeTransformBackend()
        backend.queue_error(RuntimeError("kaboom"))
        lc = TransformLifecycle(backend=backend)
        with pytest.raises(RuntimeError, match="kaboom"):
            lc.transform("text", "sys")
