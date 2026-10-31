"""FallbackTranscriber — the MLX session fallback composite (#232 / spec #224).

Pure and protocol-level: tested around ``FakeTranscriberBackend`` only. The
composite wraps a primary backend (MLX in production) and a lazily-built
fallback (the Apple-Silicon-row faster-whisper backend). A primary failure
latches the fallback for the rest of the session and re-runs the same audio
there, so the dictation is never lost.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from dictatem.exceptions import ModelLoadError
from dictatem.transcribe.fallback import FallbackTranscriber
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.types import Transcript
from tests.fakes import FakeTranscriberBackend

AUDIO = np.arange(16000, dtype=np.float32)


def test_primary_load_failure_transcribes_the_same_audio_on_the_fallback() -> None:
    primary = FakeTranscriberBackend(result="from mlx")
    primary.fail_load_always(RuntimeError("Metal device not found"))
    fallback = FakeTranscriberBackend(result="from cpu")
    composite = FallbackTranscriber(primary=primary, fallback_factory=lambda: fallback)

    composite.load_model()
    result = composite.transcribe(AUDIO)

    assert result == Transcript("from cpu")
    assert composite.is_loaded is True
    assert len(fallback.transcribe_calls) == 1
    assert fallback.transcribe_calls[0] is AUDIO
    assert primary.transcribe_calls == []


def _failing_primary() -> FakeTranscriberBackend:
    primary = FakeTranscriberBackend(result="from mlx")
    primary.fail_load_always(RuntimeError("Metal device not found"))
    return primary


class _CountingFactory:
    def __init__(self, result: str = "from cpu") -> None:
        self.built: list[FakeTranscriberBackend] = []
        self._result = result

    def __call__(self) -> FakeTranscriberBackend:
        backend = FakeTranscriberBackend(result=self._result)
        self.built.append(backend)
        return backend


def test_callback_fires_exactly_once_across_the_session() -> None:
    calls: list[str] = []
    composite = FallbackTranscriber(
        primary=_failing_primary(),
        fallback_factory=_CountingFactory(),
        on_fallback=calls.append,
    )

    for _ in range(3):
        composite.load_model()
        composite.transcribe(AUDIO)
        composite.unload_model()

    assert calls == ["mlx-load-failed"]


def test_primary_is_never_retried_after_falling_back() -> None:
    primary = _failing_primary()
    factory = _CountingFactory()
    composite = FallbackTranscriber(primary=primary, fallback_factory=factory)

    composite.load_model()
    composite.unload_model()
    composite.load_model()
    composite.transcribe(AUDIO)
    composite.download_to_disk()

    assert primary.load_count == 1
    assert primary.transcribe_calls == []
    assert primary.download_to_disk_count == 0
    assert len(factory.built) == 1
    assert factory.built[0].load_count == 2


def test_fallback_factory_is_not_invoked_on_the_happy_path() -> None:
    primary = FakeTranscriberBackend(result="from mlx")
    factory = _CountingFactory()
    calls: list[str] = []
    composite = FallbackTranscriber(
        primary=primary, fallback_factory=factory, on_fallback=calls.append
    )

    composite.download_to_disk()
    composite.load_model()
    assert composite.transcribe(AUDIO) == Transcript("from mlx")
    composite.unload_model()

    assert factory.built == []
    assert calls == []
    assert composite.fell_back is False


def test_lifecycle_calls_delegate_to_the_primary_before_any_failure() -> None:
    primary = FakeTranscriberBackend()
    composite = FallbackTranscriber(primary=primary, fallback_factory=_CountingFactory())

    composite.download_to_disk()
    assert primary.download_to_disk_count == 1
    composite.load_model()
    assert primary.is_loaded and composite.is_loaded
    composite.empty_cache()
    assert primary.empty_cache_count == 1
    composite.unload_model()
    assert primary.unload_count == 1
    assert composite.is_loaded is False


def test_lifecycle_calls_delegate_to_the_fallback_after_falling_back() -> None:
    factory = _CountingFactory()
    composite = FallbackTranscriber(primary=_failing_primary(), fallback_factory=factory)
    composite.load_model()
    fallback = factory.built[0]

    assert composite.is_loaded is True
    composite.empty_cache()
    assert fallback.empty_cache_count == 1
    composite.unload_model()
    assert fallback.unload_count == 1
    assert composite.is_loaded is False
    composite.download_to_disk()
    assert fallback.download_to_disk_count == 1
    assert composite.is_loaded is False


def test_a_transcribe_time_failure_reruns_the_same_audio_on_the_fallback() -> None:
    primary = FakeTranscriberBackend(result="from mlx")
    primary.queue_error(RuntimeError("[metal] command buffer failed"))
    factory = _CountingFactory()
    calls: list[str] = []
    composite = FallbackTranscriber(
        primary=primary, fallback_factory=factory, on_fallback=calls.append
    )
    composite.load_model()

    assert composite.transcribe(AUDIO) == Transcript("from cpu")
    assert factory.built[0].transcribe_calls[0] is AUDIO
    assert primary.is_loaded is False  # the failed engine's memory is released
    assert calls == ["mlx-transcribe-failed"]


def test_a_failing_fallback_raises_the_fallback_error() -> None:
    fallback = FakeTranscriberBackend()
    fallback.fail_load_always(OSError("CPU model download failed"))
    composite = FallbackTranscriber(primary=_failing_primary(), fallback_factory=lambda: fallback)

    with pytest.raises(OSError, match="CPU model download failed"):
        composite.load_model()
    # Still latched: the next attempt goes to the fallback, never the primary.
    with pytest.raises(OSError, match="CPU model download failed"):
        composite.load_model()
    assert composite.fell_back is True


def test_a_failing_fallback_surfaces_as_todays_transcription_failure_via_lifecycle() -> None:
    fallback = FakeTranscriberBackend()
    fallback.fail_load_always(ModelLoadError("CPU model unavailable"))
    lifecycle = TranscribeLifecycle(
        backend=FallbackTranscriber(primary=_failing_primary(), fallback_factory=lambda: fallback),
        clock=lambda: 0.0,
    )

    with pytest.raises(ModelLoadError):
        lifecycle.transcribe(AUDIO)


def test_a_raising_callback_does_not_lose_the_dictation() -> None:
    def boom(_reason: str) -> None:
        raise RuntimeError("tray gone")

    composite = FallbackTranscriber(
        primary=_failing_primary(), fallback_factory=_CountingFactory(), on_fallback=boom
    )

    composite.load_model()
    assert composite.transcribe(AUDIO) == Transcript("from cpu")


def test_progress_callback_reaches_the_fallback_built_later() -> None:
    factory = _CountingFactory()
    composite = FallbackTranscriber(primary=_failing_primary(), fallback_factory=factory)
    seen: list[tuple[int, int]] = []
    composite.set_progress_callback(lambda done, total: seen.append((done, total)))

    composite.load_model()
    factory.built[0].simulate_progress(5, 10)

    assert seen == [(5, 10)]


def test_the_cause_is_logged_once_as_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    composite = FallbackTranscriber(
        primary=_failing_primary(), fallback_factory=_CountingFactory()
    )
    with caplog.at_level(logging.WARNING, logger="dictatem.transcribe.fallback"):
        composite.load_model()
        composite.unload_model()
        composite.load_model()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Metal device not found" in warnings[0].getMessage()


class _RaisingFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> FakeTranscriberBackend:
        self.calls += 1
        raise ImportError("faster_whisper missing")


def test_a_raising_factory_latches_and_never_retries_the_primary() -> None:
    primary = _failing_primary()
    factory = _RaisingFactory()
    reasons: list[str] = []
    composite = FallbackTranscriber(
        primary=primary, fallback_factory=factory, on_fallback=reasons.append
    )

    with pytest.raises(ImportError, match="faster_whisper missing"):
        composite.load_model()
    with pytest.raises(ImportError, match="faster_whisper missing"):
        composite.load_model()
    with pytest.raises(ImportError, match="faster_whisper missing"):
        composite.transcribe(AUDIO)

    assert primary.load_count == 1
    assert primary.transcribe_calls == []
    assert composite.fell_back is True
    assert composite.is_loaded is False
    assert reasons == ["mlx-load-failed"]


def test_a_raising_factory_surfaces_as_todays_transcription_failure_via_lifecycle() -> None:
    lifecycle = TranscribeLifecycle(
        backend=FallbackTranscriber(
            primary=_failing_primary(), fallback_factory=_RaisingFactory()
        ),
        clock=lambda: 0.0,
    )

    # Today's failure since the load-failure classifier (#225): the lifecycle
    # wraps the raw error in an (UNKNOWN-diagnosis) ModelLoadError.
    with pytest.raises(ModelLoadError) as excinfo:
        lifecycle.transcribe(AUDIO)
    assert isinstance(excinfo.value.__cause__, ImportError)


# --- The confirm pass (#249): transcribe_command falls back the same way ---

TRIGGER_WORDS = ("summarize", "paste")


def test_transcribe_command_delegates_to_the_primary_on_the_happy_path() -> None:
    primary = FakeTranscriberBackend(result="from mlx")
    factory = _CountingFactory()
    composite = FallbackTranscriber(primary=primary, fallback_factory=factory)
    composite.load_model()

    assert composite.transcribe_command(AUDIO, TRIGGER_WORDS) == Transcript("from mlx")
    assert primary.command_calls == [(AUDIO, TRIGGER_WORDS)]
    assert factory.built == []
    assert composite.fell_back is False


def test_transcribe_command_after_a_load_failure_runs_on_the_fallback() -> None:
    primary = _failing_primary()
    factory = _CountingFactory()
    composite = FallbackTranscriber(primary=primary, fallback_factory=factory)
    composite.load_model()

    assert composite.transcribe_command(AUDIO, TRIGGER_WORDS) == Transcript("from cpu")
    assert primary.command_calls == []
    assert factory.built[0].command_calls == [(AUDIO, TRIGGER_WORDS)]


def test_a_command_pass_failure_reruns_the_same_audio_and_words_on_the_fallback() -> None:
    primary = FakeTranscriberBackend(result="from mlx")
    primary.queue_error(RuntimeError("[metal] command buffer failed"))
    factory = _CountingFactory()
    reasons: list[str] = []
    composite = FallbackTranscriber(
        primary=primary, fallback_factory=factory, on_fallback=reasons.append
    )
    composite.load_model()

    assert composite.transcribe_command(AUDIO, TRIGGER_WORDS) == Transcript("from cpu")
    fallback = factory.built[0]
    assert len(fallback.command_calls) == 1
    audio, words = fallback.command_calls[0]
    assert audio is AUDIO
    assert words == TRIGGER_WORDS
    assert primary.is_loaded is False  # the failed engine's memory is released
    assert reasons == ["mlx-transcribe-failed"]

    # Latched for the session: regular dictation now runs on the fallback too.
    assert composite.transcribe(AUDIO) == Transcript("from cpu")
    assert primary.transcribe_calls == []


def test_a_transcribe_failure_latches_the_command_pass_onto_the_fallback() -> None:
    primary = FakeTranscriberBackend(result="from mlx")
    primary.queue_error(RuntimeError("[metal] command buffer failed"))
    factory = _CountingFactory()
    composite = FallbackTranscriber(primary=primary, fallback_factory=factory)
    composite.load_model()
    composite.transcribe(AUDIO)

    composite.transcribe_command(AUDIO, TRIGGER_WORDS)

    assert primary.command_calls == []
    assert factory.built[0].command_calls == [(AUDIO, TRIGGER_WORDS)]


def test_a_raising_factory_on_the_command_pass_surfaces_and_stays_latched() -> None:
    primary = FakeTranscriberBackend(result="from mlx")
    primary.queue_error(RuntimeError("[metal] command buffer failed"))
    factory = _RaisingFactory()
    composite = FallbackTranscriber(primary=primary, fallback_factory=factory)
    composite.load_model()

    with pytest.raises(ImportError, match="faster_whisper missing"):
        composite.transcribe_command(AUDIO, TRIGGER_WORDS)
    with pytest.raises(ImportError, match="faster_whisper missing"):
        composite.transcribe_command(AUDIO, TRIGGER_WORDS)

    assert len(primary.command_calls) == 1
    assert composite.fell_back is True
