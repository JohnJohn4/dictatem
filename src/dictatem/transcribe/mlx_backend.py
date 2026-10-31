"""MlxBackend — mlx-whisper adapter for the Apple-GPU tier (#231, spec #224).

A thin native adapter (macOS arm64 only, real-Mac QA; excluded from pyright like
the other mac adapters). The decisions it relies on live in the pure
:mod:`dictatem.transcribe.mlx_models`.

Import-safe on every OS: ``mlx`` / ``mlx_whisper`` (and faster-whisper's VAD)
are imported lazily inside the methods, so constructing an ``MlxBackend`` or
importing the daemon on Windows or an Intel Mac never touches MLX.

Every MLX call (load, transcribe, unload, cache clearing) runs on ONE
backend-owned worker thread, so MLX never sees concurrent or cross-thread use
under load-on-arm (ADR-0025). The public methods block until the worker is done,
matching the synchronous ``TranscriberBackend`` contract.
"""

from __future__ import annotations

import gc
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, TypeVar

import numpy as np

from dictatem.transcribe.mlx_models import (
    keep_speech,
    mlx_recognition_hint,
    mlx_repo_for,
    normalise_mlx_compute_type,
)
from dictatem.types import EmptyResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.types import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _local_snapshot(repo: str) -> str:
    """Path of *repo*'s snapshot in the HF cache, fetching only if it's missing.

    The local lookup needs no network, so "offline after setup" holds for the
    GPU tier (ADR-0025): a cached model loads with ``HF_HUB_OFFLINE=1`` or no
    connection at all.
    """
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        return snapshot_download(repo, local_files_only=True)
    except LocalEntryNotFoundError:
        logger.info("Fetching MLX model %s into the HuggingFace cache", repo)
        return snapshot_download(repo)


class MlxBackend:
    """TranscriberBackend implementation using mlx-whisper on the Apple GPU."""

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        compute_type: str = "float16",
        language: str | None = None,
        vad_filter: bool = True,
        vocabulary: list[str] | None = None,
    ) -> None:
        self._model_name = model_name
        self._compute_type = compute_type
        self._language = language
        self._vad_filter = vad_filter
        self._vocabulary = vocabulary or []
        # mlx-whisper has no `hotwords`: Vocabulary always rides initial_prompt.
        self._recognition_hint = mlx_recognition_hint(self._vocabulary)
        self._model_path: str | None = None
        self._fp16 = True
        self._loaded = False
        self._progress_callback: Callable[[int, int], None] | None = None
        # The worker thread is only started on the first submit.
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dictatem-mlx")

    def _on_worker(self, fn: Callable[[], _T]) -> _T:
        return self._worker.submit(fn).result()

    # -- TranscriberBackend ---------------------------------------------------

    def load_model(self) -> None:
        self._on_worker(self._load)

    def unload_model(self) -> None:
        self._on_worker(self._unload)

    def download_to_disk(self) -> None:
        """Fetch the MLX weights into the HF cache WITHOUT loading them.

        Touches only huggingface_hub (no MLX, no Metal), so it runs on the
        caller's thread. Idempotent: a cached model returns with no network.
        """
        _local_snapshot(mlx_repo_for(self._model_name))

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        return self._on_worker(lambda: self._transcribe(audio))

    def empty_cache(self) -> None:
        self._on_worker(self._clear_mlx_cache)

    def set_progress_callback(self, callback: Callable[[int, int], None] | None) -> None:
        self._progress_callback = callback

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # -- worker-thread bodies -------------------------------------------------

    def _load(self) -> None:
        if self._loaded:
            return
        # UnknownMlxModelError surfaces here, at load, where the runtime
        # fallback (#232) catches it like any other load failure.
        repo = mlx_repo_for(self._model_name)
        fp16 = normalise_mlx_compute_type(self._compute_type) == "float16"
        path = _local_snapshot(repo)

        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder

        ModelHolder.get_model(path, mx.float16 if fp16 else mx.float32)
        self._model_path = path
        self._fp16 = fp16
        self._loaded = True
        if self._vocabulary:
            logger.info(
                "Vocabulary: %d term(s) fed to mlx-whisper via initial_prompt "
                "(no hotwords on this engine; biasing may be weaker)",
                len(self._vocabulary),
            )

    def _unload(self) -> None:
        if not self._loaded:
            return
        from mlx_whisper.transcribe import ModelHolder

        # Drop the process-global holder, then return the buffers to the OS so
        # idle unload / tray Unload actually frees unified memory.
        ModelHolder.model = None
        ModelHolder.model_path = None
        self._model_path = None
        self._loaded = False
        gc.collect()
        self._clear_mlx_cache()

    def _clear_mlx_cache(self) -> None:
        # Never import MLX just to clear a cache it hasn't allocated.
        if "mlx.core" not in sys.modules:
            return
        import mlx.core as mx

        mx.clear_cache()

    def _transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        if not self._loaded or self._model_path is None:
            return EmptyResult()
        samples = np.asarray(audio, dtype=np.float32)
        if self._vad_filter:
            # mlx-whisper has no VAD: pre-trim with the Silero VAD bundled in
            # faster-whisper (always installed as the fallback engine), the
            # same silence-hallucination guard as the CPU path.
            from faster_whisper.vad import get_speech_timestamps

            samples = keep_speech(samples, get_speech_timestamps(samples))
            if samples.size == 0:
                # Same as faster-whisper's vad_filter on silence: empty text.
                return ""

        import mlx_whisper

        kwargs: dict[str, Any] = {
            "path_or_hf_repo": self._model_path,
            "language": self._language,
            "fp16": self._fp16,
            "verbose": None,
            **self._recognition_hint,
        }
        result = mlx_whisper.transcribe(samples, **kwargs)
        return str(result.get("text", ""))
