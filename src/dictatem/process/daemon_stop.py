"""Pure daemon-process matcher for a clean stop (#69).

`dictatem --uninstall` (and the tray Upgrade) must terminate the running daemon
before `uv tool uninstall`/`uv tool install` can touch
``…\\uv\\tools\\dictatem\\Scripts``: Windows refuses to delete a directory whose
interpreter is loaded, so the step otherwise fails with
``Access is denied. (os error 5)`` (reproduced on a managed laptop, #69).

The *decision* — given a snapshot of running processes and where Dictatem is
installed, which PIDs are daemons safe to terminate — is pure logic with no OS
calls, so the full match table is unit-testable on any OS. The win32 adapter
(``win32_stopper``) supplies the snapshot and terminates the matches; this module
is the testable core, mirroring ``autostart.reconcile``.

Matching is by **full executable path**, never PID: a process matches when its
exe lives under the uv tools dictatem dir (the ``Scripts`` interpreter that holds
the lock) or equals the ``~/.local/bin/dictatem(.exe)`` trampoline. Path matching
sidesteps any PID-recycling risk, and the invoking process (``os.getpid()``) is
always excluded so a clean-stop never terminates itself mid-flight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class ProcessInfo:
    """One running process from the OS snapshot.

    *exe_path* is the process's full executable path, or ``""`` when the adapter
    could not read it (e.g. access denied for a process owned by another user) —
    an unreadable path never matches.
    """

    pid: int
    exe_path: str


def _normalize(path: str) -> str:
    """Lower-case, forward-slash, trailing-slash-stripped form for comparison.

    Windows (and default macOS APFS/HFS+) filesystems are case-insensitive and
    accept either separator, so we compare on a single canonical form rather than
    the raw OS string.
    """
    return path.replace("\\", "/").rstrip("/").lower()


def is_path_under(path: str, parent: str) -> bool:
    """True when *path* sits strictly inside directory *parent*.

    Case-insensitive and separator-agnostic (see :func:`_normalize`). A bare
    prefix is not enough — ``…/dictatem-old`` is not under ``…/dictatem`` — so the
    match requires *parent* followed by a path separator. The directory itself is
    not "under" itself (a directory is never a running process), and an empty
    *path* never matches.
    """
    if not path:
        return False
    norm_path = _normalize(path)
    norm_parent = _normalize(parent)
    if not norm_parent:
        return False
    return norm_path.startswith(norm_parent + "/")


def pids_to_stop(
    processes: Iterable[ProcessInfo],
    *,
    self_pid: int,
    tool_dir: str,
    extra_exes: tuple[str, ...] = (),
) -> list[int]:
    """PIDs of running Dictatem daemons to terminate, excluding *self_pid*.

    A process matches when its executable lives under *tool_dir* (the uv tools
    dictatem dir whose ``Scripts`` interpreter holds the lock) or equals one of
    *extra_exes* (the ``~/.local/bin/dictatem(.exe)`` trampoline — an exact path
    match, so a different uv tool in the same bin dir is not caught). *self_pid*
    is always excluded so the invoking ``--uninstall``/daemon process is never
    terminated. Input order is preserved.
    """
    extra_normalized = {_normalize(exe) for exe in extra_exes if exe}
    matched: list[int] = []
    for proc in processes:
        if proc.pid == self_pid or not proc.exe_path:
            continue
        if is_path_under(proc.exe_path, tool_dir) or (
            _normalize(proc.exe_path) in extra_normalized
        ):
            matched.append(proc.pid)
    return matched
