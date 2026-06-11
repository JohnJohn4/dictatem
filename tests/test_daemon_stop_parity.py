"""Parity + sync tests for the two daemon-stop implementations (#69/#98/#100).

The same daemon-stop *decision* lives in two languages — Python
(``dictatem.process.daemon_stop.pids_to_stop``, used by ``dictatem --uninstall``)
and PowerShell (``Get-DaemonKillSet``, used by ``install.ps1``'s upgrade stop).
They drifted once already — the Python side excluded the launching process and the
PowerShell side didn't, which let the tray upgrade's installer kill itself. These
tests stop that from recurring:

* **Sync** (every OS): ``install.ps1`` embeds the canonical
  ``scripts/daemon_stop_lib.ps1`` verbatim — so the script can't drift from the
  unit-tested source.
* **Parity** (Windows only — needs ``powershell``): both implementations produce
  the *same* kill-set over shared fixtures, including the self-in-tree case that
  the drift broke.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dictatem.process.daemon_stop import ProcessInfo, pids_to_stop

_REPO = Path(__file__).resolve().parent.parent
_LIB = _REPO / "scripts" / "daemon_stop_lib.ps1"
_INSTALL_PS1 = _REPO / "install.ps1"

_TOOL_DIR = r"C:\Users\me\AppData\Roaming\uv\tools\dictatem"
_TRAMPOLINE = r"C:\Users\me\.local\bin\dictatem.exe"
_SCRIPTS_PY = r"C:\Users\me\AppData\Roaming\uv\tools\dictatem\Scripts\pythonw.exe"
_BASE_PY = r"C:\Users\me\AppData\Local\Programs\Python\Python313\pythonw.exe"


def _proc(pid: int, ppid: int, exe: str, create: str = "100") -> dict:
    return {"pid": pid, "parent_pid": ppid, "exe_path": exe, "create_time": create}


# Each case feeds BOTH implementations; `expected` is the agreed kill-set.
_CASES: list[dict] = [
    {
        "id": "root-under-tool-dir",
        "processes": [_proc(4532, 1, _SCRIPTS_PY)],
        "tool_dir": _TOOL_DIR, "trampolines": [], "self_pid": 999,
        "expected": [4532],
    },
    {
        "id": "reexec-child-outside-tool-dir",
        "processes": [
            _proc(1000, 1, r"C:\Windows\explorer.exe", "050"),
            _proc(3112, 1000, _TRAMPOLINE, "100"),
            _proc(4532, 3112, _SCRIPTS_PY, "101"),
            _proc(9424, 4532, _BASE_PY, "102"),
        ],
        "tool_dir": _TOOL_DIR, "trampolines": [_TRAMPOLINE], "self_pid": 999,
        "expected": [3112, 4532, 9424],
    },
    {
        "id": "self-leaf-excluded",
        "processes": [
            _proc(3112, 1, _TRAMPOLINE, "100"),
            _proc(4532, 3112, _SCRIPTS_PY, "101"),
            _proc(9424, 4532, _BASE_PY, "102"),
        ],
        "tool_dir": _TOOL_DIR, "trampolines": [_TRAMPOLINE], "self_pid": 9424,
        "expected": [3112, 4532],
    },
    {
        "id": "self-subtree-excluded",
        "processes": [
            _proc(3112, 1, _TRAMPOLINE, "100"),
            _proc(4532, 3112, _SCRIPTS_PY, "101"),
            _proc(9424, 4532, _BASE_PY, "102"),
        ],
        "tool_dir": _TOOL_DIR, "trampolines": [_TRAMPOLINE], "self_pid": 4532,
        "expected": [3112],
    },
    {
        "id": "trampoline-exact-not-sibling",
        "processes": [
            _proc(42, 1, _TRAMPOLINE),
            _proc(7, 1, r"C:\Users\me\.local\bin\ruff.exe"),
        ],
        "tool_dir": _TOOL_DIR, "trampolines": [_TRAMPOLINE], "self_pid": 999,
        "expected": [42],
    },
    {
        "id": "recycled-parent-pid-guard",
        "processes": [
            _proc(4532, 3112, _SCRIPTS_PY, "200"),
            _proc(8888, 4532, r"C:\Windows\System32\svchost.exe", "050"),
        ],
        "tool_dir": _TOOL_DIR, "trampolines": [], "self_pid": 999,
        "expected": [4532],
    },
    {
        "id": "no-roots",
        "processes": [
            _proc(1, 0, r"C:\Windows\explorer.exe"),
            _proc(2, 1, r"C:\Users\me\AppData\Roaming\uv\tools\ruff\ruff.exe"),
        ],
        "tool_dir": _TOOL_DIR, "trampolines": [], "self_pid": 999,
        "expected": [],
    },
    {
        "id": "empty-snapshot",
        "processes": [],
        "tool_dir": _TOOL_DIR, "trampolines": [], "self_pid": 999,
        "expected": [],
    },
]


def _python_kill_set(case: dict) -> list[int]:
    procs = [ProcessInfo(**p) for p in case["processes"]]
    return pids_to_stop(
        procs,
        self_pid=case["self_pid"],
        tool_dir=case["tool_dir"],
        trampolines=tuple(case["trampolines"]),
    )


def _powershell_kill_set(case: dict, tmp_path: Path) -> list[int]:
    payload = {
        "processes": [
            {
                "ProcessId": p["pid"],
                "ParentProcessId": p["parent_pid"],
                "ExecutablePath": p["exe_path"],
                "CreationDate": p["create_time"],
            }
            for p in case["processes"]
        ],
        "tool_dir": case["tool_dir"],
        "trampolines": case["trampolines"],
        "self_pid": case["self_pid"],
    }
    case_json = tmp_path / "case.json"
    case_json.write_text(json.dumps(payload), encoding="utf-8")
    cmd = (
        f". '{_LIB}'; "
        f"$c = Get-Content -Raw '{case_json}' | ConvertFrom-Json; "
        f"$kill = Get-DaemonKillSet -Processes @($c.processes) -ToolDir ([string]$c.tool_dir) "
        f"-Trampolines @($c.trampolines) -SelfPid ([int]$c.self_pid); "
        f"Write-Output (@($kill) -join ',')"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", cmd],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"powershell failed: {result.stderr}"
    out = result.stdout.strip()
    return [int(x) for x in out.split(",") if x.strip()]


def _normalize_ps(text: str) -> str:
    """EOL- and trailing-whitespace-insensitive form for the sync compare."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip("\n")


class TestInstallPs1EmbedsCanonicalDecision:
    """install.ps1 must contain scripts/daemon_stop_lib.ps1 verbatim (no drift)."""

    def test_canonical_lib_is_embedded_in_install_ps1(self) -> None:
        lib = _normalize_ps(_LIB.read_text(encoding="utf-8"))
        install = _normalize_ps(_INSTALL_PS1.read_text(encoding="utf-8"))
        assert lib in install, (
            "install.ps1 has drifted from scripts/daemon_stop_lib.ps1 — re-sync the "
            "embedded canonical daemon-stop block."
        )


class TestPythonMatchesExpected:
    """The shared fixtures pin the Python core's behaviour on every OS."""

    @pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
    def test_python_kill_set(self, case: dict) -> None:
        assert sorted(_python_kill_set(case)) == sorted(case["expected"])


class TestPowerShellPythonParity:
    """Both implementations must agree, fixture-for-fixture (Windows only)."""

    @pytest.mark.skipif(sys.platform != "win32", reason="needs Windows PowerShell")
    @pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
    def test_powershell_matches_python(self, case: dict, tmp_path: Path) -> None:
        ps = _powershell_kill_set(case, tmp_path)
        py = _python_kill_set(case)
        assert sorted(ps) == sorted(py) == sorted(case["expected"]), (
            f"case {case['id']}: powershell={sorted(ps)} python={sorted(py)} "
            f"expected={sorted(case['expected'])}"
        )
