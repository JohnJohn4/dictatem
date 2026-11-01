"""The ``apple-gpu`` extra and the ``install.sh`` gate that selects it (#230, ADR-0013).

The extra ships the MLX engine (mlx-whisper) to Apple-Silicon Macs on macOS 14+.
mlx/mlx-metal/torch publish arm64 wheels for macOS 14+ only, so an install that
pulls them on macOS 12/13 or an Intel Mac fails outright (the same failure class
as the ``av`` pin in the runtime extra). Two layers keep that from happening:

* the extra's own requirements are marker-guarded to darwin + arm64, so on any
  other platform the extra resolves to exactly the runtime extra; and
* ``install.sh`` asks for the extra only when opted in with ``DICTATEM_APPLE_GPU=1``
  on arm64 with macOS major >= 14 (a PEP 508 marker cannot express the OS
  version). Opt-in until real-Mac QA (v0.7.0 owner decision).

Both layers are enforced here: the extra statically, the gate behaviourally by
running the installer's own selection function under ``sh``.
"""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

_REPO = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO / "pyproject.toml"
_INSTALL_SH = _REPO / "install.sh"
_CI_YML = _REPO / ".github" / "workflows" / "ci.yml"


def _extra(name: str) -> list[Requirement]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return [Requirement(r) for r in data["project"]["optional-dependencies"][name]]


def _engine_reqs() -> list[Requirement]:
    """The apple-gpu requirements beyond the runtime extra it includes."""
    return [r for r in _extra("apple-gpu") if r.name != "dictatem"]


def _env(sys_platform: str, platform_machine: str) -> dict[str, str]:
    env = dict(default_environment())
    env.update(sys_platform=sys_platform, platform_machine=platform_machine, extra="")
    return env


class TestAppleGpuExtra:
    def test_includes_the_runtime_extra(self) -> None:
        # faster-whisper stays installed either way: it is the fallback engine.
        includes = [r for r in _extra("apple-gpu") if r.name == "dictatem"]
        assert [sorted(r.extras) for r in includes] == [["runtime"]]

    def test_pins_mlx_whisper_exactly(self) -> None:
        (req,) = [r for r in _engine_reqs() if r.name == "mlx-whisper"]
        assert str(req.specifier) == "==0.4.3"

    def test_bounds_mlx_to_a_tested_range(self) -> None:
        (req,) = [r for r in _engine_reqs() if r.name == "mlx"]
        specs = {s.operator for s in req.specifier}
        assert ">=" in specs and "<" in specs, f"mlx must be bounded, got {req.specifier}"
        assert "0.32.4" in SpecifierSet(str(req.specifier))  # the CI-locked version

    @pytest.mark.parametrize(
        ("sys_platform", "machine"),
        [
            ("win32", "AMD64"),
            ("win32", "ARM64"),
            ("darwin", "x86_64"),  # Intel Mac / Rosetta interpreter
            ("linux", "x86_64"),
            ("linux", "aarch64"),
        ],
    )
    def test_adds_nothing_beyond_runtime_off_apple_silicon(
        self, sys_platform: str, machine: str
    ) -> None:
        # mlx now ships win/linux wheels, so `sys_platform == 'darwin'` alone is
        # not enough: every engine requirement must also be gated on arm64.
        env = _env(sys_platform, machine)
        active = [str(r) for r in _engine_reqs() if r.marker is None or r.marker.evaluate(env)]
        assert active == []

    def test_engine_requirements_apply_on_apple_silicon(self) -> None:
        env = _env("darwin", "arm64")
        reqs = _engine_reqs()
        assert reqs and all(r.marker is not None and r.marker.evaluate(env) for r in reqs)


# --- install.sh gate ---------------------------------------------------------

_FUNC = "select_dictatem_extra"


def _gate_function() -> str:
    """The installer's selection function, extracted verbatim."""
    text = _INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(rf"^{_FUNC}\(\)\s*\{{\n.*?^\}}$", text, re.MULTILINE | re.DOTALL)
    assert match, f"install.sh must define a top-level `{_FUNC}()` function"
    return match.group(0)


_SH = shutil.which("sh")


@pytest.mark.skipif(_SH is None, reason="needs a POSIX sh")
class TestInstallShGate:
    def _select(self, arch: str, version: str, opt_in: str | None = "1") -> str:
        assert _SH is not None
        script = f'{_gate_function()}\n{_FUNC} "$1" "$2"\n'
        env = {"PATH": "/usr/bin:/bin"}
        if opt_in is not None:
            env["DICTATEM_APPLE_GPU"] = opt_in
        result = subprocess.run(
            [_SH, "-c", script, "gate", arch, version],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        return result.stdout.strip()

    @pytest.mark.parametrize("version", ["14.0", "14.7.1", "15.3", "26.0.1", "14"])
    def test_apple_silicon_on_macos_14_plus_gets_apple_gpu(self, version: str) -> None:
        assert self._select("arm64", version) == "apple-gpu"

    @pytest.mark.parametrize("version", ["13.6.7", "12.7", "10.15.7", "", "garbage"])
    def test_apple_silicon_below_14_or_unknown_gets_runtime(self, version: str) -> None:
        assert self._select("arm64", version) == "runtime"

    @pytest.mark.parametrize("version", ["15.3", "13.6"])
    def test_intel_mac_gets_runtime(self, version: str) -> None:
        assert self._select("x86_64", version) == "runtime"

    def test_without_opt_in_apple_silicon_gets_runtime(self) -> None:
        # v0.7.0: the Apple GPU engine is opt-in until real-Mac QA (#230-#233).
        assert self._select("arm64", "15.3", opt_in=None) == "runtime"

    def test_opt_in_other_than_1_is_ignored(self) -> None:
        assert self._select("arm64", "15.3", opt_in="") == "runtime"
        assert self._select("arm64", "15.3", opt_in="yes") == "runtime"


class TestInstallShWiring:
    def _code(self) -> str:
        text = _INSTALL_SH.read_text(encoding="utf-8")
        return "\n".join(line.split("#", 1)[0] for line in text.splitlines())

    def test_gate_is_fed_the_real_arch_and_macos_version(self) -> None:
        assert re.search(
            rf'{_FUNC}\s+"\$\(uname -m\)"\s+"\$\(sw_vers -productVersion[^"]*\)"', self._code()
        )

    def test_requirement_uses_the_selected_extra(self) -> None:
        code = self._code()
        assert re.search(r'requirement="dictatem\[\$\{?dictatem_extra\}?\] @ ', code)
        assert "dictatem[runtime] @" not in code

    def test_installer_names_the_engine_set(self) -> None:
        code = self._code()
        assert "Apple GPU" in code and "CPU" in code


class TestCiResolvesTheExtra:
    def test_macos_leg_syncs_apple_gpu(self) -> None:
        # ADR-0013's brittle-resolution constraint: the matrix runs every Python
        # on macos-latest, so syncing the extra there resolves it on each one.
        ci = _CI_YML.read_text(encoding="utf-8")
        assert re.search(r"uv sync\b[^\n]*--extra apple-gpu", ci)
        assert "macos-latest" in ci

    def test_windows_leg_checks_apple_gpu_adds_nothing(self) -> None:
        # `uv sync --check` exits non-zero if syncing the extra would change the
        # runtime environment, so the Windows leg proves the MLX set is gated off.
        ci = _CI_YML.read_text(encoding="utf-8")
        assert re.search(
            r"if: runner\.os == 'Windows'\s*\n\s*run: uv sync --extra apple-gpu --check\b",
            ci,
        )
