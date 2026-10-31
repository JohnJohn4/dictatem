"""Aggregating faster-whisper segments into a Transcript (#246).

The real adapter is manual-QA only; the pure aggregation it uses is pinned here
with stand-in segment / info objects shaped like faster-whisper's.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dictatem.transcribe.faster_whisper_backend import transcript_from_segments
from dictatem.types import Transcript


def _seg(text: str, start: float, end: float, logprob: float, nsp: float) -> object:
    return SimpleNamespace(
        text=text, start=start, end=end, avg_logprob=logprob, no_speech_prob=nsp
    )


def test_joins_text_and_aggregates_confidence() -> None:
    segments = [
        _seg(" Hello", 0.0, 3.0, -0.2, 0.1),
        _seg(" world.", 3.0, 4.0, -0.6, 0.4),
    ]
    info = SimpleNamespace(duration=5.0, duration_after_vad=4.0)

    t = transcript_from_segments(segments, info)

    assert t.text == " Hello world."
    assert t.confidence is not None
    # Duration-weighted mean: (3 * -0.2 + 1 * -0.6) / 4 = -0.3
    assert t.confidence.avg_logprob == pytest.approx(-0.3)
    # Worst (max) no_speech_prob.
    assert t.confidence.no_speech_prob == pytest.approx(0.4)
    assert t.speech_duration_s == pytest.approx(4.0)


def test_zero_length_segments_fall_back_to_plain_mean() -> None:
    segments = [_seg("a", 1.0, 1.0, -1.0, 0.0), _seg("b", 1.0, 1.0, -0.5, 0.2)]
    t = transcript_from_segments(segments, SimpleNamespace(duration_after_vad=0.0))
    assert t.confidence is not None
    assert t.confidence.avg_logprob == pytest.approx(-0.75)


def test_no_segments_has_unknown_confidence() -> None:
    t = transcript_from_segments([], SimpleNamespace(duration_after_vad=0.0))
    assert t == Transcript("", confidence=None, speech_duration_s=0.0)


def test_info_without_vad_duration_leaves_it_unknown() -> None:
    t = transcript_from_segments([_seg("hi", 0.0, 1.0, -0.1, 0.0)], object())
    assert t.speech_duration_s is None
