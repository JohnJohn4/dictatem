"""FasterWhisperBackend — CTranslate2/faster-whisper adapter (Windows manual QA only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.types import AudioChunk, TranscriptionResult


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
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]

        self._model = WhisperModel(
            self._model_name,
            device=self._device,
            compute_type=self._compute_type,
        )

    def unload_model(self) -> None:
        del self._model
        self._model = None
        try:
            import torch  # type: ignore[import-not-found]

            torch.cuda.empty_cache()
        except ImportError:
            pass

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        if self._model is None:
            from dictatem.types import EmptyResult

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
                from dictatem.exceptions import GPUOutOfMemoryError

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
