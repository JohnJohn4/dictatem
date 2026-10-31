"""DaemonCore surfaces the Config Load Report and never writes an unreadable config (#238)."""

from __future__ import annotations

from dictatem.config import ConfigLoadReport, ConfigProblem
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
        assert "not changed" in body

    def test_valid_config_gives_no_notification(self) -> None:
        core, tray = _core()
        core.notify_config_problems(ConfigLoadReport())
        assert tray.notifications == []


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
