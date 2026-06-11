"""Tests for the pure daemon-process matcher (#69).

`dictatem --uninstall` (and the tray Upgrade) must terminate the running daemon
before `uv tool uninstall`/`uv tool install` can touch the
``…\\uv\\tools\\dictatem\\Scripts`` directory — Windows refuses to delete a
directory whose interpreter is loaded ("Access is denied"). The *decision* —
given a process snapshot and where Dictatem is installed, which PIDs are the
daemon's tree — is pure logic with no OS calls, so it is fully unit-tested here.
The win32 adapter supplies the WMI snapshot and kills the matches.

The critical case is the launcher's re-exec'd base-interpreter child: its exe
lives *outside* the tool dir, so path-matching alone orphans the real daemon. The
matcher walks parent→child from the path-matched roots to catch it (the bug a
real-machine uninstall surfaced).
"""

from __future__ import annotations

from dictatem.process.daemon_stop import ProcessInfo, is_path_under, pids_to_stop

_TOOL_DIR = r"C:\Users\me\AppData\Roaming\uv\tools\dictatem"
_TRAMPOLINE = r"C:\Users\me\.local\bin\dictatem.exe"
_SCRIPTS_PY = r"C:\Users\me\AppData\Roaming\uv\tools\dictatem\Scripts\pythonw.exe"
# The re-exec'd real daemon — base CPython, exe OUTSIDE the tool dir.
_BASE_PY = r"C:\Users\me\AppData\Local\Programs\Python\Python313\pythonw.exe"


def _p(pid: int, parent_pid: int, exe: str, create: str | None = "100") -> ProcessInfo:
    return ProcessInfo(pid=pid, parent_pid=parent_pid, exe_path=exe, create_time=create)


class TestIsPathUnder:
    def test_child_is_under_parent(self) -> None:
        assert is_path_under(_SCRIPTS_PY, _TOOL_DIR) is True

    def test_unrelated_path_is_not_under(self) -> None:
        assert is_path_under(r"C:\Windows\System32\notepad.exe", _TOOL_DIR) is False

    def test_sibling_with_shared_prefix_is_not_under(self) -> None:
        sibling = r"C:\Users\me\AppData\Roaming\uv\tools\dictatem-old\Scripts\py.exe"
        assert is_path_under(sibling, _TOOL_DIR) is False

    def test_case_insensitive(self) -> None:
        assert is_path_under(_SCRIPTS_PY.upper(), _TOOL_DIR.lower()) is True

    def test_mixed_separators_normalized(self) -> None:
        forward = "C:/Users/me/AppData/Roaming/uv/tools/dictatem/Scripts/pythonw.exe"
        assert is_path_under(forward, _TOOL_DIR) is True

    def test_the_dir_itself_is_not_under_itself(self) -> None:
        assert is_path_under(_TOOL_DIR, _TOOL_DIR) is False

    def test_empty_path_is_never_under(self) -> None:
        assert is_path_under("", _TOOL_DIR) is False


# The real daemon process tree as seen on Windows: explorer -> trampoline ->
# Scripts stub -> re-exec'd base CPython (the actual daemon).
def _daemon_tree() -> list[ProcessInfo]:
    return [
        _p(1000, 24936, r"C:\Windows\explorer.exe", create="050"),
        _p(3112, 1000, _TRAMPOLINE, create="100"),
        _p(4532, 3112, _SCRIPTS_PY, create="101"),
        _p(9424, 4532, _BASE_PY, create="102"),
    ]


class TestPidsToStop:
    def test_matches_root_under_tool_dir(self) -> None:
        procs = [_p(4532, 1, _SCRIPTS_PY)]
        assert pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR) == [4532]

    def test_matches_trampoline_root_exactly(self) -> None:
        procs = [_p(3112, 1, _TRAMPOLINE)]
        result = pids_to_stop(
            procs, self_pid=999, tool_dir=_TOOL_DIR, trampolines=(_TRAMPOLINE,)
        )
        assert result == [3112]

    def test_trampoline_match_is_exact_not_prefix(self) -> None:
        other = r"C:\Users\me\.local\bin\ruff.exe"
        procs = [_p(7, 1, other)]
        result = pids_to_stop(
            procs, self_pid=999, tool_dir=_TOOL_DIR, trampolines=(_TRAMPOLINE,)
        )
        assert result == []

    def test_catches_reexec_base_python_child_outside_tool_dir(self) -> None:
        # THE regression: 9424's exe is Python313\pythonw.exe (outside the tool
        # dir), reachable only by walking from the Scripts-stub root. Path
        # matching alone would orphan it and leave the lock held.
        result = pids_to_stop(
            _daemon_tree(), self_pid=999, tool_dir=_TOOL_DIR, trampolines=(_TRAMPOLINE,)
        )
        assert set(result) == {3112, 4532, 9424}
        assert 9424 in result

    def test_excludes_self_even_inside_the_tree(self) -> None:
        # The --uninstall process is itself the re-exec'd base python under the
        # tool tree; it must never terminate itself.
        result = pids_to_stop(
            _daemon_tree(), self_pid=9424, tool_dir=_TOOL_DIR, trampolines=(_TRAMPOLINE,)
        )
        assert 9424 not in result
        assert set(result) == {3112, 4532}

    def test_unrelated_process_not_caught(self) -> None:
        # A shell that merely mentions the path (not a descendant of a root) and
        # the explorer parent must not be swept up.
        procs = _daemon_tree() + [
            _p(5000, 1000, r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"),
        ]
        result = pids_to_stop(
            procs, self_pid=999, tool_dir=_TOOL_DIR, trampolines=(_TRAMPOLINE,)
        )
        assert 5000 not in result
        assert 1000 not in result  # explorer (the trampoline's parent) is not a root

    def test_recycled_parent_pid_child_is_skipped(self) -> None:
        # A process whose parent_pid equals a root's PID but which started BEFORE
        # that root is a recycled-PID coincidence, not a real child.
        procs = [
            _p(4532, 3112, _SCRIPTS_PY, create="200"),
            _p(8888, 4532, r"C:\Windows\System32\svchost.exe", create="050"),
        ]
        result = pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR)
        assert result == [4532]
        assert 8888 not in result

    def test_genuine_child_after_parent_is_kept(self) -> None:
        procs = [
            _p(4532, 3112, _SCRIPTS_PY, create="100"),
            _p(9424, 4532, _BASE_PY, create="101"),
        ]
        result = pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR)
        assert set(result) == {4532, 9424}

    def test_missing_create_time_does_not_block_walk(self) -> None:
        # Best-effort: if timestamps are unavailable the guard is simply not
        # applied, so the child is still caught.
        procs = [
            _p(4532, 3112, _SCRIPTS_PY, create=None),
            _p(9424, 4532, _BASE_PY, create=None),
        ]
        result = pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR)
        assert set(result) == {4532, 9424}

    def test_no_roots_yields_nothing(self) -> None:
        procs = [
            _p(1, 0, r"C:\Windows\explorer.exe"),
            _p(2, 1, r"C:\Users\me\AppData\Roaming\uv\tools\ruff\ruff.exe"),
        ]
        assert pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR) == []

    def test_empty_snapshot_yields_nothing(self) -> None:
        assert pids_to_stop([], self_pid=999, tool_dir=_TOOL_DIR) == []

    def test_empty_tool_dir_matches_nothing(self) -> None:
        # A failed tool-dir resolution must not turn into an everything-matches.
        assert pids_to_stop(_daemon_tree(), self_pid=999, tool_dir="") == []

    def test_preserves_input_order(self) -> None:
        result = pids_to_stop(
            _daemon_tree(), self_pid=999, tool_dir=_TOOL_DIR, trampolines=(_TRAMPOLINE,)
        )
        assert result == [3112, 4532, 9424]
