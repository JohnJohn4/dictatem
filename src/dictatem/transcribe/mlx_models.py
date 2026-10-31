"""Pure decisions for the Apple-GPU MLX backend (#231, spec #224).

Kept apart from the native adapter (``mlx_backend``) so they are pyright-checked
and unit-tested on any OS. Nothing here imports MLX, mlx-whisper or
faster-whisper.

- :func:`mlx_repo_for` maps a ``[model].name`` Whisper size name to its
  ``mlx-community`` HuggingFace repo. A value containing ``/`` is already a repo
  id and passes through. An unknown name raises :class:`UnknownMlxModelError`,
  which the runtime fallback (#232) catches like any other load failure.
- :func:`normalise_mlx_compute_type` accepts ``float16`` / ``float32`` and
  degrades anything else to ``float16`` with a warning.
- :func:`mlx_recognition_hint` feeds Vocabulary via ``initial_prompt`` (the
  engine has no ``hotwords``).
- :func:`mlx_command_bias` is the confirm pass's one-off command bias (#249):
  ``initial_prompt`` only, phrased exactly as for faster-whisper.
- :func:`keep_speech` concatenates the speech spans a VAD found, so the backend
  can pre-trim silence before mlx-whisper (which has no VAD of its own).
- :func:`transcript_from_mlx_result` turns mlx-whisper's result dict into a
  :class:`~dictatem.types.Transcript` with the same confidence aggregation as
  faster-whisper (#246).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np

from dictatem.transcribe.faster_whisper_backend import transcript_from_segments
from dictatem.transcribe.vocabulary import select_command_bias, select_recognition_hint
from dictatem.types import SAMPLE_RATE, Transcript

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Whisper size name -> mlx-community repo id (verified on the Hub 2026-10-31).
# large-v3-turbo is the one repo without the "-mlx" suffix.
_MLX_REPOS: dict[str, str] = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "tiny.en": "mlx-community/whisper-tiny.en-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "base.en": "mlx-community/whisper-base.en-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "small.en": "mlx-community/whisper-small.en-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "medium.en": "mlx-community/whisper-medium.en-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}

_MLX_COMPUTE_TYPES = frozenset({"float16", "float32"})
_DEFAULT_MLX_COMPUTE_TYPE = "float16"


class UnknownMlxModelError(ValueError):
    """``[model].name`` is neither a known Whisper size nor an ``org/name`` repo id."""


def mlx_repo_for(name: str) -> str:
    """Return the MLX-format HuggingFace repo for the ``[model].name`` *name*. Pure."""
    if "/" in name:
        return name
    try:
        return _MLX_REPOS[name]
    except KeyError:
        raise UnknownMlxModelError(
            f"Unknown [model].name {name!r} for the Apple-GPU (MLX) engine "
            f"(expected one of {', '.join(_MLX_REPOS)}, or an org/name repo id)"
        ) from None


def normalise_mlx_compute_type(compute_type: str) -> str:
    """Return ``float16`` / ``float32`` for *compute_type*; anything else -> ``float16``."""
    if compute_type in _MLX_COMPUTE_TYPES:
        return compute_type
    logger.warning(
        "[model].compute_type %r is not supported by the Apple-GPU (MLX) engine "
        "(expected float16 or float32) — using %s.",
        compute_type,
        _DEFAULT_MLX_COMPUTE_TYPE,
    )
    return _DEFAULT_MLX_COMPUTE_TYPE


def mlx_recognition_hint(vocabulary: list[str]) -> dict[str, str]:
    """Vocabulary kwargs for mlx-whisper: it has no ``hotwords``, so ``initial_prompt``."""
    return select_recognition_hint(vocabulary, supports_hotwords=False)


def mlx_command_bias(trigger_words: Sequence[str]) -> dict[str, str]:
    """Confirm-pass bias for mlx-whisper (#249): no ``hotwords``, so ``initial_prompt``."""
    return select_command_bias(trigger_words, supports_hotwords=False)


def transcript_from_mlx_result(
    result: Mapping[str, Any], *, speech_samples: int, sample_rate: int = SAMPLE_RATE
) -> Transcript:
    """Build a :class:`Transcript` from an ``mlx_whisper.transcribe`` result. Pure.

    mlx-whisper's segments are openai-whisper-shaped dicts (``start``, ``end``,
    ``avg_logprob``, ``no_speech_prob``), so confidence is aggregated exactly as
    for faster-whisper (duration-weighted mean ``avg_logprob``, worst
    ``no_speech_prob``; unknown with no segments, or if a segment lacks the
    fields). Text is the result's ``text``. *speech_samples* is the length of the
    audio actually fed to the model — post-VAD when the backend pre-trimmed it,
    the whole chunk when VAD was off, matching faster-whisper's
    ``duration_after_vad``.
    """
    speech_duration_s = speech_samples / sample_rate
    raw_segments = result.get("segments") or []
    try:
        segments = [
            SimpleNamespace(
                text=str(seg.get("text", "")),
                start=float(seg["start"]),
                end=float(seg["end"]),
                avg_logprob=float(seg["avg_logprob"]),
                no_speech_prob=float(seg["no_speech_prob"]),
            )
            for seg in raw_segments
        ]
    except (KeyError, TypeError, ValueError, AttributeError):
        segments = []
    confidence = transcript_from_segments(segments, None).confidence
    return Transcript(
        text=str(result.get("text", "")),
        confidence=confidence,
        speech_duration_s=speech_duration_s,
    )


def keep_speech(
    audio: NDArray[np.float32], spans: Iterable[Mapping[str, int]]
) -> NDArray[np.float32]:
    """Concatenate the ``{"start", "end"}`` sample spans of *audio*, in order. Pure."""
    pieces = [audio[span["start"] : span["end"]] for span in spans]
    if not pieces:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(pieces).astype(np.float32, copy=False)
