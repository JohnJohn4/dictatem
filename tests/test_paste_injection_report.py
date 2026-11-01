"""The pipeline asks a diagnostics-capable sender for its per-injection line (#269)."""

from __future__ import annotations

import logging

import pytest

from dictatem.interfaces import InjectionDiagnostics, KeystrokeSender
from dictatem.paste.pipeline import paste
from tests.fakes import FakeClipboardIO, FakeForegroundTracker, FakeKeystrokeSender


class _DiagnosingSender(FakeKeystrokeSender):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail
        self.reports: list[tuple[int, str]] = []

    def report_injection(self, target_id: int, kind: str) -> None:
        self.events.append(("report", kind))
        self.reports.append((target_id, kind))
        if self.fail:
            raise RuntimeError("diagnostics blew up")


def _paste(ks: FakeKeystrokeSender, *, replace: int = 0, target: int = 7) -> FakeClipboardIO:
    clip = FakeClipboardIO()
    paste(
        "secret words",
        clipboard=clip,
        keystroke=ks,
        foreground=FakeForegroundTracker(target_id=target),
        replace_chars=replace,
        target_id=target,
        schedule_restore=lambda _d, _cb: None,
    )
    return clip


def test_protocol_shape() -> None:
    ks = _DiagnosingSender()
    assert isinstance(ks, InjectionDiagnostics)
    assert isinstance(ks, KeystrokeSender)
    assert not isinstance(FakeKeystrokeSender(), InjectionDiagnostics)


def test_regular_paste_reports_right_after_ctrl_v() -> None:
    ks = _DiagnosingSender()
    _paste(ks, target=42)
    assert ks.reports == [(42, "paste")]
    assert ks.events == [("paste", 1), ("report", "paste")]


def test_trigger_fire_reports_after_typed_text() -> None:
    ks = _DiagnosingSender()
    _paste(ks, replace=3, target=9)
    assert ks.reports == [(9, "trigger-fire")]
    assert [e[0] for e in ks.events] == ["backspaces", "send_text", "report"]


def test_plain_sender_is_not_asked() -> None:
    ks = FakeKeystrokeSender()
    _paste(ks)
    assert ks.paste_count == 1


@pytest.mark.parametrize("replace", [0, 3])
def test_diagnostics_failure_never_breaks_the_paste(
    replace: int, caplog: pytest.LogCaptureFixture
) -> None:
    ks = _DiagnosingSender(fail=True)
    with caplog.at_level(logging.DEBUG, logger="dictatem.paste.pipeline"):
        _paste(ks, replace=replace)
    failures = [r for r in caplog.records if "diagnostics failed" in r.getMessage()]
    assert failures and all(r.levelno == logging.DEBUG for r in failures)
    assert "Paste: sent" in caplog.text or "typed-replacement complete" in caplog.text
    assert "secret" not in caplog.text
