"""Transcription contract suite — every ``TranscriberBackend`` must pass it (#229).

One parametrised suite asserts the ``TranscriberBackend`` contract through the
protocol alone (never by inspecting how an engine is called). It always runs
against :class:`~tests.fakes.FakeTranscriberBackend` in default CI.

Real engines run only on opt-in, never in default CI: they need the engine
installed, may download weights, and are slow. To run the real faster-whisper
backend (``tiny`` / ``cpu`` / ``int8``, about 75 MB fetched into the HF cache
on first run)::

    uv sync --extra runtime
    DICTATEM_REAL_ENGINES=1 uv run pytest tests/test_transcriber_contract.py -m real_engine

(PowerShell: ``$env:DICTATEM_REAL_ENGINES = "1"`` first.) Without the flag the
real-engine params are skipped.

The MLX backend (``tiny``, ~75 MB) runs the same way on an Apple-Silicon Mac
with the apple-gpu extra (``uv sync --extra apple-gpu``); elsewhere it skips.

The MLX session fallback composite (#232) runs around fakes in default CI, both
on the happy path (primary serves) and after a primary load failure (the
fallback serves for the session).

Adding a backend is one entry in
``BACKENDS``: a ``pytest.param`` whose value is a zero-argument factory
returning a fresh, unloaded backend. Mark real engines with ``_real_engine()``.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import TYPE_CHECKING

import numpy as np
import pytest

from dictatem.interfaces import TranscriberBackend
from dictatem.transcribe.fallback import FallbackTranscriber
from dictatem.types import EmptyResult
from tests.fakes import FakeTranscriberBackend

if TYPE_CHECKING:
    from collections.abc import Callable

REAL_ENGINES_ENV = "DICTATEM_REAL_ENGINES"

# One second of silence at 16 kHz — the shape every backend is fed.
AUDIO = np.zeros(16000, dtype=np.float32)


def _real_engine() -> list[pytest.MarkDecorator]:
    """Marks for a real-engine param: tagged, and skipped unless opted in."""
    return [
        pytest.mark.real_engine,
        pytest.mark.skipif(
            os.environ.get(REAL_ENGINES_ENV) != "1",
            reason=f"real engine: set {REAL_ENGINES_ENV}=1 to run",
        ),
    ]


def _faster_whisper_tiny() -> TranscriberBackend:
    from dictatem.transcribe.faster_whisper_backend import FasterWhisperBackend

    return FasterWhisperBackend(model_name="tiny", device="cpu", compute_type="int8")


def _mlx_tiny() -> TranscriberBackend:
    from dictatem.transcribe.mlx_backend import MlxBackend

    return MlxBackend(model_name="tiny", compute_type="float16")


def _fallback_composite_happy() -> TranscriberBackend:
    return FallbackTranscriber(
        primary=FakeTranscriberBackend(), fallback_factory=FakeTranscriberBackend
    )


def _fallback_composite_fell_back() -> TranscriberBackend:
    primary = FakeTranscriberBackend()
    primary.fail_load_always(RuntimeError("primary engine failed to load"))
    return FallbackTranscriber(primary=primary, fallback_factory=FakeTranscriberBackend)


# MLX runs only on an Apple-Silicon Mac with the apple-gpu extra (#231). GitHub
# macOS runners can't be relied on for Metal, so this is real-Mac QA only.
_APPLE_SILICON = sys.platform == "darwin" and platform.machine() == "arm64"

BACKENDS = [
    pytest.param(FakeTranscriberBackend, id="fake"),
    pytest.param(_fallback_composite_happy, id="fallback-composite"),
    pytest.param(_fallback_composite_fell_back, id="fallback-composite-fell-back"),
    pytest.param(_faster_whisper_tiny, id="faster-whisper", marks=_real_engine()),
    pytest.param(
        _mlx_tiny,
        id="mlx",
        marks=[
            *_real_engine(),
            pytest.mark.skipif(
                not _APPLE_SILICON, reason="MLX needs an Apple-Silicon Mac (darwin/arm64)"
            ),
        ],
    ),
]


@pytest.fixture(params=BACKENDS)
def backend(request: pytest.FixtureRequest) -> TranscriberBackend:
    factory: Callable[[], TranscriberBackend] = request.param
    return factory()


def test_satisfies_the_protocol(backend: TranscriberBackend) -> None:
    assert isinstance(backend, TranscriberBackend)


def test_nothing_is_loaded_at_construction(backend: TranscriberBackend) -> None:
    assert backend.is_loaded is False


def test_download_to_disk_does_not_load(backend: TranscriberBackend) -> None:
    backend.download_to_disk()
    assert backend.is_loaded is False


def test_load_then_transcribe_returns_text(backend: TranscriberBackend) -> None:
    backend.load_model()
    assert backend.is_loaded is True
    result = backend.transcribe(AUDIO)
    # Text, not the suppressed sentinel. Silence may legitimately transcribe
    # to "" on a real engine, so the contract is the type, not the content.
    assert isinstance(result, str)


def test_transcribe_while_unloaded_returns_the_empty_result(
    backend: TranscriberBackend,
) -> None:
    assert backend.transcribe(AUDIO) == EmptyResult()
    assert backend.is_loaded is False


def test_load_is_idempotent(backend: TranscriberBackend) -> None:
    backend.load_model()
    backend.load_model()
    assert backend.is_loaded is True
    assert isinstance(backend.transcribe(AUDIO), str)


def test_unload_flips_is_loaded(backend: TranscriberBackend) -> None:
    backend.load_model()
    backend.unload_model()
    assert backend.is_loaded is False
    assert backend.transcribe(AUDIO) == EmptyResult()


def test_reload_after_unload(backend: TranscriberBackend) -> None:
    backend.load_model()
    backend.unload_model()
    backend.load_model()
    assert backend.is_loaded is True
    assert isinstance(backend.transcribe(AUDIO), str)


def test_empty_cache_is_safe_and_keeps_load_state(backend: TranscriberBackend) -> None:
    backend.empty_cache()
    assert backend.is_loaded is False
    backend.load_model()
    backend.empty_cache()
    assert backend.is_loaded is True


def test_progress_callback_registration(backend: TranscriberBackend) -> None:
    calls: list[tuple[int, int]] = []
    backend.set_progress_callback(lambda done, total: calls.append((done, total)))
    backend.set_progress_callback(None)
    # Registering (or clearing) a callback is not a load and reports nothing.
    assert backend.is_loaded is False
    assert calls == []
