"""The Python version each installer pins must be one the CI matrix tests (#90).

Both installers pin a uv-managed CPython for a reproducible install (ADR-0011/
0015): ``install.sh`` via ``DICTATEM_PYTHON`` (macOS, #61), ``install.ps1`` via
``$dictatemPython`` (x64 ``--managed-python`` + the ARM x64-emulation build,
ADR-0017). A pin the CI matrix (``.github/workflows/ci.yml``) does not exercise
would ship users an interpreter no test ever ran — the "CI-tested version"
comment turned into an enforced invariant, so the pin and the matrix cannot
drift apart.
"""

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_INSTALL_PS1 = _REPO / "install.ps1"
_INSTALL_SH = _REPO / "install.sh"
_CI_YML = _REPO / ".github" / "workflows" / "ci.yml"

_VER = r"(\d+\.\d+)"

# install.ps1: the `$dictatemPython = ... else { '3.12' }` default, plus any
# hard-coded `cpython-X.Y-windows` build id (the ARM pin currently interpolates
# $dictatemPython, but a future literal would be caught too).
_PS1_PINS = [
    rf"DICTATEM_PYTHON[^\n]*?else\s*\{{\s*'{_VER}'",
    rf"cpython-{_VER}-windows",
]
# install.sh: the `DICTATEM_PYTHON="${DICTATEM_PYTHON:-3.12}"` default.
_SH_PINS = [rf"DICTATEM_PYTHON:-{_VER}"]


def _pins(text: str, patterns: list[str]) -> set[str]:
    found: set[str] = set()
    for pattern in patterns:
        found.update(re.findall(pattern, text))
    return found


def _ci_matrix_versions(text: str) -> set[str]:
    line = re.search(r"python-version:\s*\[([^\]]*)\]", text)
    assert line, "could not find a `python-version: [...]` matrix in ci.yml"
    return set(re.findall(_VER, line.group(1)))


class TestInstallerPythonPin:
    def test_ci_matrix_parses(self) -> None:
        matrix = _ci_matrix_versions(_CI_YML.read_text(encoding="utf-8"))
        assert matrix, "no Python versions parsed from the CI matrix"

    def test_every_installer_pin_is_in_the_ci_matrix(self) -> None:
        matrix = _ci_matrix_versions(_CI_YML.read_text(encoding="utf-8"))
        ps1_pins = _pins(_INSTALL_PS1.read_text(encoding="utf-8"), _PS1_PINS)
        sh_pins = _pins(_INSTALL_SH.read_text(encoding="utf-8"), _SH_PINS)

        # Guard against a parser that silently matches nothing (a refactor of the
        # pin syntax) turning the assertion below into a vacuous pass.
        assert ps1_pins, "no pinned Python version found in install.ps1"
        assert sh_pins, "no pinned Python version found in install.sh"

        for version in ps1_pins | sh_pins:
            assert version in matrix, (
                f"an installer pins Python {version} but the CI matrix only tests "
                f"{sorted(matrix)} (install.ps1={sorted(ps1_pins)}, "
                f"install.sh={sorted(sh_pins)}) — add it to ci.yml or change the pin"
            )
