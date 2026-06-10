"""Tests for the pure daemon-process matcher (#69).

`dictatem --uninstall` (and, later, the tray Upgrade) must terminate the running
daemon before `uv tool uninstall`/`uv tool install` can touch the
``…\\uv\\tools\\dictatem\\Scripts`` directory — Windows refuses to delete a
directory whose interpreter is loaded ("Access is denied"). The *decision* —
given a snapshot of running processes and where Dictatem is installed, which PIDs
are daemons safe to terminate — is pure logic with no OS calls, so the full match
table is unit-tested here. The win32 adapter supplies the snapshot and kills the
matches.
"""

from __future__ import annotations

from dictatem.process.daemon_stop import ProcessInfo, is_path_under, pids_to_stop

# A representative uv tools install dir; tests use both separator styles to prove
# normalization, since the win32 adapter yields backslash paths.
_TOOL_DIR = r"C:\Users\me\AppData\Roaming\uv\tools\dictatem"
_SCRIPTS_PY = r"C:\Users\me\AppData\Roaming\uv\tools\dictatem\Scripts\pythonw.exe"
_TRAMPOLINE = r"C:\Users\me\.local\bin\dictatem.exe"


class TestIsPathUnder:
    def test_child_is_under_parent(self) -> None:
        assert is_path_under(_SCRIPTS_PY, _TOOL_DIR) is True

    def test_unrelated_path_is_not_under(self) -> None:
        assert is_path_under(r"C:\Windows\System32\notepad.exe", _TOOL_DIR) is False

    def test_sibling_with_shared_prefix_is_not_under(self) -> None:
        # `…\dictatem-old\…` must not match `…\dictatem` on a prefix alone.
        sibling = r"C:\Users\me\AppData\Roaming\uv\tools\dictatem-old\Scripts\py.exe"
        assert is_path_under(sibling, _TOOL_DIR) is False

    def test_case_insensitive(self) -> None:
        # Windows (and default macOS HFS+/APFS) filesystems are case-insensitive.
        assert is_path_under(_SCRIPTS_PY.upper(), _TOOL_DIR.lower()) is True

    def test_mixed_separators_normalized(self) -> None:
        forward = "C:/Users/me/AppData/Roaming/uv/tools/dictatem/Scripts/pythonw.exe"
        assert is_path_under(forward, _TOOL_DIR) is True

    def test_the_dir_itself_is_not_under_itself(self) -> None:
        # A bare directory match is not a process; only things strictly inside.
        assert is_path_under(_TOOL_DIR, _TOOL_DIR) is False

    def test_empty_path_is_never_under(self) -> None:
        # The adapter passes "" for processes whose exe path it couldn't read.
        assert is_path_under("", _TOOL_DIR) is False


class TestPidsToStop:
    def test_matches_process_under_tool_dir(self) -> None:
        procs = [ProcessInfo(pid=1234, exe_path=_SCRIPTS_PY)]
        assert pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR) == [1234]

    def test_excludes_self_even_when_under_tool_dir(self) -> None:
        # The --uninstall process runs the same interpreter under the tool dir;
        # terminating it would kill the cleanup mid-flight.
        procs = [
            ProcessInfo(pid=999, exe_path=_SCRIPTS_PY),
            ProcessInfo(pid=1234, exe_path=_SCRIPTS_PY),
        ]
        assert pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR) == [1234]

    def test_excludes_processes_outside_tool_dir(self) -> None:
        procs = [
            ProcessInfo(pid=1, exe_path=r"C:\Windows\explorer.exe"),
            ProcessInfo(pid=2, exe_path=r"C:\Users\me\AppData\Roaming\uv\tools\ruff\ruff.exe"),
        ]
        assert pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR) == []

    def test_matches_trampoline_exe_exactly(self) -> None:
        procs = [ProcessInfo(pid=42, exe_path=_TRAMPOLINE)]
        result = pids_to_stop(
            procs, self_pid=999, tool_dir=_TOOL_DIR, extra_exes=(_TRAMPOLINE,)
        )
        assert result == [42]

    def test_trampoline_match_is_exact_not_prefix(self) -> None:
        # A different exe in ~/.local/bin (another uv tool) must not match.
        other = r"C:\Users\me\.local\bin\ruff.exe"
        procs = [ProcessInfo(pid=7, exe_path=other)]
        result = pids_to_stop(
            procs, self_pid=999, tool_dir=_TOOL_DIR, extra_exes=(_TRAMPOLINE,)
        )
        assert result == []

    def test_returns_all_matches_in_order(self) -> None:
        procs = [
            ProcessInfo(pid=10, exe_path=_SCRIPTS_PY),
            ProcessInfo(pid=20, exe_path=r"C:\Windows\explorer.exe"),
            ProcessInfo(pid=30, exe_path=_TRAMPOLINE),
        ]
        result = pids_to_stop(
            procs, self_pid=999, tool_dir=_TOOL_DIR, extra_exes=(_TRAMPOLINE,)
        )
        assert result == [10, 30]

    def test_skips_unreadable_exe_paths(self) -> None:
        procs = [ProcessInfo(pid=5, exe_path="")]
        assert pids_to_stop(procs, self_pid=999, tool_dir=_TOOL_DIR) == []

    def test_empty_snapshot_yields_nothing(self) -> None:
        assert pids_to_stop([], self_pid=999, tool_dir=_TOOL_DIR) == []
