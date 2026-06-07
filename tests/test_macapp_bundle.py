"""Tests for the pure ``.app`` bundle generator (#61 / ADR-0014).

The generator is pure file I/O against injected paths, so the full layout —
Info.plist, PkgInfo, exec shim, icon — is generated and inspected under
``tmp_path`` on any OS. Plist content is verified by round-tripping through
``plistlib.loads``, never by string-matching XML. Only "the bundle actually
launches and binds TCC grants" is real-Mac QA.
"""

from __future__ import annotations

import plistlib
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from dictatem.autostart.launch_agent import LaunchAgentRegistrar
from dictatem.macapp.bundle import (
    APP_BUNDLE_NAME,
    EXECUTABLE_NAME,
    ICON_FILENAME,
    generate_app_bundle,
    install_app_bundle,
    launch_arguments,
    remove_app_bundle,
    render_exec_shim,
    resolve_launcher,
)
from dictatem.macapp.plist import BUNDLE_ID


@pytest.fixture
def icns(tmp_path: Path) -> Path:
    """A stand-in .icns asset with recognisable bytes."""
    source = tmp_path / "source.icns"
    source.write_bytes(b"icns-bytes")
    return source


def _generate(tmp_path: Path, icns: Path, **overrides: Any) -> Path:
    return generate_app_bundle(
        apps_dir=tmp_path / "Applications",
        launcher=overrides.get("launcher", Path("/Users/me/.local/bin/dictatem")),
        icns_source=icns,
        version=overrides.get("version"),
    )


def _info(bundle: Path) -> dict[str, Any]:
    info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    assert isinstance(info, dict)
    return info


class TestResolveLauncher:
    """Generation-time resolution mirrors win32 ``_launch_command``."""

    def test_prefers_the_path_which_found(self) -> None:
        resolved = resolve_launcher(
            "/opt/somewhere/bin/dictatem", home=Path("/Users/me")
        )
        assert resolved == Path("/opt/somewhere/bin/dictatem")

    def test_falls_back_to_uv_tool_bin_dir(self) -> None:
        # uv's documented tool-bin directory on macOS.
        resolved = resolve_launcher(None, home=Path("/Users/me"))
        assert resolved == Path("/Users/me/.local/bin/dictatem")


class TestLaunchArguments:
    """The canonical .app launch command (ADR-0012/0014): open, backgrounded."""

    def test_launches_via_open_in_background(self) -> None:
        args = launch_arguments(Path("/Users/me/Applications/Dictatem.app"))
        assert args == [
            "/usr/bin/open",
            "-g",
            "/Users/me/Applications/Dictatem.app",
        ]


class TestRenderExecShim:
    """The shim execs the launcher in-PID so TCC attribution stays bundled."""

    def test_is_a_posix_sh_script(self) -> None:
        shim = render_exec_shim(Path("/Users/me/.local/bin/dictatem"))
        assert shim.startswith("#!/bin/sh\n")

    def test_execs_the_quoted_launcher_forwarding_args(self) -> None:
        shim = render_exec_shim(Path("/Users/me/My Tools/dictatem"))
        assert 'exec "/Users/me/My Tools/dictatem" "$@"' in shim

    def test_ends_with_a_newline(self) -> None:
        assert render_exec_shim(Path("/x/dictatem")).endswith("\n")


class TestGenerateAppBundle:
    """The full Contents/ layout, generated against an injected apps_dir."""

    def test_creates_the_bundle_layout(self, tmp_path: Path, icns: Path) -> None:
        bundle = _generate(tmp_path, icns)
        assert bundle == tmp_path / "Applications" / APP_BUNDLE_NAME
        assert (bundle / "Contents" / "Info.plist").is_file()
        assert (bundle / "Contents" / "PkgInfo").is_file()
        assert (bundle / "Contents" / "MacOS" / EXECUTABLE_NAME).is_file()
        assert (bundle / "Contents" / "Resources" / ICON_FILENAME).is_file()

    def test_info_plist_names_match_files_on_disk(
        self, tmp_path: Path, icns: Path
    ) -> None:
        # CFBundleExecutable/CFBundleIconFile must match the actual filenames,
        # or macOS cannot start the shim / show the icon.
        bundle = _generate(tmp_path, icns)
        info = _info(bundle)
        assert (bundle / "Contents" / "MacOS" / info["CFBundleExecutable"]).is_file()
        assert (bundle / "Contents" / "Resources" / info["CFBundleIconFile"]).is_file()
        assert info["CFBundleIdentifier"] == BUNDLE_ID

    def test_version_is_embedded_when_known(self, tmp_path: Path, icns: Path) -> None:
        info = _info(_generate(tmp_path, icns, version="9.9.9"))
        assert info["CFBundleShortVersionString"] == "9.9.9"
        assert info["CFBundleVersion"] == "9.9.9"

    def test_version_keys_absent_when_unknown(
        self, tmp_path: Path, icns: Path
    ) -> None:
        info = _info(_generate(tmp_path, icns))
        assert "CFBundleShortVersionString" not in info
        assert "CFBundleVersion" not in info

    def test_pkginfo_marks_an_application(self, tmp_path: Path, icns: Path) -> None:
        bundle = _generate(tmp_path, icns)
        assert (bundle / "Contents" / "PkgInfo").read_bytes() == b"APPL????"

    def test_shim_execs_the_launcher(self, tmp_path: Path, icns: Path) -> None:
        bundle = _generate(tmp_path, icns, launcher=Path("/opt/bin/dictatem"))
        shim = (bundle / "Contents" / "MacOS" / EXECUTABLE_NAME).read_text(
            encoding="utf-8"
        )
        assert shim == render_exec_shim(Path("/opt/bin/dictatem"))

    @pytest.mark.skipif(
        sys.platform == "win32", reason="exec bits are not a thing on Windows"
    )
    def test_shim_is_executable(self, tmp_path: Path, icns: Path) -> None:
        bundle = _generate(tmp_path, icns)
        mode = (bundle / "Contents" / "MacOS" / EXECUTABLE_NAME).stat().st_mode
        assert mode & stat.S_IXUSR

    def test_copies_the_icns_bytes(self, tmp_path: Path, icns: Path) -> None:
        bundle = _generate(tmp_path, icns)
        copied = bundle / "Contents" / "Resources" / ICON_FILENAME
        assert copied.read_bytes() == b"icns-bytes"

    def test_regeneration_refreshes_in_place(self, tmp_path: Path, icns: Path) -> None:
        # An upgrade re-runs the generator: the launcher path and version are
        # refreshed while the bundle path (the TCC identity anchor) is stable.
        first = _generate(tmp_path, icns, launcher=Path("/old/dictatem"))
        second = _generate(
            tmp_path, icns, launcher=Path("/new/dictatem"), version="2.0"
        )
        assert second == first
        shim = (second / "Contents" / "MacOS" / EXECUTABLE_NAME).read_text(
            encoding="utf-8"
        )
        assert '"/new/dictatem"' in shim
        assert _info(second)["CFBundleVersion"] == "2.0"


class TestInstallAppBundle:
    """Bundle generation + the upgrade-path LaunchAgent refresh (PR #86 note)."""

    def _install(self, tmp_path: Path, icns: Path) -> tuple[Path, bool]:
        return install_app_bundle(
            apps_dir=tmp_path / "Applications",
            agents_dir=tmp_path / "LaunchAgents",
            launcher=Path("/Users/me/.local/bin/dictatem"),
            icns_source=icns,
        )

    def test_fresh_install_does_not_create_a_launch_agent(
        self, tmp_path: Path, icns: Path
    ) -> None:
        # Autostart is the daemon's to reconcile (ADR-0012) — no plist means
        # the flag has never been applied, and the installer must not preempt
        # the user's config.
        bundle, refreshed = self._install(tmp_path, icns)
        assert bundle.is_dir()
        assert refreshed is False
        assert not (tmp_path / "LaunchAgents" / f"{BUNDLE_ID}.plist").exists()

    def test_existing_launch_agent_is_rewritten_with_current_command(
        self, tmp_path: Path, icns: Path
    ) -> None:
        # The stale-launch-command heal: is_enabled() is existence-only, so
        # the upgrade path (here) is what rewrites an old ProgramArguments.
        agents_dir = tmp_path / "LaunchAgents"
        stale = LaunchAgentRegistrar(
            agents_dir=agents_dir, program_arguments=["/old/command"]
        )
        stale.enable()

        bundle, refreshed = self._install(tmp_path, icns)

        assert refreshed is True
        agent = plistlib.loads((agents_dir / f"{BUNDLE_ID}.plist").read_bytes())
        assert agent["ProgramArguments"] == launch_arguments(bundle)


class TestRemoveAppBundle:
    """Uninstall removes the generated bundle before `uv tool uninstall`."""

    def test_removes_the_bundle_and_returns_its_path(
        self, tmp_path: Path, icns: Path
    ) -> None:
        bundle = _generate(tmp_path, icns)
        removed = remove_app_bundle(bundle)
        assert removed == bundle
        assert not bundle.exists()

    def test_returns_none_when_already_absent(self, tmp_path: Path) -> None:
        assert remove_app_bundle(tmp_path / "Applications" / APP_BUNDLE_NAME) is None
