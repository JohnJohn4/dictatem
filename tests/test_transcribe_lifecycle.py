"""Tests for TranscribeLifecycle — pure-core lifecycle wrapper."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import numpy as np
import pytest

from dictatem.exceptions import GPUOutOfMemoryError, TranscriptionFailedError
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.types import EmptyResult
from tests.fakes import FakeTranscriberBackend
from tests.support import wait_until

if TYPE_CHECKING:
    from dictatem.types import TranscriptionResult

AUDIO = np.zeros(16000, dtype=np.float32)


class TestLazyLoad:
    def test_no_load_at_construction(self) -> None:
        backend = FakeTranscriberBackend()
        TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert backend.load_count == 0
        assert backend.is_loaded is False

    def test_load_on_first_transcribe(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        lc.transcribe(AUDIO)
        assert backend.load_count == 1
        assert backend.is_loaded is True

    def test_no_double_load_on_second_transcribe(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        lc.transcribe(AUDIO)
        lc.transcribe(AUDIO)
        assert backend.load_count == 1


class TestIdleTimer:
    def test_no_unload_before_timeout(self) -> None:
        current_time = 0.0

        def clock() -> float:
            return current_time

        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(
            backend=backend, clock=clock, idle_timeout_s=1800.0
        )
        lc.transcribe(AUDIO)
        assert backend.is_loaded is True

        current_time = 29 * 60  # 29 minutes
        lc.check_idle()
        assert backend.is_loaded is True
        assert backend.unload_count == 0

    def test_unload_at_timeout(self) -> None:
        current_time = 0.0

        def clock() -> float:
            return current_time

        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(
            backend=backend, clock=clock, idle_timeout_s=1800.0
        )
        lc.transcribe(AUDIO)

        current_time = 30 * 60  # 30 minutes
        lc.check_idle()
        assert backend.is_loaded is False
        assert backend.unload_count == 1

    def test_timer_resets_on_each_transcribe(self) -> None:
        current_time = 0.0

        def clock() -> float:
            return current_time

        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(
            backend=backend, clock=clock, idle_timeout_s=1800.0
        )
        lc.transcribe(AUDIO)

        # 20 minutes later, transcribe again
        current_time = 20 * 60
        lc.transcribe(AUDIO)

        # 29 minutes after second transcribe (49 min total)
        current_time = 49 * 60
        lc.check_idle()
        assert backend.is_loaded is True

        # 30 minutes after second transcribe (50 min total)
        current_time = 50 * 60
        lc.check_idle()
        assert backend.is_loaded is False

    def test_lazy_reload_after_idle_unload(self) -> None:
        current_time = 0.0

        def clock() -> float:
            return current_time

        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(
            backend=backend, clock=clock, idle_timeout_s=1800.0
        )
        lc.transcribe(AUDIO)
        assert backend.load_count == 1

        # Idle unload
        current_time = 30 * 60
        lc.check_idle()
        assert backend.is_loaded is False

        # Transcribe again triggers reload
        current_time = 35 * 60
        lc.transcribe(AUDIO)
        assert backend.load_count == 2
        assert backend.is_loaded is True


class TestPreload:
    def test_preload_loads_on_background_thread(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        lc.preload()
        wait_until(lambda: lc.is_loaded)

        assert backend.load_count == 1
        assert backend.is_loaded is True

    def test_transcribe_after_preload_does_not_reload(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        lc.preload()
        wait_until(lambda: lc.is_loaded)

        result = lc.transcribe(AUDIO)
        assert backend.load_count == 1
        assert result == "fake transcription"

    def test_preload_when_already_loaded_is_noop(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        lc.transcribe(AUDIO)
        assert backend.load_count == 1

        lc.preload()  # already resident → synchronous no-op, no thread spawned
        assert backend.load_count == 1

    def test_is_loading_false_before_preload(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert lc.is_loading is False

    def test_is_loading_false_after_preload_completes(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        lc.preload()
        wait_until(lambda: lc.is_loaded)
        assert lc.is_loading is False
        assert lc.is_loaded is True

    def test_preload_sets_last_activity_so_idle_unload_works(self) -> None:
        """A preloaded-but-never-transcribed model must still auto-unload."""
        current_time = 0.0

        def clock() -> float:
            return current_time

        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(
            backend=backend, clock=clock, idle_timeout_s=1800.0
        )
        lc.preload()
        wait_until(lambda: lc.is_loaded)
        assert lc.is_loaded is True

        current_time = 30 * 60
        lc.check_idle()
        assert lc.is_loaded is False


class TestPrefetchToDisk:
    """First-run fetch (ADR-0025 / #162): download the weights to disk without
    loading them into VRAM, best-effort, on a background thread."""

    def test_prefetch_downloads_without_loading(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        lc.prefetch_to_disk()
        wait_until(lambda: not lc.is_downloading)

        assert backend.download_to_disk_count == 1
        assert backend.load_count == 0  # to disk only — never loaded into VRAM
        assert backend.is_loaded is False
        assert lc.last_download_succeeded is True

    def test_is_downloading_true_while_in_flight(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        backend.block_download()
        lc.prefetch_to_disk()
        wait_until(lambda: backend.download_to_disk_count >= 1)
        assert lc.is_downloading is True

        backend.release_download()
        wait_until(lambda: not lc.is_downloading)

    def test_prefetch_failure_is_swallowed(self) -> None:
        backend = FakeTranscriberBackend()
        backend.queue_download_error(RuntimeError("offline"))
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        lc.prefetch_to_disk()  # must not raise
        wait_until(lambda: not lc.is_downloading)

        assert backend.download_to_disk_count == 1
        assert lc.last_download_succeeded is False
        assert backend.is_loaded is False  # a failed fetch loads nothing

    def test_prefetch_noop_when_already_loaded(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        lc.transcribe(AUDIO)  # loads the model
        assert backend.is_loaded is True

        lc.prefetch_to_disk()  # resident → nothing to fetch (synchronous no-op)
        assert lc.is_downloading is False
        assert backend.download_to_disk_count == 0

    def test_prefetch_noop_while_a_load_is_in_flight(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        backend.block_load()
        lc.preload()  # is_loading → a load is already pulling the weights
        wait_until(lambda: backend.load_count >= 1)

        lc.prefetch_to_disk()  # skip — the load downloads anyway
        assert backend.download_to_disk_count == 0

        backend.release_load()
        wait_until(lambda: backend.is_loaded)

    def test_no_double_prefetch_while_in_flight(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        backend.block_download()
        lc.prefetch_to_disk()
        wait_until(lambda: backend.download_to_disk_count >= 1)
        lc.prefetch_to_disk()  # second call while in flight → no-op

        backend.release_download()
        wait_until(lambda: not lc.is_downloading)
        assert backend.download_to_disk_count == 1

    def test_prefetch_does_not_arm_idle_unload(self) -> None:
        """Prefetch leaves nothing resident, so the idle timer has nothing to
        reap and check_idle is a no-op (no spurious unload)."""
        current_time = 0.0

        def clock() -> float:
            return current_time

        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=clock, idle_timeout_s=1800.0)

        lc.prefetch_to_disk()
        wait_until(lambda: not lc.is_downloading)
        assert backend.is_loaded is False

        current_time = 60 * 60  # well past the idle timeout
        lc.check_idle()
        assert backend.unload_count == 0


class TestEmptyResultDetection:
    def test_empty_string(self) -> None:
        backend = FakeTranscriberBackend(result="")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert lc.transcribe(AUDIO) == EmptyResult()

    def test_whitespace_only(self) -> None:
        backend = FakeTranscriberBackend(result="   ")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert lc.transcribe(AUDIO) == EmptyResult()

    def test_punctuation_only(self) -> None:
        backend = FakeTranscriberBackend(result=".,?")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert lc.transcribe(AUDIO) == EmptyResult()

    def test_short_after_stripping(self) -> None:
        backend = FakeTranscriberBackend(result="Hi")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert lc.transcribe(AUDIO) == EmptyResult()

    def test_valid_text_passes_through(self) -> None:
        backend = FakeTranscriberBackend(result="Hello world")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert lc.transcribe(AUDIO) == "Hello world"

    def test_exactly_min_chars_passes(self) -> None:
        backend = FakeTranscriberBackend(result="Yes")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert lc.transcribe(AUDIO) == "Yes"

    def test_backend_empty_result_passes_through(self) -> None:
        backend = FakeTranscriberBackend(result=EmptyResult())
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        assert lc.transcribe(AUDIO) == EmptyResult()


class TestOOMRetry:
    def test_retry_succeeds_after_single_oom(self) -> None:
        backend = FakeTranscriberBackend(result="recovered text")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        backend.queue_error(GPUOutOfMemoryError("VRAM full"))

        result = lc.transcribe(AUDIO)
        assert result == "recovered text"
        assert backend.empty_cache_count == 1
        assert len(backend.transcribe_calls) == 2

    def test_empty_cache_called_between_retries(self) -> None:
        backend = FakeTranscriberBackend(result="ok")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        backend.queue_error(GPUOutOfMemoryError())

        lc.transcribe(AUDIO)
        assert backend.empty_cache_count == 1

    def test_double_oom_raises_transcription_failed(self) -> None:
        backend = FakeTranscriberBackend(result="never returned")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        backend.queue_error(GPUOutOfMemoryError("first"))
        backend.queue_error(GPUOutOfMemoryError("second"))

        with pytest.raises(TranscriptionFailedError):
            lc.transcribe(AUDIO)

    def test_double_oom_error_is_descriptive(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        backend.queue_error(GPUOutOfMemoryError())
        backend.queue_error(GPUOutOfMemoryError())

        with pytest.raises(TranscriptionFailedError, match="out of memory"):
            lc.transcribe(AUDIO)


class TestUnload:
    def test_unload_calls_backend(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        lc.transcribe(AUDIO)
        lc.unload()
        assert backend.is_loaded is False
        assert backend.unload_count == 1

    def test_unload_resets_lazy_state(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        lc.transcribe(AUDIO)
        lc.unload()

        # Next transcribe should trigger reload
        lc.transcribe(AUDIO)
        assert backend.load_count == 2


class TestDownloadProgress:
    def test_progress_callback_fires(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        events: list[tuple[int, int]] = []
        lc.on_download_progress(lambda d, t: events.append((d, t)))

        backend.simulate_progress(500, 1000)
        backend.simulate_progress(1000, 1000)

        assert events == [(500, 1000), (1000, 1000)]

    def test_progress_callback_replaces_previous(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)

        first_events: list[tuple[int, int]] = []
        second_events: list[tuple[int, int]] = []

        lc.on_download_progress(lambda d, t: first_events.append((d, t)))
        lc.on_download_progress(lambda d, t: second_events.append((d, t)))

        backend.simulate_progress(100, 200)

        assert first_events == []
        assert second_events == [(100, 200)]


class TestImportSafety:
    def test_lifecycle_has_no_faster_whisper_import(self) -> None:
        import importlib
        import sys

        before = set(sys.modules.keys())
        importlib.import_module("dictatem.transcribe.lifecycle")
        after = set(sys.modules.keys())
        new_modules = after - before

        for forbidden in ("faster_whisper", "ctranslate2"):
            violations = [
                m for m in new_modules if m == forbidden or m.startswith(forbidden + ".")
            ]
            assert violations == [], (
                f"lifecycle.py pulled in forbidden module(s): {violations}"
            )


class TestUnloadDuringTranscription:
    """F-7 / #236: an unload never pulls the model out from under an in-flight
    transcription; it is deferred and runs once the transcription finishes."""

    @staticmethod
    def _start_blocked_transcription(
        lc: TranscribeLifecycle, backend: FakeTranscriberBackend
    ) -> tuple[threading.Thread, list[TranscriptionResult]]:
        results: list[TranscriptionResult] = []
        backend.block_transcribe()
        thread = threading.Thread(
            target=lambda: results.append(lc.transcribe(AUDIO)), daemon=True
        )
        thread.start()
        wait_until(lambda: len(backend.transcribe_calls) >= 1)
        return thread, results

    def test_explicit_unload_is_deferred_until_transcription_completes(
        self,
    ) -> None:
        backend = FakeTranscriberBackend(result="hello world")
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        thread, results = self._start_blocked_transcription(lc, backend)

        lc.unload()  # the tray "Unload model" click, mid-transcription
        assert backend.is_loaded is True
        assert backend.unload_count == 0

        backend.release_transcribe()
        thread.join(timeout=2.0)

        assert results == ["hello world"]
        assert backend.is_loaded is False
        assert backend.unload_count == 1

    def test_idle_unload_is_deferred_until_after_transcription(self) -> None:
        now = [0.0]
        backend = FakeTranscriberBackend(result="hello world")
        lc = TranscribeLifecycle(
            backend=backend, clock=lambda: now[0], idle_timeout_s=1800.0
        )
        lc.transcribe(AUDIO)  # model resident, last activity at t=0
        thread, results = self._start_blocked_transcription(lc, backend)

        now[0] = 30 * 60  # the idle deadline arrives mid-transcription
        lc.check_idle()
        assert backend.is_loaded is True

        backend.release_transcribe()
        thread.join(timeout=2.0)
        assert results == ["hello world"]
        assert backend.is_loaded is True  # idle restarts from the end

        now[0] = 60 * 60  # a full idle period after the transcription ended
        lc.check_idle()
        assert backend.is_loaded is False
        assert backend.unload_count == 1

    def test_long_transcription_does_not_unload_immediately_on_return(
        self,
    ) -> None:
        now = [0.0]
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(
            backend=backend, clock=lambda: now[0], idle_timeout_s=1800.0
        )
        thread, _ = self._start_blocked_transcription(lc, backend)

        now[0] = 45 * 60  # transcribing well past the idle threshold
        backend.release_transcribe()
        thread.join(timeout=2.0)

        lc.check_idle()
        assert backend.is_loaded is True

        now[0] = 45 * 60 + 29 * 60
        lc.check_idle()
        assert backend.is_loaded is True

        now[0] = 45 * 60 + 30 * 60
        lc.check_idle()
        assert backend.is_loaded is False

    def test_load_after_pending_unload_keeps_model_resident(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        thread, _ = self._start_blocked_transcription(lc, backend)

        lc.unload()  # deferred
        lc.preload()  # a new load (e.g. load-on-arm) supersedes it

        backend.release_transcribe()
        thread.join(timeout=2.0)

        assert backend.is_loaded is True
        assert backend.unload_count == 0

    def test_deferred_unload_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        thread, _ = self._start_blocked_transcription(lc, backend)

        with caplog.at_level("INFO", logger="dictatem.transcribe.lifecycle"):
            lc.unload()
        assert any("deferred" in r.getMessage().lower() for r in caplog.records)

        backend.release_transcribe()
        thread.join(timeout=2.0)

    def test_failed_transcription_still_runs_deferred_unload(self) -> None:
        backend = FakeTranscriberBackend()
        lc = TranscribeLifecycle(backend=backend, clock=lambda: 0.0)
        backend.queue_error(GPUOutOfMemoryError())
        backend.queue_error(GPUOutOfMemoryError())
        errors: list[BaseException] = []

        def run() -> None:
            try:
                lc.transcribe(AUDIO)
            except TranscriptionFailedError as exc:
                errors.append(exc)

        backend.block_transcribe()
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        wait_until(lambda: len(backend.transcribe_calls) >= 1)

        lc.unload()
        backend.release_transcribe()
        thread.join(timeout=2.0)

        assert len(errors) == 1
        assert backend.is_loaded is False
        assert backend.unload_count == 1
