"""install.ps1 must judge `uv tool install` by ITS exit code, not a later call's.

Home-PC QA (2026-11-03): after a failed install, Test-DictatemEnvBroken ran
`uv tool dir`, which reset $LASTEXITCODE to 0, so the installer skipped its
throw and went on to prewarm and launch a broken install. The exit code is now
captured straight after each `uv tool install`. A truncated (0-byte)
python.exe also counts as a broken env.
"""

from __future__ import annotations

import re
from pathlib import Path

_SCRIPT = (Path(__file__).resolve().parents[1] / "install.ps1").read_text(encoding="utf-8")


def _install_block() -> str:
    start = _SCRIPT.index("Write-Host \"Installing dictatem[")
    end = _SCRIPT.index("# Make the freshly installed")
    return _SCRIPT[start:end]


def test_every_uv_tool_install_is_followed_by_capturing_its_exit_code() -> None:
    lines = [ln.strip() for ln in _install_block().splitlines()]
    installs = [i for i, ln in enumerate(lines) if ln.startswith("uv tool install ")]
    assert len(installs) == 2  # first attempt + the one recovery retry
    for i in installs:
        following = next(ln for ln in lines[i + 1 :] if ln and not ln.startswith("#"))
        assert following == "$uvInstallExit = $LASTEXITCODE", following


def test_failure_checks_use_the_captured_exit_code() -> None:
    block = _install_block()
    assert "if ($uvInstallExit -ne 0)" in block
    assert re.search(r"if \(\$LASTEXITCODE -ne 0\)", block) is None
    assert "exit code $uvInstallExit). See the error above" in block


def test_a_truncated_python_exe_counts_as_a_broken_env() -> None:
    start = _SCRIPT.index("function Test-DictatemEnvBroken")
    body = _SCRIPT[start : _SCRIPT.index("\n}\n", start)]
    assert ".Length -lt 1024" in body
