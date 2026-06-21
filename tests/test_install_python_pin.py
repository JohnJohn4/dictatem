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

# install.ps1: the `$dictatemPython = if (...) ... else { '3.12' }` default —
# anchored on the assignment and tolerant of single/double quotes and a
# multi-line reformat — plus any hard-coded `cpython-X.Y-windows` build id (the
# ARM pin interpolates $dictatemPython today, but a future literal is caught too).
_PS1_PINS = [
    rf"\$dictatemPython\s*=\s*if[\s\S]*?else\s*\{{\s*['\"]{_VER}['\"]",
    rf"cpython-{_VER}-windows",
]
# install.sh: the `DICTATEM_PYTHON="${DICTATEM_PYTHON:-3.12}"` default.
_SH_PINS = [rf"DICTATEM_PYTHON:-{_VER}"]


def _strip_comments(text: str) -> str:
    """Drop `#`-to-end-of-line on every line.

    Both installers mention example versions in comments (e.g. the
    `cpython-3.12-windows-x86_64` in install.ps1's `uv tool install` note).
    Parsing only code keeps an illustrative or stale comment from masquerading as
    an enforced pin — which would both false-fail and defeat the vacuous-pass
    guard below (a comment version would keep the pin set non-empty even after the
    real pin stopped matching).
    """
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _pins(text: str, patterns: list[str]) -> set[str]:
    code = _strip_comments(text)
    found: set[str] = set()
    for pattern in patterns:
        found.update(re.findall(pattern, code))
    return found


def _ci_matrix_versions(text: str) -> set[str]:
    # The matrix is inline today (`python-version: ["3.11", ...]`); also accept a
    # YAML block list. Anchored on the key so the `${{ matrix.python-version }}`
    # reference in the setup step is never mistaken for the matrix.
    match = re.search(
        r"python-version:\s*(\[[^\]]*\]|(?:\n\s*-\s*['\"]?\d+\.\d+['\"]?)+)", text
    )
    assert match, "could not find a `python-version` matrix in ci.yml"
    return set(re.findall(_VER, match.group(1)))


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
