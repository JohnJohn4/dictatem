"""Tests for the pure transcription backend selection (#229)."""

from __future__ import annotations

import sys

from dictatem.interfaces import TranscriberBackend
from dictatem.transcribe.backend_selection import (
    BackendSelection,
    build_transcriber,
    cpu_fallback_selection,
    select_backend,
)
from dictatem.transcribe.fallback import FallbackTranscriber
from dictatem.transcribe.faster_whisper_backend import FasterWhisperBackend
from dictatem.transcribe.mlx_models import mlx_recognition_hint


class TestSelectBackend:
    def test_cuda_selects_faster_whisper_unchanged(self) -> None:
        sel = select_backend(device="cuda", model="large-v3-turbo", compute_type="float16")
        assert sel == BackendSelection(
            kind="faster-whisper",
            model="large-v3-turbo",
            device="cuda",
            compute_type="float16",
            warning=None,
        )

    def test_cpu_selects_faster_whisper_unchanged(self) -> None:
        sel = select_backend(device="cpu", model="small", compute_type="int8")
        assert sel == BackendSelection(
            kind="faster-whisper",
            model="small",
            device="cpu",
            compute_type="int8",
            warning=None,
        )

    def test_mlx_is_reserved_for_the_mlx_backend(self) -> None:
        sel = select_backend(device="mlx", model="large-v3-turbo", compute_type="float16")
        assert sel == BackendSelection(
            kind="mlx",
            model="large-v3-turbo",
            device="mlx",
            compute_type="float16",
            warning=None,
        )

    def test_unknown_device_warns_and_resolves_to_the_cpu_row(self) -> None:
        sel = select_backend(device="metal", model="large-v3-turbo", compute_type="float16")
        assert sel.kind == "faster-whisper"
        # The whole CPU row (base/cpu/int8), not just the device: a GPU
        # compute_type would not run on CPU either (ADR-0009).
        assert (sel.model, sel.device, sel.compute_type) == ("base", "cpu", "int8")
        assert sel.warning is not None
        assert "metal" in sel.warning


class TestBuildTranscriber:
    def _build(self, sel: BackendSelection) -> TranscriberBackend:
        return build_transcriber(sel, language=None, vad_filter=True, vocabulary=[])

    def test_faster_whisper_selection_builds_an_unloaded_faster_whisper_backend(
        self,
    ) -> None:
        for device in ("cuda", "cpu"):
            sel = select_backend(device=device, model="small", compute_type="int8")
            backend = self._build(sel)
            assert isinstance(backend, FasterWhisperBackend)
            assert isinstance(backend, TranscriberBackend)
            assert backend.is_loaded is False

    def test_mlx_selection_builds_the_session_fallback_composite_without_importing_mlx(
        self,
    ) -> None:
        # Construction is import-safe on any OS: mlx / mlx_whisper are imported
        # lazily on the backend's worker thread at load time (#231). The MLX
        # backend is wrapped in the CPU session fallback (#232).
        before = set(sys.modules)
        sel = select_backend(device="mlx", model="large-v3-turbo", compute_type="float16")
        backend = self._build(sel)
        assert isinstance(backend, FallbackTranscriber)
        assert backend.fell_back is False
        assert isinstance(backend, TranscriberBackend)
        assert backend.is_loaded is False
        new = set(sys.modules) - before
        assert not [m for m in new if m.split(".")[0] in {"mlx", "mlx_whisper"}]

    def test_cuda_and_cpu_are_never_wrapped_in_the_fallback_composite(self) -> None:
        for device in ("cuda", "cpu"):
            sel = select_backend(device=device, model="small", compute_type="int8")
            backend = build_transcriber(
                sel,
                language=None,
                vad_filter=True,
                vocabulary=[],
                on_fallback=lambda: None,
            )
            assert not isinstance(backend, FallbackTranscriber)


class TestCpuFallbackSelection:
    def test_is_the_apple_silicon_cpu_row_on_faster_whisper(self) -> None:
        assert cpu_fallback_selection() == BackendSelection(
            kind="faster-whisper", model="small", device="cpu", compute_type="int8"
        )


class TestMlxVocabularyHint:
    def test_vocabulary_is_fed_via_initial_prompt(self) -> None:
        # mlx-whisper has no `hotwords`, so the pure hint selection must pick
        # initial_prompt for the MLX path.
        assert mlx_recognition_hint(["Dictatem", "Ollama"]) == {
            "initial_prompt": "Dictatem Ollama"
        }

    def test_empty_vocabulary_leaves_the_call_unchanged(self) -> None:
        assert mlx_recognition_hint([]) == {}
