"""Tests for the pure transcription backend selection (#229)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dictatem.interfaces import TranscriberBackend
from dictatem.transcribe.backend_selection import (
    BackendSelection,
    build_transcriber,
    select_backend,
)
from dictatem.transcribe.faster_whisper_backend import FasterWhisperBackend

if TYPE_CHECKING:
    import pytest


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

    def test_mlx_without_an_mlx_engine_degrades_to_cpu_faster_whisper(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Until the MLX backend lands (#231) a hand-pinned `mlx` must not crash
        # the daemon: it runs on CPU faster-whisper and says so once.
        sel = select_backend(device="mlx", model="large-v3-turbo", compute_type="float16")
        with caplog.at_level(logging.WARNING):
            backend = self._build(sel)
        assert isinstance(backend, FasterWhisperBackend)
        assert backend.is_loaded is False
        assert any("mlx" in r.getMessage().lower() for r in caplog.records)
