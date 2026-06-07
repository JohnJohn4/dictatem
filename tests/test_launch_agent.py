"""Tests for the macOS LaunchAgent renderer + registrar (#61 / ADR-0012/0014).

The plist renderer is pure; the registrar is only the file I/O seam around an
injected LaunchAgents directory, so all three Protocol methods run against
``tmp_path`` on any OS. The reconcile decision is reused from
``autostart.reconcile``, never duplicated here. Plist content is verified by
round-tripping through ``plistlib.loads`` — never string-matching XML.
"""

from __future__ import annotations

import plistlib
from typing import TYPE_CHECKING, Any

import pytest

from dictatem.autostart.launch_agent import (
    LaunchAgentRegistrar,
    render_launch_agent_plist,
)
from dictatem.autostart.reconcile import AutostartAction, apply_autostart
from dictatem.interfaces import AutostartRegistrar
from dictatem.macapp.plist import BUNDLE_ID

if TYPE_CHECKING:
    from pathlib import Path

PROGRAM_ARGS = ["/usr/bin/open", "-a", "/Users/me/Applications/Dictatem.app"]


def _registrar(tmp_path: Path) -> LaunchAgentRegistrar:
    return LaunchAgentRegistrar(
        agents_dir=tmp_path / "LaunchAgents", program_arguments=PROGRAM_ARGS
    )


def _load(plist_path: Path) -> dict[str, Any]:
    agent = plistlib.loads(plist_path.read_bytes())
    assert isinstance(agent, dict)
    return agent


class TestRenderLaunchAgentPlist:
    """Pure renderer: (label, argv) -> plist bytes with the launchd keys."""

    def test_round_trips_label_and_program_arguments(self) -> None:
        rendered = render_launch_agent_plist(
            label="com.example.job", program_arguments=("cmd", "--flag")
        )
        agent = plistlib.loads(rendered)
        assert agent["Label"] == "com.example.job"
        assert agent["ProgramArguments"] == ["cmd", "--flag"]

    def test_runs_at_load(self) -> None:
        rendered = render_launch_agent_plist(label="x", program_arguments=["cmd"])
        agent = plistlib.loads(rendered)
        assert agent["RunAtLoad"] is True

    def test_associates_the_label_bundle_for_login_items(self) -> None:
        # macOS 13+ Login Items shows the owning app's name via this key;
        # without it the entry surfaces as the bare argv[0] — "open" (#61).
        rendered = render_launch_agent_plist(
            label="com.example.job", program_arguments=["cmd"]
        )
        agent = plistlib.loads(rendered)
        assert agent["AssociatedBundleIdentifiers"] == ["com.example.job"]


class TestRegistrarProtocol:
    """The registrar satisfies the AutostartRegistrar Protocol."""

    def test_is_an_autostart_registrar(self, tmp_path: Path) -> None:
        assert isinstance(_registrar(tmp_path), AutostartRegistrar)


class TestEnable:
    """enable writes ``<agents_dir>/<label>.plist`` launching the .app."""

    def test_creates_plist_named_after_bundle_id(self, tmp_path: Path) -> None:
        registrar = _registrar(tmp_path)
        registrar.enable()
        assert registrar.plist_path == tmp_path / "LaunchAgents" / f"{BUNDLE_ID}.plist"
        assert registrar.plist_path.is_file()

    def test_plist_content_round_trips(self, tmp_path: Path) -> None:
        registrar = _registrar(tmp_path)
        registrar.enable()
        agent = _load(registrar.plist_path)
        assert agent["Label"] == BUNDLE_ID
        assert agent["ProgramArguments"] == PROGRAM_ARGS
        assert agent["RunAtLoad"] is True

    def test_creates_missing_launch_agents_dir(self, tmp_path: Path) -> None:
        # A fresh user account may have no ~/Library/LaunchAgents at all.
        registrar = _registrar(tmp_path)
        assert not (tmp_path / "LaunchAgents").exists()
        registrar.enable()
        assert registrar.is_enabled()

    def test_idempotent_when_already_enabled(self, tmp_path: Path) -> None:
        registrar = _registrar(tmp_path)
        registrar.enable()
        registrar.enable()
        agent = _load(registrar.plist_path)
        assert agent["Label"] == BUNDLE_ID
        assert agent["ProgramArguments"] == PROGRAM_ARGS

    def test_custom_label_names_the_plist(self, tmp_path: Path) -> None:
        registrar = LaunchAgentRegistrar(
            agents_dir=tmp_path, program_arguments=["cmd"], label="com.example.other"
        )
        registrar.enable()
        assert (tmp_path / "com.example.other.plist").is_file()

    def test_leaves_no_tmp_sibling_behind(self, tmp_path: Path) -> None:
        # The atomic write goes through a sibling tmp file + os.replace.
        registrar = _registrar(tmp_path)
        registrar.enable()
        assert [p.name for p in registrar.plist_path.parent.iterdir()] == [
            registrar.plist_path.name
        ]

    def test_failed_write_never_corrupts_an_existing_plist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A crash mid-write must not leave a truncated plist that the
        # existence-only is_enabled() reports as registered: the write lands
        # in a tmp sibling, so the registered plist stays parseable.
        registrar = _registrar(tmp_path)
        registrar.enable()

        def _boom(self: Path, data: bytes) -> int:
            self.write_text("truncated garbage", encoding="utf-8")
            raise OSError("disk full mid-write")

        monkeypatch.setattr(type(registrar.plist_path), "write_bytes", _boom)
        with pytest.raises(OSError, match="disk full"):
            registrar.enable()

        agent = _load(registrar.plist_path)
        assert agent["ProgramArguments"] == PROGRAM_ARGS


class TestDisable:
    """disable removes the plist; a no-op when already absent."""

    def test_removes_the_plist(self, tmp_path: Path) -> None:
        registrar = _registrar(tmp_path)
        registrar.enable()
        registrar.disable()
        assert not registrar.plist_path.exists()
        assert not registrar.is_enabled()

    def test_idempotent_when_already_absent(self, tmp_path: Path) -> None:
        registrar = _registrar(tmp_path)
        registrar.disable()  # never enabled — must not raise
        registrar.enable()
        registrar.disable()
        registrar.disable()  # already removed — must not raise
        assert not registrar.is_enabled()


class TestIsEnabled:
    """is_enabled reflects the plist file's existence."""

    def test_false_before_enable(self, tmp_path: Path) -> None:
        assert _registrar(tmp_path).is_enabled() is False

    def test_tracks_enable_and_disable(self, tmp_path: Path) -> None:
        registrar = _registrar(tmp_path)
        registrar.enable()
        assert registrar.is_enabled() is True
        registrar.disable()
        assert registrar.is_enabled() is False


class TestReconcileIntegration:
    """One composition smoke test: the daemon drives this registrar through
    the pure reconcile decision. The full ENABLE/NOOP/DISABLE table lives in
    test_autostart_reconcile.py — never duplicated here."""

    def test_apply_autostart_enables_through_registrar(self, tmp_path: Path) -> None:
        registrar = _registrar(tmp_path)
        action = apply_autostart(desired=True, registrar=registrar)
        assert action is AutostartAction.ENABLE
        assert registrar.is_enabled() is True
