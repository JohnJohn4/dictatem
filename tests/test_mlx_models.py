"""Tests for the pure MLX model-name mapping and compute-type normalisation (#231)."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from dictatem.transcribe.mlx_models import (
    UnknownMlxModelError,
    keep_speech,
    mlx_command_bias,
    mlx_repo_for,
    normalise_mlx_compute_type,
    transcript_from_mlx_result,
)
from dictatem.types import SegmentConfidence, Transcript


class TestMlxRepoFor:
    @pytest.mark.parametrize(
        ("name", "repo"),
        [
            ("tiny", "mlx-community/whisper-tiny-mlx"),
            ("tiny.en", "mlx-community/whisper-tiny.en-mlx"),
            ("base", "mlx-community/whisper-base-mlx"),
            ("base.en", "mlx-community/whisper-base.en-mlx"),
            ("small", "mlx-community/whisper-small-mlx"),
            ("small.en", "mlx-community/whisper-small.en-mlx"),
            ("medium", "mlx-community/whisper-medium-mlx"),
            ("medium.en", "mlx-community/whisper-medium.en-mlx"),
            ("large-v3", "mlx-community/whisper-large-v3-mlx"),
            ("large-v3-turbo", "mlx-community/whisper-large-v3-turbo"),
        ],
    )
    def test_every_whisper_size_name_maps_to_its_mlx_community_repo(
        self, name: str, repo: str
    ) -> None:
        assert mlx_repo_for(name) == repo

    def test_a_full_repo_id_passes_through_unchanged(self) -> None:
        assert (
            mlx_repo_for("mlx-community/whisper-large-v3-turbo-q4")
            == "mlx-community/whisper-large-v3-turbo-q4"
        )

    def test_an_unknown_name_raises_a_typed_error_naming_it(self) -> None:
        with pytest.raises(UnknownMlxModelError, match="large-v9"):
            mlx_repo_for("large-v9")

    def test_the_typed_error_is_a_value_error(self) -> None:
        # The runtime fallback (#232) catches load failures broadly; a
        # ValueError subclass keeps the error honest for other callers too.
        assert issubclass(UnknownMlxModelError, ValueError)


class TestNormaliseMlxComputeType:
    def test_float16_and_float32_are_accepted(self) -> None:
        assert normalise_mlx_compute_type("float16") == "float16"
        assert normalise_mlx_compute_type("float32") == "float32"

    def test_anything_else_warns_and_uses_float16(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            assert normalise_mlx_compute_type("int8_float16") == "float16"
        assert any("int8_float16" in r.getMessage() for r in caplog.records)

    def test_an_accepted_value_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            normalise_mlx_compute_type("float32")
        assert caplog.records == []


class TestKeepSpeech:
    def test_concatenates_the_speech_spans_in_order(self) -> None:
        audio = np.arange(10, dtype=np.float32)
        kept = keep_speech(audio, [{"start": 1, "end": 3}, {"start": 6, "end": 8}])
        assert kept.tolist() == [1.0, 2.0, 6.0, 7.0]
        assert kept.dtype == np.float32

    def test_no_speech_spans_yields_empty_audio(self) -> None:
        kept = keep_speech(np.ones(10, dtype=np.float32), [])
        assert kept.size == 0


def _seg(start: float, end: float, avg_logprob: float, no_speech_prob: float) -> dict:
    """An mlx-whisper (openai-whisper-shaped) segment dict."""
    return {
        "start": start,
        "end": end,
        "text": " x",
        "avg_logprob": avg_logprob,
        "no_speech_prob": no_speech_prob,
    }


class TestTranscriptFromMlxResult:
    def test_confidence_is_aggregated_like_faster_whisper(self) -> None:
        result = {
            "text": " Hello there.",
            "segments": [_seg(0.0, 3.0, -0.2, 0.1), _seg(3.0, 4.0, -1.0, 0.4)],
        }
        t = transcript_from_mlx_result(result, speech_samples=64_000)
        assert t.text == " Hello there."
        assert t.confidence is not None
        # Duration-weighted mean avg_logprob, worst no_speech_prob.
        assert t.confidence.avg_logprob == pytest.approx((3 * -0.2 + 1 * -1.0) / 4)
        assert t.confidence.no_speech_prob == pytest.approx(0.4)
        assert t.speech_duration_s == pytest.approx(4.0)

    def test_no_segments_means_unknown_confidence(self) -> None:
        t = transcript_from_mlx_result({"text": "", "segments": []}, speech_samples=0)
        assert t == Transcript("", confidence=None, speech_duration_s=0.0)

    def test_segments_missing_the_fields_mean_unknown_confidence(self) -> None:
        t = transcript_from_mlx_result(
            {"text": "hi", "segments": [{"start": 0.0, "end": 1.0}]},
            speech_samples=16_000,
        )
        assert t.text == "hi"
        assert t.confidence is None

    def test_a_missing_text_key_is_empty_text(self) -> None:
        t = transcript_from_mlx_result({}, speech_samples=8_000)
        assert t.text == ""
        assert t.speech_duration_s == pytest.approx(0.5)

    def test_matches_the_segment_confidence_type(self) -> None:
        t = transcript_from_mlx_result(
            {"text": "a", "segments": [_seg(0.0, 1.0, -0.5, 0.2)]}, speech_samples=16_000
        )
        assert t.confidence == SegmentConfidence(avg_logprob=-0.5, no_speech_prob=0.2)


class TestMlxCommandBias:
    def test_is_initial_prompt_only_phrased_like_the_faster_whisper_confirm_pass(
        self,
    ) -> None:
        # mlx-whisper has no hotwords: the same one-word sentences, no hotwords key.
        assert mlx_command_bias(["summarize", "paste"]) == {
            "initial_prompt": "Summarize. Paste."
        }

    def test_an_empty_lexicon_is_no_bias(self) -> None:
        assert mlx_command_bias([]) == {}
