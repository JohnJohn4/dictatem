"""DaemonCore surfaces the Config Load Report and never writes an unreadable config (#238)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dictatem.config import (
    ConfigLoadReport,
    ConfigProblem,
    load_config_with_report,
    write_config,
)
from dictatem.daemon import DaemonCore
from dictatem.state import StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from tests.fakes import (
    FakeAudioCapture,
    FakeAutostartRegistrar,
    FakeOverlayRenderer,
    FakeTranscriberBackend,
    FakeTrayRenderer,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _core(
    *,
    config_read_only: bool = False,
    registrar: FakeAutostartRegistrar | None = None,
    persisted: list[bool] | None = None,
) -> tuple[DaemonCore, FakeTrayRenderer]:
    tray = FakeTrayRenderer()
    core = DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(
            backend=FakeTranscriberBackend(result="hi"), clock=lambda: 0.0
        ),
        overlay=FakeOverlayRenderer(),
        tray=tray,
        autostart_registrar=registrar,
        persist_autostart=persisted.append if persisted is not None else None,
        config_read_only=config_read_only,
    )
    return core, tray


class TestStartupNotification:
    def test_non_empty_report_gives_exactly_one_notification(self) -> None:
        core, tray = _core()
        core.notify_config_problems(ConfigLoadReport(problems=[
            ConfigProblem("[hotkey].tap_threshold_ms", "Wrong type"),
            ConfigProblem("[audio].sample_rate", "Invalid value"),
        ]))
        assert len(tray.notifications) == 1
        _title, body = tray.notifications[0]
        assert "[hotkey].tap_threshold_ms" in body
        assert "Open config file" in body

    def test_full_detail_goes_to_the_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # The toast is kept short enough not to truncate (#280); every key
        # and the "file was not changed" promise live in daemon.log instead.
        core, _tray = _core()
        with caplog.at_level(logging.WARNING, logger="dictatem.daemon"):
            core.notify_config_problems(ConfigLoadReport(problems=[
                ConfigProblem("[hotkey].tap_threshold_ms", "Wrong type"),
                ConfigProblem("[audio].sample_rate", "Invalid value"),
                ConfigProblem("[overlay].position", "Invalid value"),
            ]))
        text = caplog.text
        assert "[hotkey].tap_threshold_ms" in text
        assert "[audio].sample_rate" in text
        assert "[overlay].position" in text
        assert "not changed" in text

    def test_valid_config_gives_no_notification(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        core, tray = _core()
        with caplog.at_level(logging.WARNING, logger="dictatem.daemon"):
            core.notify_config_problems(ConfigLoadReport())
        assert tray.notifications == []
        assert caplog.records == []


class TestStartAtLoginWithUnreadableConfig:
    def test_toggle_applies_for_session_without_writing_and_notifies(self) -> None:
        registrar = FakeAutostartRegistrar(enabled=True)
        persisted: list[bool] = []
        core, tray = _core(
            config_read_only=True, registrar=registrar, persisted=persisted
        )
        core.on_tray_set_autostart(False)
        assert registrar.is_enabled() is False  # applied for this session
        assert persisted == []  # the config writer was never called
        assert len(tray.notifications) == 1
        _title, body = tray.notifications[0]
        assert "this session" in body
        assert "not changed" in body

    def test_readable_config_still_persists_without_notification(self) -> None:
        registrar = FakeAutostartRegistrar(enabled=True)
        persisted: list[bool] = []
        core, tray = _core(registrar=registrar, persisted=persisted)
        core.on_tray_set_autostart(False)
        assert persisted == [False]
        assert tray.notifications == []


class TestStartAtLoginWithAPerKeyProblem:
    """A wrong-type value is a problem too: the file must stay byte-identical.

    The startup notice promises "Your config.toml was not changed", so the
    Start-at-login toggle may not rewrite it (dropping comments and replacing
    the user's value with the default) for the rest of that session.
    """

    def test_toggle_leaves_file_bytes_unchanged_and_notifies(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "config.toml"
        original = (
            b'# my settings\n[hotkey]\ntap_threshold_ms = "fast"\n'
            b"[startup]\nautostart = true\n"
        )
        path.write_bytes(original)
        config, report = load_config_with_report(path)
        assert not report.is_empty and not report.read_only

        def persist(enabled: bool) -> None:
            config.startup.autostart = enabled
            write_config(config, path)

        registrar = FakeAutostartRegistrar(enabled=True)
        tray = FakeTrayRenderer()
        core = DaemonCore(
            state_machine=StateMachine(tap_threshold_ms=200),
            audio_capture=FakeAudioCapture(duration_s=1.0),
            lifecycle=TranscribeLifecycle(
                backend=FakeTranscriberBackend(result="hi"), clock=lambda: 0.0
            ),
            overlay=FakeOverlayRenderer(),
            tray=tray,
            autostart_registrar=registrar,
            persist_autostart=persist,
            config_read_only=report.write_protected,
        )
        core.on_tray_set_autostart(False)

        assert path.read_bytes() == original
        assert registrar.is_enabled() is False  # applied for this session
        assert len(tray.notifications) == 1
        _title, body = tray.notifications[0]
        assert "this session" in body
        assert "not changed" in body
