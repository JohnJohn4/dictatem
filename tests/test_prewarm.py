"""Engine prewarm (ADR-0029): when it runs, how it spawns, and that it never raises."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dictatem.config import StartupConfig
from dictatem.transcribe.prewarm import (
    PREWARM_MODULE,
    nvidia_dll_paths,
    should_prewarm,
    start_prewarm,
)


def test_prewarm_is_on_by_default() -> None:
    assert StartupConfig().prewarm_engine is True


@pytest.mark.parametrize("kind", ["cuda", "cpu"])
def test_prewarms_faster_whisper_on_windows(kind: str) -> None:
    assert should_prewarm(
        platform="win32", backend_kind=kind, enabled=True, preload_model=False
    )


@pytest.mark.parametrize(
    ("platform", "kind", "enabled", "preload"),
    [
        ("darwin", "mlx", True, False),  # macOS / MLX: not the target
        ("darwin", "cpu", True, False),
        ("linux", "cuda", True, False),
        ("win32", "cuda", False, False),  # user turned it off
        ("win32", "cuda", True, True),  # preload_model loads the real model anyway
    ],
)
def test_skips_prewarm(platform: str, kind: str, enabled: bool, preload: bool) -> None:
    assert not should_prewarm(
        platform=platform, backend_kind=kind, enabled=enabled, preload_model=preload
    )


class _Proc:
    def __init__(self, code: int) -> None:
        self.code = code

    def wait(self) -> int:
        return self.code


def test_spawns_a_quiet_low_priority_child_and_logs_the_outcome(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    ticks = iter([10.0, 12.5])

    def spawn(cmd: list[str], **kwargs: Any) -> _Proc:
        calls.append((cmd, kwargs))
        return _Proc(0)

    with caplog.at_level(logging.INFO, logger="dictatem"):
        watcher = start_prewarm(
            executable="pythonw.exe", spawn=spawn, clock=lambda: next(ticks)
        )
        assert watcher is not None
        watcher.join(timeout=5)

    (cmd, kwargs), = calls
    assert cmd == ["pythonw.exe", "-m", PREWARM_MODULE]
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["creationflags"] & 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
    assert kwargs["creationflags"] & 0x08000000  # CREATE_NO_WINDOW
    assert "Engine prewarm finished in 2.5s (exit 0)" in caplog.text


def test_a_failed_spawn_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    def spawn(cmd: list[str], **kwargs: Any) -> _Proc:
        raise OSError("no such file")

    with caplog.at_level(logging.WARNING, logger="dictatem"):
        assert start_prewarm(executable="missing.exe", spawn=spawn) is None

    assert "Engine prewarm could not start" in caplog.text


def test_nvidia_dll_paths_lists_only_dlls(tmp_path: Path) -> None:
    cublas = tmp_path / "cublas" / "bin"
    cublas.mkdir(parents=True)
    (cublas / "cublas64_12.dll").write_bytes(b"")
    (cublas / "cublasLt64_12.DLL").write_bytes(b"")
    (cublas / "readme.txt").write_text("")

    paths = nvidia_dll_paths([str(cublas), str(tmp_path / "missing")])

    assert [Path(p).name for p in paths] == ["cublas64_12.dll", "cublasLt64_12.DLL"]
