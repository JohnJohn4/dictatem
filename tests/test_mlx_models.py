"""Tests for the pure MLX model-name mapping and compute-type normalisation (#231)."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from dictatem.transcribe.mlx_models import (
    UnknownMlxModelError,
    keep_speech,
    mlx_repo_for,
    normalise_mlx_compute_type,
)


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
