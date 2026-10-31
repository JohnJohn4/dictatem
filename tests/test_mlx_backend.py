"""MlxBackend's transcribe paths, on any OS, around a fake ``mlx_whisper`` (#224 x #226).

The real engine is Apple-Silicon-only and opt-in (``test_transcriber_contract``).
These tests skip the load (no MLX, no Metal) and stub ``mlx_whisper.transcribe``
plus faster-whisper's Silero VAD, to pin what the adapter sends the engine and
how it shapes the result into a :class:`~dictatem.types.Transcript`.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import numpy as np
import pytest

from dictatem.transcribe.mlx_backend import MlxBackend
from dictatem.types import EmptyResult, SegmentConfidence, Transcript

AUDIO = np.ones(32_000, dtype=np.float32)  # 2 s at 16 kHz

_RESULT = {
    "text": " Summarize.",
    "segments": [
        {"start": 0.0, "end": 1.0, "text": " Summarize.", "avg_logprob": -0.3,
         "no_speech_prob": 0.05},
    ],
}


class _FakeEngine:
    def __init__(self, speech: list[dict[str, int]]) -> None:
        self.calls: list[tuple[np.ndarray, dict[str, Any]]] = []
        self.vad_calls = 0
        self._speech = speech

    def transcribe(self, samples: np.ndarray, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((samples, kwargs))
        return _RESULT

    def get_speech_timestamps(self, samples: np.ndarray) -> list[dict[str, int]]:
        self.vad_calls += 1
        return self._speech


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> _FakeEngine:
    fake = _FakeEngine(speech=[{"start": 0, "end": 16_000}])
    mlx_whisper = types.ModuleType("mlx_whisper")
    mlx_whisper.transcribe = fake.transcribe  # type: ignore[attr-defined]
    vad = types.ModuleType("faster_whisper.vad")
    vad.get_speech_timestamps = fake.get_speech_timestamps  # type: ignore[attr-defined]
    faster_whisper = types.ModuleType("faster_whisper")
    faster_whisper.vad = vad  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_whisper", mlx_whisper)
    monkeypatch.setitem(sys.modules, "faster_whisper", faster_whisper)
    monkeypatch.setitem(sys.modules, "faster_whisper.vad", vad)
    return fake


def _loaded(**kwargs: Any) -> MlxBackend:
    backend = MlxBackend(model_name="tiny", **kwargs)
    # Skip the real load: no MLX / Metal off a Mac.
    backend._loaded = True  # type: ignore[attr-defined]
    backend._model_path = "/cache/whisper-tiny-mlx"  # type: ignore[attr-defined]
    return backend


def test_transcribe_returns_a_transcript_with_confidence_and_post_vad_duration(
    engine: _FakeEngine,
) -> None:
    result = _loaded(vocabulary=["Dictatem"]).transcribe(AUDIO)

    assert result == Transcript(
        " Summarize.",
        confidence=SegmentConfidence(avg_logprob=-0.3, no_speech_prob=0.05),
        speech_duration_s=1.0,  # the VAD kept 1 s of the 2 s chunk
    )
    samples, kwargs = engine.calls[0]
    assert samples.size == 16_000
    assert kwargs["initial_prompt"] == "Dictatem"  # the persistent Vocabulary hint


def test_silence_is_an_empty_transcript_like_faster_whisper(
    engine: _FakeEngine,
) -> None:
    engine._speech = []

    assert _loaded().transcribe(AUDIO) == Transcript(
        "", confidence=None, speech_duration_s=0.0
    )
    assert engine.calls == []


def test_transcribe_command_is_command_biased_with_vad_off(engine: _FakeEngine) -> None:
    backend = _loaded(vocabulary=["Dictatem"])

    result = backend.transcribe_command(AUDIO, ["summarize", "paste"])

    assert isinstance(result, Transcript)
    assert result.speech_duration_s == pytest.approx(2.0)  # whole chunk: no VAD
    assert engine.vad_calls == 0
    samples, kwargs = engine.calls[0]
    assert samples.size == AUDIO.size
    # The bias replaces the Vocabulary hint; no hotwords on this engine.
    assert kwargs["initial_prompt"] == "Summarize. Paste."
    assert "hotwords" not in kwargs


def test_transcribe_command_with_an_empty_lexicon_sends_no_prompt(
    engine: _FakeEngine,
) -> None:
    _loaded(vocabulary=["Dictatem"]).transcribe_command(AUDIO, [])

    assert "initial_prompt" not in engine.calls[0][1]


def test_unloaded_returns_the_empty_result(engine: _FakeEngine) -> None:
    backend = MlxBackend(model_name="tiny")

    assert backend.transcribe(AUDIO) == EmptyResult()
    assert backend.transcribe_command(AUDIO, ["paste"]) == EmptyResult()
    assert engine.calls == []
