"""Unit tests for the pure Model Load Failure classifier (#241).

The classifier maps a model-load exception — plus the configured device,
compute type and model name — onto exactly one actionable reason, with a
user-facing title and message. It is pure: no I/O, no native imports.

faster-whisper, CTranslate2 and huggingface_hub are runtime-only extras (not
installed in the dev/CI environment), so the classifier matches on exception
class *names* across the MRO plus well-known message fragments, never on
``isinstance`` against an imported type. The stand-in classes below mirror the
real huggingface_hub class names and bases exactly; the message strings are
copied verbatim from huggingface_hub 1.x, faster-whisper 1.2 and the
CTranslate2 4.x binary. When the runtime extra *is* installed, the real-type
tests at the bottom also run against the genuine classes.
"""

from __future__ import annotations

import errno
import json

import pytest

from dictatem.exceptions import GPUOutOfMemoryError, ModelLoadError
from dictatem.transcribe.load_failure import (
    LoadFailureReason,
    ModelLoadDiagnosis,
    classify_model_load_failure,
)

# --- Stand-ins mirroring huggingface_hub.errors (names + bases match) -------


class OfflineModeIsEnabled(ConnectionError):  # noqa: N818 — real HF name
    pass


class EntryNotFoundError(Exception):
    pass


class LocalEntryNotFoundError(FileNotFoundError, EntryNotFoundError):
    pass


class HTTPError(OSError):  # requests.HTTPError-ish base
    pass


class HfHubHTTPError(HTTPError):
    pass


class RepositoryNotFoundError(HfHubHTTPError):
    pass


# --- Stand-in mirroring httpx (huggingface_hub 1.x transport) ----------------


class TransportError(Exception):
    pass


class ConnectError(TransportError):
    pass


# --- Verbatim message fragments ---------------------------------------------

_HF_OFFLINE_MSG = (
    "Cannot find an appropriate cached snapshot folder for the specified revision "
    "on the local disk and outgoing traffic has been disabled. To enable repo "
    "look-ups and downloads online, set 'HF_HUB_OFFLINE=0' as environment variable."
)
_HF_NO_CONNECTION_MSG = (
    "Got: ConnectError: [Errno 11001] getaddrinfo failed\n"
    "An error happened while trying to locate the files on the Hub and we cannot "
    "find the appropriate snapshot folder for the specified revision on the local "
    "disk. Please check your internet connection and try again."
)

_MODEL = "large-v3-turbo"


def _classify(
    exc: BaseException,
    *,
    device: str = "cuda",
    compute_type: str = "float16",
    model_name: str = _MODEL,
) -> ModelLoadDiagnosis:
    return classify_model_load_failure(
        exc, device=device, compute_type=compute_type, model_name=model_name
    )


def _chained(outer: BaseException, cause: BaseException) -> BaseException:
    outer.__cause__ = cause
    return outer


class TestDownloadFailed:
    def test_hf_hub_offline_with_empty_cache(self) -> None:
        exc = _chained(
            LocalEntryNotFoundError(_HF_OFFLINE_MSG),
            OfflineModeIsEnabled("Cannot reach https://huggingface.co: offline mode"),
        )
        diagnosis = _classify(exc)
        assert diagnosis.reason is LoadFailureReason.DOWNLOAD_FAILED
        assert _MODEL in diagnosis.message
        assert "internet" in diagnosis.message.lower()

    def test_no_connection(self) -> None:
        exc = _chained(
            LocalEntryNotFoundError(_HF_NO_CONNECTION_MSG),
            ConnectError("[Errno 11001] getaddrinfo failed"),
        )
        assert _classify(exc).reason is LoadFailureReason.DOWNLOAD_FAILED

    def test_bare_transport_error(self) -> None:
        exc = ConnectError("[Errno 111] Connection refused")
        assert _classify(exc).reason is LoadFailureReason.DOWNLOAD_FAILED

    def test_hub_server_error(self) -> None:
        exc = HfHubHTTPError("503 Server Error: Service Unavailable for url: ...")
        assert _classify(exc).reason is LoadFailureReason.DOWNLOAD_FAILED


class TestDiskFull:
    def test_enospc(self) -> None:
        exc = OSError(errno.ENOSPC, "No space left on device")
        diagnosis = _classify(exc)
        assert diagnosis.reason is LoadFailureReason.DISK_FULL
        assert "disk space" in diagnosis.message.lower()

    def test_windows_disk_full_message(self) -> None:
        # winerror 112 (ERROR_DISK_FULL) surfaces with this text.
        exc = OSError("[WinError 112] There is not enough space on the disk")
        assert _classify(exc).reason is LoadFailureReason.DISK_FULL


class TestCudaMissing:
    def test_cublas_dll_not_found(self) -> None:
        exc = RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
        diagnosis = _classify(exc)
        assert diagnosis.reason is LoadFailureReason.CUDA_MISSING
        assert 'device = "cpu"' in diagnosis.message

    def test_cudnn_linux(self) -> None:
        exc = RuntimeError(
            "Unable to load any of {libcudnn_ops.so.9.1.0, libcudnn_ops.so.9.1, "
            "libcudnn_ops.so.9, libcudnn_ops.so}"
        )
        assert _classify(exc).reason is LoadFailureReason.CUDA_MISSING

    def test_no_cuda_device(self) -> None:
        exc = RuntimeError("CUDA failed with error no CUDA-capable device is detected")
        assert _classify(exc).reason is LoadFailureReason.CUDA_MISSING

    def test_driver_too_old(self) -> None:
        exc = RuntimeError(
            "CUDA failed with error CUDA driver version is insufficient for CUDA "
            "runtime version"
        )
        assert _classify(exc).reason is LoadFailureReason.CUDA_MISSING

    def test_ctranslate2_built_without_cuda(self) -> None:
        exc = ValueError("This CTranslate2 package was not compiled with CUDA support")
        assert _classify(exc).reason is LoadFailureReason.CUDA_MISSING


class TestComputeTypeUnsupported:
    def test_float16_on_unsupported_device(self) -> None:
        exc = ValueError(
            "Requested float16 compute type, but the target device or backend do not "
            "support efficient float16 computation."
        )
        diagnosis = _classify(exc, device="cpu", compute_type="float16")
        assert diagnosis.reason is LoadFailureReason.COMPUTE_TYPE_UNSUPPORTED
        assert "float16" in diagnosis.message
        assert "cpu" in diagnosis.message

    def test_invalid_compute_type_value(self) -> None:
        exc = ValueError("Invalid compute type: float17")
        assert (
            _classify(exc, compute_type="float17").reason
            is LoadFailureReason.COMPUTE_TYPE_UNSUPPORTED
        )


class TestOutOfMemory:
    def test_cuda_out_of_memory(self) -> None:
        # Must win over the CUDA-missing "CUDA failed with error" fragment.
        exc = RuntimeError("CUDA failed with error out of memory")
        diagnosis = _classify(exc)
        assert diagnosis.reason is LoadFailureReason.OUT_OF_MEMORY
        assert "GPU" in diagnosis.message

    def test_host_memory_error(self) -> None:
        # pybind11 translates std::bad_alloc to MemoryError.
        exc = MemoryError("std::bad_alloc")
        diagnosis = _classify(exc, device="cpu", compute_type="int8")
        assert diagnosis.reason is LoadFailureReason.OUT_OF_MEMORY
        assert "GPU" not in diagnosis.message

    def test_dictatem_gpu_oom(self) -> None:
        exc = GPUOutOfMemoryError("out of memory")
        assert _classify(exc).reason is LoadFailureReason.OUT_OF_MEMORY


class TestUnknownModel:
    def test_invalid_model_size(self) -> None:
        exc = ValueError(
            "Invalid model size 'large-v9', expected one of: tiny.en, tiny, base.en, "
            "base, small.en, small, medium.en, medium, large-v1, large-v2, large-v3, "
            "large, distil-large-v2, distil-medium.en, distil-small.en, "
            "distil-large-v3, distil-large-v3.5, large-v3-turbo, turbo"
        )
        diagnosis = _classify(exc, model_name="large-v9")
        assert diagnosis.reason is LoadFailureReason.UNKNOWN_MODEL
        assert "large-v9" in diagnosis.message

    def test_repository_not_found(self) -> None:
        # Must win over the generic HfHubHTTPError download bucket.
        exc = RepositoryNotFoundError(
            "404 Client Error. Repository Not Found for url: "
            "https://huggingface.co/api/models/someone/nope/revision/main."
        )
        assert (
            _classify(exc, model_name="someone/nope").reason
            is LoadFailureReason.UNKNOWN_MODEL
        )


class TestCorruptCache:
    def test_model_bin_missing(self) -> None:
        exc = RuntimeError(
            "Unable to open file 'model.bin' in model "
            "'C:\\Users\\u\\.cache\\huggingface\\hub\\models--x\\snapshots\\abc'"
        )
        diagnosis = _classify(exc)
        assert diagnosis.reason is LoadFailureReason.CORRUPT_CACHE
        assert "re-download" in diagnosis.message

    def test_model_bin_truncated(self) -> None:
        exc = RuntimeError(
            "File model.bin is incomplete: failed to read a buffer of size 4096 at "
            "position 1234"
        )
        assert _classify(exc).reason is LoadFailureReason.CORRUPT_CACHE

    def test_unreadable_config_json(self) -> None:
        exc = json.JSONDecodeError("Expecting value", "", 0)
        assert _classify(exc).reason is LoadFailureReason.CORRUPT_CACHE

    def test_unreadable_tokenizer_json(self) -> None:
        # tokenizers raises a bare Exception carrying the serde error.
        exc = Exception("expected value at line 1 column 1")
        assert _classify(exc).reason is LoadFailureReason.CORRUPT_CACHE


class TestUnknown:
    def test_unrecognised_error_falls_through(self) -> None:
        diagnosis = _classify(RuntimeError("something nobody has seen before"))
        assert diagnosis.reason is LoadFailureReason.UNKNOWN
        assert "log" in diagnosis.message.lower()

    def test_every_reason_has_a_title_and_message(self) -> None:
        diagnosis = _classify(RuntimeError("?"))
        assert diagnosis.title
        assert diagnosis.message


class TestCauseChain:
    def test_classifies_through_a_model_load_error_wrapper(self) -> None:
        wrapper = _chained(
            ModelLoadError("Model failed to load"),
            RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"),
        )
        assert _classify(wrapper).reason is LoadFailureReason.CUDA_MISSING

    def test_implicit_context_is_followed(self) -> None:
        inner = OSError(errno.ENOSPC, "No space left on device")
        outer = RuntimeError("download aborted")
        outer.__context__ = inner
        assert _classify(outer).reason is LoadFailureReason.DISK_FULL


# --- Genuine runtime types (skipped unless the runtime extra is installed) ---


class TestRealHuggingFaceTypes:
    def test_real_local_entry_not_found_is_download_failed(self) -> None:
        errors = pytest.importorskip("huggingface_hub.errors")
        exc = errors.LocalEntryNotFoundError(_HF_OFFLINE_MSG)
        assert _classify(exc).reason is LoadFailureReason.DOWNLOAD_FAILED

    def test_real_offline_mode_is_download_failed(self) -> None:
        errors = pytest.importorskip("huggingface_hub.errors")
        exc = errors.OfflineModeIsEnabled("offline")
        assert _classify(exc).reason is LoadFailureReason.DOWNLOAD_FAILED
