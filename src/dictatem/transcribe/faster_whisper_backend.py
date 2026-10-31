"""FasterWhisperBackend — CTranslate2/faster-whisper adapter (Windows manual QA only)."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Any

from dictatem.exceptions import GPUOutOfMemoryError
from dictatem.types import EmptyResult, SegmentConfidence, Transcript

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

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


def transcript_from_segments(segments: Sequence[Any], info: object) -> Transcript:
    """Build a :class:`Transcript` from faster-whisper segments + info (#246).

    Text is the segments' texts joined (as before). Confidence is the
    duration-weighted mean ``avg_logprob`` (plain mean if every segment is
    zero-length) and the worst ``no_speech_prob``; unknown when there are no
    segments. Speech duration is ``info.duration_after_vad`` — the post-VAD
    speech length — or unknown if the info doesn't carry it.
    """
    text = "".join(seg.text for seg in segments)
    confidence: SegmentConfidence | None = None
    if segments:
        weights = [max(0.0, float(seg.end) - float(seg.start)) for seg in segments]
        total = sum(weights)
        if total <= 0.0:
            weights = [1.0] * len(segments)
            total = float(len(segments))
        avg_logprob = (
            sum(w * float(seg.avg_logprob) for w, seg in zip(weights, segments, strict=True))
            / total
        )
        no_speech_prob = max(float(seg.no_speech_prob) for seg in segments)
        confidence = SegmentConfidence(
            avg_logprob=avg_logprob, no_speech_prob=no_speech_prob
        )
    vad_duration = getattr(info, "duration_after_vad", None)
    speech_duration_s = float(vad_duration) if vad_duration is not None else None
    return Transcript(
        text=text, confidence=confidence, speech_duration_s=speech_duration_s
    )


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
        # Whether the installed faster-whisper takes ``hotwords``; detected at
        # load time and reused by the confirm pass's command bias (#249).
        self._supports_hotwords = False
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
        self._supports_hotwords = backend_supports_hotwords(self._model.transcribe)  # type: ignore[union-attr]
        self._recognition_hint = select_recognition_hint(
            self._vocabulary, supports_hotwords=self._supports_hotwords
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

    def download_to_disk(self) -> None:
        """Fetch the model weights into the on-disk cache WITHOUT loading them.

        Uses faster-whisper's ``download_model`` (a ``huggingface_hub``
        snapshot download), so the weights enter the same cache a later
        ``WhisperModel(...)`` reads from, but no model is constructed — no
        GPU/CPU memory is touched and no CUDA DLLs are needed. Idempotent: an
        already-cached model returns near-instantly with no network (ADR-0025).
        """
        from faster_whisper import download_model  # type: ignore[import-not-found]

        download_model(self._model_name)

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        return self._run(audio, vad_filter=self._vad_filter, hint=self._recognition_hint)

    def transcribe_command(
        self, audio: AudioChunk, trigger_words: Sequence[str]
    ) -> TranscriptionResult:
        """The Borderline confirm pass (#249): command-biased, VAD off.

        The bias replaces the Vocabulary hint for this one call; VAD is off so
        a clipped onset isn't trimmed further (review §6.3).
        """
        from dictatem.transcribe.vocabulary import select_command_bias

        hint = select_command_bias(trigger_words, supports_hotwords=self._supports_hotwords)
        return self._run(audio, vad_filter=False, hint=hint)

    def _run(
        self, audio: AudioChunk, *, vad_filter: bool, hint: dict[str, str]
    ) -> TranscriptionResult:
        if self._model is None:
            return EmptyResult()

        try:
            segments, info = self._model.transcribe(  # type: ignore[union-attr]
                audio,
                language=self._language,
                vad_filter=vad_filter,
                **hint,
            )
            # ``segments`` is a lazy generator — decoding happens while it is
            # consumed, so an OOM still surfaces inside this ``try``.
            return transcript_from_segments(list(segments), info)
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
