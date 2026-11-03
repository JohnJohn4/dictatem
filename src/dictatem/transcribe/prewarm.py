"""Engine prewarm: load the transcription DLLs once, in a throwaway child process.

Why (work-laptop QA, 2026-11-02, ADR-0029): under an endpoint scanner (Microsoft
Defender for Endpoint) the first load of each newly seen engine DLL is scanned
before it maps. In-process, that cost lands on the first dictation: 17-46 s
importing faster-whisper/CTranslate2 and 36-74 s in the first transcribe, when
cuBLAS/cuDNN load lazily. While it happens the daemon's own threads stall: the
pill appears late and the audio callback overflows, so audio gets lost. The
scan verdict is cached per file, so once *any* process has loaded a DLL, the
next load is fast.

So shortly after launch the daemon spawns ``python -m dictatem.transcribe.prewarm``
at below-normal priority. The child imports faster-whisper (which pulls in the
CTranslate2, ONNX Runtime and PyAV DLL trees) and loads every DLL in the NVIDIA
wheels' ``bin`` directories, then exits. It touches no GPU memory, loads no
model and makes no network call, so ADR-0025's "no model in VRAM at launch"
still holds. On a machine without such a scanner it only pulls the files into
the OS cache (a second or two of background disk reads), which also helps the
first dictation.

The parent never waits on it. If it fails, nothing changes except the log line.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

PREWARM_MODULE = "dictatem.transcribe.prewarm"

# Windows process-creation flags (subprocess exposes them only on win32).
_CREATE_NO_WINDOW = 0x08000000
_BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


def should_prewarm(
    *, platform: str, backend_kind: str, enabled: bool, preload_model: bool
) -> bool:
    """Whether to spawn the prewarm child on this launch.

    Windows only (the scanner cost it targets is a Windows one) and only for
    the faster-whisper engine (``cuda`` / ``cpu``; MLX is macOS). Skipped when
    the user opted into ``preload_model``, which loads the real model at
    launch anyway.
    """
    return (
        enabled
        and not preload_model
        and platform == "win32"
        and backend_kind in ("cuda", "cpu")
    )


def prewarm_command(executable: str) -> list[str]:
    return [executable, "-m", PREWARM_MODULE]


def start_prewarm(
    *,
    executable: str = sys.executable,
    spawn: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    clock: Callable[[], float] = time.monotonic,
) -> threading.Thread | None:
    """Spawn the prewarm child and log its outcome from a daemon thread.

    Returns the watcher thread, or ``None`` if the spawn failed (logged, never
    raised: a failed prewarm must not affect the daemon).
    """
    started = clock()
    try:
        proc = spawn(
            prewarm_command(executable),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW | _BELOW_NORMAL_PRIORITY_CLASS,
        )
    except Exception:
        logger.warning("Engine prewarm could not start", exc_info=True)
        return None

    def _watch() -> None:
        try:
            code = proc.wait()
        except Exception:
            logger.warning("Engine prewarm wait failed", exc_info=True)
            return
        logger.info("Engine prewarm finished in %.1fs (exit %s)", clock() - started, code)

    watcher = threading.Thread(target=_watch, name="dictatem-prewarm", daemon=True)
    watcher.start()
    logger.info("Engine prewarm started in the background")
    return watcher


def nvidia_dll_paths(bin_dirs: Sequence[str]) -> list[str]:
    """Every ``*.dll`` in the given NVIDIA wheel ``bin`` directories, sorted."""
    paths: list[str] = []
    for directory in bin_dirs:
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        paths.extend(
            os.path.join(directory, n) for n in sorted(names) if n.lower().endswith(".dll")
        )
    return paths


def _nvidia_bin_dirs() -> list[str]:
    try:
        import nvidia  # type: ignore[import-not-found]
    except ImportError:
        return []
    dirs: list[str] = []
    for base in nvidia.__path__:
        try:
            entries = os.listdir(base)
        except OSError:
            continue
        for entry in entries:
            candidate = os.path.join(base, entry, "bin")
            if os.path.isdir(candidate):
                dirs.append(candidate)
    return dirs


def main() -> int:  # pragma: no cover - native; exercised by manual QA
    """Child entry point: load the engine's DLLs, then exit."""
    from dictatem.transcribe.faster_whisper_backend import _register_cuda_dll_directories

    _register_cuda_dll_directories()
    import faster_whisper  # type: ignore[import-not-found]  # noqa: F401

    if sys.platform == "win32":
        import ctypes

        for path in nvidia_dll_paths(_nvidia_bin_dirs()):
            # A DLL whose dependencies can't resolve on this machine is still
            # read (and scanned) by the attempt; nothing more to do.
            with contextlib.suppress(OSError):
                ctypes.WinDLL(path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
