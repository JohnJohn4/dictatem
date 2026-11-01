"""Pure classifier mapping a model-load failure to an actionable message (#241).

Given the exception a model load raised plus the configured device, compute
type and model name, this returns exactly one ``LoadFailureReason`` with a
user-facing title and message, surfaced on the daemon's model-error path.
Modelled on the Transform failure classifier (``transform/failure_classifier``).

This module is PURE: no I/O, no native imports. faster-whisper, CTranslate2
and huggingface_hub are runtime-only extras, so we match on exception class
*names* across the MRO plus well-known message fragments rather than on
``isinstance`` against imported types. The whole cause chain (``__cause__``,
then ``__context__``) is examined outermost first, so a wrapping
``ModelLoadError`` or a huggingface_hub error raised ``from`` a transport error
both classify correctly. Anything unrecognised is UNKNOWN — we never guess.
"""

from __future__ import annotations

import errno
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_CONFIG_PATH = "~/.dictatem/config.toml"


class LoadFailureReason(Enum):
    """The diagnosed cause of a transcription-model load failure."""

    DOWNLOAD_FAILED = auto()
    """The weights aren't cached and couldn't be fetched (offline,
    ``HF_HUB_OFFLINE=1``, DNS/connection failure, Hub server error)."""

    DISK_FULL = auto()
    """Writing the weights to the cache ran out of disk space."""

    CUDA_MISSING = auto()
    """The CUDA runtime (cuBLAS/cuDNN), driver or GPU couldn't be found, or
    CTranslate2 was built without CUDA."""

    COMPUTE_TYPE_UNSUPPORTED = auto()
    """The device can't run the configured compute type (e.g. float16 on CPU)."""

    OUT_OF_MEMORY = auto()
    """GPU or host memory ran out while loading the model."""

    UNKNOWN_MODEL = auto()
    """The configured model name isn't a faster-whisper size or a Hub repo."""

    CORRUPT_CACHE = auto()
    """The cached model files are missing, truncated or unreadable."""

    UNKNOWN = auto()
    """Anything else — see the log."""


@dataclass(frozen=True)
class ModelLoadDiagnosis:
    """A classified model-load failure: reason plus what to tell the user."""

    reason: LoadFailureReason
    title: str
    message: str


def classify_model_load_failure(
    exc: BaseException,
    *,
    device: str,
    compute_type: str,
    model_name: str,
) -> ModelLoadDiagnosis:
    """Diagnose *exc* (raised while loading the model) into a ``ModelLoadDiagnosis``."""
    for link in _cause_chain(exc):
        reason = _classify_one(link)
        if reason is not None:
            return _diagnosis(
                reason, device=device, compute_type=compute_type, model_name=model_name
            )
    return _diagnosis(
        LoadFailureReason.UNKNOWN,
        device=device,
        compute_type=compute_type,
        model_name=model_name,
    )


def _cause_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


_DOWNLOAD_TYPES = frozenset(
    {
        "LocalEntryNotFoundError",  # huggingface_hub: not cached + can't fetch
        "OfflineModeIsEnabled",  # huggingface_hub: HF_HUB_OFFLINE=1
        "HfHubHTTPError",  # huggingface_hub: Hub returned an HTTP error
        "TransportError",  # httpx (huggingface_hub 1.x transport)
        "ConnectionError",  # builtin + requests (huggingface_hub 0.x)
        "TimeoutError",
        "Timeout",  # requests
        "gaierror",  # socket DNS failure
    }
)
_UNKNOWN_MODEL_TYPES = frozenset({"RepositoryNotFoundError"})
_CORRUPT_TYPES = frozenset({"JSONDecodeError"})

_OOM_FRAGMENTS = ("out of memory", "bad_alloc")
_DISK_FULL_FRAGMENTS = ("no space left on device", "not enough space on the disk")
_UNKNOWN_MODEL_FRAGMENTS = ("invalid model size",)
_CUDA_FRAGMENTS = (
    "is not found or cannot be loaded",  # CTranslate2 (Windows DLLs)
    "unable to load any of {libcu",  # CTranslate2 (Linux .so)
    "could not load library",  # cuDNN
    "not compiled with cuda support",
    "cuda driver",
    "no cuda-capable device",
    "cuda failed with error",
)
_COMPUTE_TYPE_FRAGMENTS = ("do not support efficient", "invalid compute type")
_CORRUPT_FRAGMENTS = (
    "unable to open file",  # CTranslate2: model.bin missing from the snapshot
    "is incomplete",  # CTranslate2: model.bin truncated
    "unsupported model binary version",
    "expected value at line",  # tokenizers: unreadable tokenizer.json
    "eof while parsing",
)
# Windows ERROR_DISK_FULL / ERROR_HANDLE_DISK_FULL.
_WIN_DISK_FULL = (112, 39)


def _classify_one(exc: BaseException) -> LoadFailureReason | None:
    names = {cls.__name__ for cls in type(exc).__mro__}
    msg = str(exc).lower()

    # Order matters: OOM before CUDA ("CUDA failed with error out of memory"),
    # unknown-model before download (RepositoryNotFoundError is an HfHubHTTPError).
    if isinstance(exc, MemoryError) or "GPUOutOfMemoryError" in names or _has(msg, _OOM_FRAGMENTS):
        return LoadFailureReason.OUT_OF_MEMORY
    if _is_disk_full(exc) or _has(msg, _DISK_FULL_FRAGMENTS):
        return LoadFailureReason.DISK_FULL
    if names & _UNKNOWN_MODEL_TYPES or _has(msg, _UNKNOWN_MODEL_FRAGMENTS):
        return LoadFailureReason.UNKNOWN_MODEL
    if names & _DOWNLOAD_TYPES:
        return LoadFailureReason.DOWNLOAD_FAILED
    if _has(msg, _CUDA_FRAGMENTS):
        return LoadFailureReason.CUDA_MISSING
    if _has(msg, _COMPUTE_TYPE_FRAGMENTS):
        return LoadFailureReason.COMPUTE_TYPE_UNSUPPORTED
    if names & _CORRUPT_TYPES or _has(msg, _CORRUPT_FRAGMENTS):
        return LoadFailureReason.CORRUPT_CACHE
    return None


def _has(msg: str, fragments: tuple[str, ...]) -> bool:
    return any(fragment in msg for fragment in fragments)


def _is_disk_full(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    return exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) in _WIN_DISK_FULL


def _diagnosis(
    reason: LoadFailureReason, *, device: str, compute_type: str, model_name: str
) -> ModelLoadDiagnosis:
    if reason is LoadFailureReason.DOWNLOAD_FAILED:
        return ModelLoadDiagnosis(
            reason,
            "Model Download Failed",
            f"Couldn't download the speech model '{model_name}' — you appear to be "
            "offline, or Hugging Face is unreachable. Connect to the internet once "
            "so it can download, then try again.",
        )
    if reason is LoadFailureReason.DISK_FULL:
        return ModelLoadDiagnosis(
            reason,
            "Disk Full",
            f"There isn't enough free disk space to download the speech model "
            f"'{model_name}'. Free up some disk space, then try again.",
        )
    if reason is LoadFailureReason.CUDA_MISSING:
        return ModelLoadDiagnosis(
            reason,
            "GPU Runtime Missing",
            "The NVIDIA CUDA runtime or GPU couldn't be used. Reinstall Dictatem "
            "with GPU support (see the README), or run on CPU by setting "
            f'device = "cpu" and compute_type = "int8" under [model] in {_CONFIG_PATH}.',
        )
    if reason is LoadFailureReason.COMPUTE_TYPE_UNSUPPORTED:
        return ModelLoadDiagnosis(
            reason,
            "Compute Type Unsupported",
            f"The {device} device doesn't support compute type '{compute_type}'. "
            f'Change compute_type under [model] in {_CONFIG_PATH} (e.g. "int8").',
        )
    if reason is LoadFailureReason.OUT_OF_MEMORY:
        where = "GPU memory" if device != "cpu" else "memory"
        return ModelLoadDiagnosis(
            reason,
            "Not Enough Memory",
            f"There isn't enough {where} to load the speech model '{model_name}'. "
            "Close other memory-heavy apps, or pick a smaller model (name under "
            f"[model] in {_CONFIG_PATH}).",
        )
    if reason is LoadFailureReason.UNKNOWN_MODEL:
        return ModelLoadDiagnosis(
            reason,
            "Unknown Model",
            f"'{model_name}' isn't a known speech model. Check name under [model] in "
            f'{_CONFIG_PATH} (e.g. "large-v3-turbo", "small" or "base").',
        )
    if reason is LoadFailureReason.CORRUPT_CACHE:
        return ModelLoadDiagnosis(
            reason,
            "Model Files Damaged",
            f"The downloaded files for '{model_name}' look damaged or incomplete. "
            "Delete the model's folder from the Hugging Face cache "
            "(~/.cache/huggingface/hub) so it can re-download, then try again.",
        )
    return ModelLoadDiagnosis(
        reason,
        "Model Unavailable",
        "The speech model couldn't be loaded; check the log for details.",
    )
