"""Proving tests for the v0.7.0 bug hunt, transcription.

See docs/reviews/2026-11-02-v0.7.0-bug-hunt.md. Each test asserts the intended
behaviour and fails on v0.7.0, so it is marked ``xfail(strict=True)`` with the
finding it proves; a fix flips it to XPASS and the strict marker forces removal.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import numpy as np
import pytest

from dictatem.exceptions import ModelLoadError
from dictatem.transcribe.fallback import FallbackTranscriber
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from tests.fakes import FakeTranscriberBackend
from tests.support import wait_until

AUDIO = np.zeros(16000, dtype=np.float32)


@pytest.mark.xfail(strict=True, reason="bug-hunt M-5: a partial MLX snapshot in the HF cache is returned as-is and never re-fetched")  # noqa: E501
def test_mlx_partial_snapshot_is_refetched_not_returned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted first-run MLX fetch leaves refs/main + a partial snapshot.

    huggingface_hub's local_files_only lookup returns that folder without
    checking the files ("we can't check if all the files are actually there"),
    so _local_snapshot never goes online again: every launch MLX fails to load
    (weights missing) and the session falls back to CPU, forever.
    """
    import huggingface_hub

    from dictatem.transcribe import mlx_backend

    repo = "mlx-community/whisper-small-mlx"
    commit = "a" * 40
    storage = tmp_path / "models--mlx-community--whisper-small-mlx"
    (storage / "refs").mkdir(parents=True)
    (storage / "refs" / "main").write_text(commit)
    snap = storage / "snapshots" / commit
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")  # weights.npz never arrived

    real = huggingface_hub.snapshot_download
    online_calls: list[str] = []

    def fake_snapshot_download(repo_id: str, **kwargs: object) -> str:
        if kwargs.get("local_files_only"):
            return real(repo_id, cache_dir=str(tmp_path), **kwargs)  # type: ignore[arg-type]
        online_calls.append(repo_id)
        return str(snap)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)

    mlx_backend._local_snapshot(repo)

    assert online_calls == [repo], "partial snapshot was returned as if complete"


@pytest.mark.xfail(strict=True, reason="bug-hunt L-5: a stale _last_activity after a failed load idle-unloads the next preload")  # noqa: E501
def test_preload_after_failed_load_is_not_immediately_idle_unloaded() -> None:
    """A failed load stamps _last_activity; a later load-on-arm keeps that stale stamp.

    Offline dictation fails at T0 -> _finish_transcription sets _last_activity=T0.
    40 min later the user arms dictation; the preload succeeds but
    _background_load only sets _last_activity when it is None, so the next
    5 s idle tick unloads the model the user is about to use.
    """
    now = 0.0

    def clock() -> float:
        return now

    backend = FakeTranscriberBackend()
    backend.queue_load_error(OSError("offline"))
    lc = TranscribeLifecycle(backend=backend, clock=clock, idle_timeout_s=1800.0)
    with pytest.raises(ModelLoadError):
        lc.transcribe(AUDIO)
    assert backend.is_loaded is False

    now = 40 * 60.0
    lc.preload()  # load-on-arm
    wait_until(lambda: backend.is_loaded and not lc.is_loading)

    lc.check_idle()  # the 5 s silence tick, while the user is still talking
    assert backend.is_loaded is True, "freshly preloaded model was idle-unloaded"


@pytest.mark.xfail(strict=True, reason="bug-hunt L-6: the CPU-fallback load mid-transcribe escapes ModelLoadError classification")  # noqa: E501
def test_fallback_load_failure_mid_transcribe_is_a_classified_model_error() -> None:
    """MLX fails mid-transcribe; the CPU fallback's weights aren't cached (ADR-0013:
    not prefetched) and the machine is offline. The fallback's load_model runs
    inside FallbackTranscriber.transcribe, outside the lifecycle's load wrapper,
    so the raw error escapes: the daemon shows the generic "Transcription Error"
    instead of the actionable "Model Download Failed" diagnosis.
    """

    class LocalEntryNotFoundError(Exception):  # huggingface_hub's name
        pass

    primary = FakeTranscriberBackend(result="from mlx")
    primary.queue_error(RuntimeError("[METAL] Command buffer execution failed"))
    fallback = FakeTranscriberBackend(result="from cpu")
    fallback.fail_load_always(LocalEntryNotFoundError("not cached, offline"))
    composite = FallbackTranscriber(primary=primary, fallback_factory=lambda: fallback)
    lc = TranscribeLifecycle(backend=composite, clock=lambda: 0.0, device="mlx")

    with pytest.raises(ModelLoadError):
        lc.transcribe(AUDIO)
