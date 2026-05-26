"""FasterWhisperBackend — CTranslate2/faster-whisper adapter (Windows manual QA only)."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from dictatem.exceptions import GPUOutOfMemoryError
from dictatem.types import EmptyResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.types import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)


def _register_cuda_dll_directories() -> None:
    """Make the pip-installed NVIDIA CUDA runtime DLLs loadable on Windows.

    CTranslate2 (under faster-whisper) loads cuBLAS and cuDNN lazily at
    transcription time. The ``nvidia-*-cu12`` wheels ship those DLLs under
    ``site-packages/nvidia/<lib>/bin``, but unlike Linux that directory is not
    on the Windows DLL search path — so the load fails at the first GPU op with
    e.g. "Library cublas64_12.dll is not found or cannot be loaded" even though
    the model itself loaded fine. Register each nvidia ``bin`` dir so Windows
    can resolve them. No-op off Windows or when the nvidia packages are absent
    (CPU-only installs).
    """
    if sys.platform != "win32":
        return
    try:
        import nvidia  # type: ignore[import-not-found]
    except ImportError:
        return
    for base in nvidia.__path__:
        try:
            entries = os.listdir(base)
        except OSError:
            continue
        for entry in entries:
            bin_dir = os.path.join(base, entry, "bin")
            if os.path.isdir(bin_dir):
                os.add_dll_directory(bin_dir)
                logger.debug("Registered CUDA DLL directory %s", bin_dir)


class FasterWhisperBackend:
    """TranscriberBackend implementation using faster-whisper.

    Requires ``faster-whisper``, ``torch``, and a CUDA GPU at runtime.
    Not imported by the pure-core lifecycle module.
    """

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        compute_type: str = "float16",
        device: str = "cuda",
        language: str | None = None,
        vad_filter: bool = True,
    ) -> None:
        self._model_name = model_name
        self._compute_type = compute_type
        self._device = device
        self._language = language
        self._vad_filter = vad_filter
        self._model: object | None = None
        self._progress_callback: Callable[[int, int], None] | None = None

    def load_model(self) -> None:
        _register_cuda_dll_directories()
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]

        self._model = WhisperModel(
            self._model_name,
            device=self._device,
            compute_type=self._compute_type,
        )

    def unload_model(self) -> None:
        self._model = None
        self.empty_cache()

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        if self._model is None:
            return EmptyResult()

        try:
            segments, _info = self._model.transcribe(  # type: ignore[union-attr]
                audio,
                language=self._language,
                vad_filter=self._vad_filter,
            )
            return "".join(seg.text for seg in segments)
        except Exception as exc:
            if "out of memory" in str(exc).lower():
                raise GPUOutOfMemoryError(str(exc)) from exc
            raise

    def empty_cache(self) -> None:
        try:
            import torch  # type: ignore[import-not-found]

            torch.cuda.empty_cache()
        except ImportError:
            pass

    def set_progress_callback(
        self, callback: Callable[[int, int], None] | None
    ) -> None:
        self._progress_callback = callback

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
