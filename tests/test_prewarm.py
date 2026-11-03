"""Engine prewarm (ADR-0029): when it runs, how it spawns, and that it never raises."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from dictatem.config import StartupConfig
from dictatem.transcribe.prewarm import (
    PREWARM_MODULE,
    nvidia_dll_paths,
    should_prewarm,
    start_prewarm,
)

if TYPE_CHECKING:
    from dictatem.transcribe.backend_selection import BackendKind


def test_prewarm_is_on_by_default() -> None:
    assert StartupConfig().prewarm_engine is True


def test_prewarms_faster_whisper_on_windows() -> None:
    assert should_prewarm(
        platform="win32", backend_kind="faster-whisper", enabled=True, preload_model=False
    )


def test_prewarm_gate_matches_the_real_backend_selection() -> None:
    # Regression: the gate once compared against device names ("cuda"/"cpu")
    # instead of the BackendKind, so it never fired in the daemon.
    from dictatem.transcribe.backend_selection import select_backend
    from dictatem.types import ResolvedHardware

    for device in ("cuda", "cpu"):
        selection = select_backend(
            ResolvedHardware(
                tier="t", model="small", device=device, compute_type="int8",
                transform_model="x",
            )
        )
        assert should_prewarm(
            platform="win32",
            backend_kind=selection.kind,
            enabled=True,
            preload_model=False,
        ), device


@pytest.mark.parametrize(
    ("platform", "kind", "enabled", "preload"),
    [
        ("darwin", "mlx", True, False),  # macOS / MLX: not the target
        ("darwin", "faster-whisper", True, False),
        ("linux", "faster-whisper", True, False),
        ("win32", "mlx", True, False),
        ("win32", "faster-whisper", False, False),  # user turned it off
        ("win32", "faster-whisper", True, True),  # preload_model loads the model anyway
    ],
)
def test_skips_prewarm(
    platform: str, kind: BackendKind, enabled: bool, preload: bool
) -> None:
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


def test_installer_prewarms_before_launching_the_daemon() -> None:
    # The install-time prewarm must finish before the tray appears, so a user
    # can't start dictating into a half-scanned engine.
    script = (Path(__file__).resolve().parents[1] / "install.ps1").read_text(encoding="utf-8")
    prewarm = script.index(f"-m {PREWARM_MODULE}")
    launch = script.index("Start-Process -FilePath 'dictatem'")
    assert prewarm < launch


def test_a_slow_prewarm_leaves_the_scanner_marker(tmp_path: Path) -> None:
    from dictatem.transcribe.prewarm import (
        SLOW_PREWARM_S,
        record_prewarm_duration,
        slow_engine_marker,
    )

    marker = slow_engine_marker(tmp_path)
    assert record_prewarm_duration(SLOW_PREWARM_S - 0.1, marker) is False
    assert not marker.exists()
    assert record_prewarm_duration(SLOW_PREWARM_S + 30, marker) is True
    assert marker.exists()


@pytest.mark.parametrize(
    ("mode", "marker", "expected"),
    [
        ("auto", False, False),  # normal machine: stay light
        ("auto", True, True),  # scanner detected: keep the engine resident
        ("on", False, True),
        ("off", True, False),
        ("bogus", True, True),  # unknown acts like auto
    ],
)
def test_resident_engine_decision(mode: str, marker: bool, expected: bool) -> None:
    from dictatem.transcribe.prewarm import wants_resident_engine

    assert wants_resident_engine(mode, marker_exists=marker) is expected


def test_resident_engine_defaults_to_auto() -> None:
    assert StartupConfig().resident_engine == "auto"


def test_on_done_runs_after_the_child_exits() -> None:
    order: list[str] = []

    class _P:
        def wait(self) -> int:
            order.append("exited")
            return 0

    watcher = start_prewarm(
        executable="pythonw.exe",
        spawn=lambda *a, **k: _P(),
        on_done=lambda: order.append("on_done"),
    )
    assert watcher is not None
    watcher.join(timeout=5)
    assert order == ["exited", "on_done"]
