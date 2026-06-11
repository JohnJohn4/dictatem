"""Pure daemon-process matcher for a clean stop (#69).

`dictatem --uninstall` (and the tray Upgrade) must terminate the running daemon
before `uv tool uninstall`/`uv tool install` can touch
``…\\uv\\tools\\dictatem\\Scripts``: Windows refuses to delete a directory whose
interpreter is loaded, so the step otherwise fails with
``Access is denied. (os error 5)`` (reproduced on a managed laptop, #69).

The *decision* — given a snapshot of running processes and where Dictatem is
installed, which PIDs are the daemon's processes safe to terminate — is pure logic
with no OS calls, so the full match table is unit-testable on any OS. The win32
adapter (``win32_stopper``) supplies the snapshot (via WMI) and terminates the
matches; this module is the testable core, mirroring ``autostart.reconcile``.

**Why a tree walk, not just a path match.** The uv gui-script launcher under
``…\\Scripts\\pythonw.exe`` re-execs the *base* CPython as a child (the two
``pythonw.exe`` of #43), and **that child is the real daemon** — its exe lives
*outside* the tool dir (e.g. ``…\\Python313\\pythonw.exe``), so path-matching
alone would orphan it: the daemon survives, keeps the tool-env DLLs loaded, and
``uv tool uninstall`` still fails with ``Access is denied``. So we path-match the
*roots* (exe under the tool dir, or the ``~/.local/bin/dictatem(.exe)``
trampoline) and then walk root→descendants, exactly like ``install.ps1``'s
``Stop-DictatemDaemon``. The invoking process (``os.getpid()``) is always
excluded so a clean-stop never terminates itself mid-flight.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class ProcessInfo:
    """One running process from the OS snapshot.

    *exe_path* is the full executable path, or ``""`` when the adapter could not
    read it. *parent_pid* enables the root→descendant walk. *create_time* is an
    opaque, lexicographically-orderable timestamp (the WMI ``CreationDate``
    string) used only to reject a recycled parent PID — a genuine child cannot
    predate its parent; ``None`` disables that guard for the process.
    """

    pid: int
    parent_pid: int
    exe_path: str
    create_time: str | None = None


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
    trampolines: tuple[str, ...] = (),
) -> list[int]:
    """PIDs of the running Dictatem daemon to terminate, excluding *self_pid*.

    A process is a **root** when its executable lives under *tool_dir* (the uv
    tools dictatem dir whose ``Scripts`` interpreter holds the lock) or equals one
    of *trampolines* (the ``~/.local/bin/dictatem(.exe)`` launcher — an exact path
    match, so a different uv tool in the same bin dir is not caught). The result
    is every root **and all its descendants** (the launcher's re-exec'd base
    interpreter, whose own exe is outside the tool dir), found by walking
    ``parent_pid`` links from the roots. A descendant that predates its parent is
    skipped (a recycled parent PID can't be a genuine child). *self_pid* is always
    excluded. Input order is preserved.
    """
    procs = list(processes)
    by_pid = {p.pid: p for p in procs}
    children: dict[int, list[ProcessInfo]] = defaultdict(list)
    for p in procs:
        children[p.parent_pid].append(p)

    tramp = {_normalize(t) for t in trampolines if t}

    def _is_root(p: ProcessInfo) -> bool:
        return bool(p.exe_path) and (
            is_path_under(p.exe_path, tool_dir) or _normalize(p.exe_path) in tramp
        )

    seen: set[int] = set()
    queue: deque[int] = deque(p.pid for p in procs if _is_root(p))
    while queue:
        pid = queue.popleft()
        if pid in seen:
            continue
        seen.add(pid)
        parent = by_pid.get(pid)
        for child in children.get(pid, ()):
            if child.pid in seen:
                continue
            # A genuine child cannot have started before its parent; a child that
            # does is a stale/recycled parent PID, not really ours — skip it.
            if (
                parent is not None
                and parent.create_time is not None
                and child.create_time is not None
                and child.create_time < parent.create_time
            ):
                continue
            queue.append(child.pid)

    seen.discard(self_pid)
    return [p.pid for p in procs if p.pid in seen]
