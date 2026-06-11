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
    the model itself loaded fine.

    CTranslate2 loads these DLLs from its own C++ code via ``LoadLibrary``,
    which searches ``PATH`` but NOT the ``os.add_dll_directory()`` list — so we
    prepend each nvidia ``bin`` dir to ``PATH`` (and also register it, which is
    harmless and helps any ctypes/Python-loaded deps). No-op off Windows or
    when the nvidia packages are absent (CPU-only installs).
    """
    if sys.platform != "win32":
        return
    try:
        import nvidia  # type: ignore[import-not-found]
    except ImportError:
        return
    bin_dirs: list[str] = []
    for base in nvidia.__path__:
        try:
            entries = os.listdir(base)
        except OSError:
            continue
        for entry in entries:
            bin_dir = os.path.join(base, entry, "bin")
            if os.path.isdir(bin_dir):
                bin_dirs.append(bin_dir)
    if not bin_dirs:
        return
    for bin_dir in bin_dirs:
        os.add_dll_directory(bin_dir)
    os.environ["PATH"] = os.pathsep.join([*bin_dirs, os.environ.get("PATH", "")])
    logger.debug("Added CUDA DLL directories to PATH: %s", bin_dirs)


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
        vocabulary: list[str] | None = None,
    ) -> None:
        self._model_name = model_name
        self._compute_type = compute_type
        self._device = device
        self._language = language
        self._vad_filter = vad_filter
        # Vocabulary recognition hints (#126). Fed to faster-whisper as
        # ``hotwords`` when the installed version supports it, else
        # ``initial_prompt``. The kwarg dict is resolved once at load time
        # (when the real ``transcribe`` signature is known) by the pure
        # ``select_recognition_hint``; empty when no terms are configured, so
        # the transcribe call is byte-for-byte unchanged.
        self._vocabulary = vocabulary or []
        self._recognition_hint: dict[str, str] = {}
        self._model: object | None = None
        self._progress_callback: Callable[[int, int], None] | None = None

    def load_model(self) -> None:
        _register_cuda_dll_directories()
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]

        from dictatem.transcribe.vocabulary import (
            backend_supports_hotwords,
            select_recognition_hint,
        )

        self._model = WhisperModel(
            self._model_name,
            device=self._device,
            compute_type=self._compute_type,
        )
        # Detect the capability on the actual model instance, then bake the
        # hint kwargs so every transcribe call reuses them.
        supports = backend_supports_hotwords(self._model.transcribe)  # type: ignore[union-attr]
        self._recognition_hint = select_recognition_hint(
            self._vocabulary, supports_hotwords=supports
        )
        if self._vocabulary:
            hint_kind = next(iter(self._recognition_hint), "none")
            logger.info(
                "Vocabulary: %d term(s) fed to faster-whisper via %s",
                len(self._vocabulary),
                hint_kind,
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
                **self._recognition_hint,
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
