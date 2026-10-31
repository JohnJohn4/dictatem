"""The tray updater never runs the installer without an explicit yes (#200, S-1).

``apply_upgrade_decision`` is the confirm-then-start flow the Qt
``UpdateChecker`` delegates to; the dialog itself is a thin manual-QA adapter.
"""

from __future__ import annotations

from dictatem.upgrade.core import (
    GITHUB_REPO,
    UpgradeConfirmation,
    apply_upgrade_decision,
    decide_upgrade,
    upgrade_confirmation,
)


class _Recorder:
    def __init__(self, *, answer: bool) -> None:
        self.answer = answer
        self.asked: list[UpgradeConfirmation] = []
        self.notes: list[str] = []
        self.started: list[str] = []
        self.events: list[str] = []

    def confirm(self, c: UpgradeConfirmation) -> bool:
        self.asked.append(c)
        self.events.append("confirm")
        return self.answer

    def notify(self, _title: str, message: str) -> None:
        self.notes.append(message)
        self.events.append("notify")

    def start(self, tag: str) -> None:
        self.started.append(tag)
        self.events.append("start")

    def run(self, current: str, latest: str | None) -> bool:
        return apply_upgrade_decision(
            decide_upgrade(current, latest),
            current_version=current,
            confirm=self.confirm,
            notify=self.notify,
            start_upgrade=self.start,
        )


class TestApplyUpgradeDecision:
    def test_declined_never_starts_the_installer(self) -> None:
        rec = _Recorder(answer=False)
        assert rec.run("0.6.4", "v0.7.0") is False
        assert rec.started == []
        assert len(rec.asked) == 1
        assert rec.notes and "skipped" in rec.notes[-1]
        assert "v0.7.0" in rec.notes[-1]

    def test_confirmed_starts_after_asking(self) -> None:
        rec = _Recorder(answer=True)
        assert rec.run("0.6.4", "v0.7.0") is True
        assert rec.started == ["v0.7.0"]
        # Asked first, then told it's updating, then the spawn.
        assert rec.events == ["confirm", "notify", "start"]
        assert "v0.7.0" in rec.notes[-1]

    def test_up_to_date_never_asks_or_starts(self) -> None:
        rec = _Recorder(answer=True)
        assert rec.run("0.7.0", "v0.7.0") is False
        assert rec.asked == []
        assert rec.started == []
        assert "up to date" in rec.notes[-1]

    def test_unknown_never_asks_or_starts(self) -> None:
        rec = _Recorder(answer=True)
        assert rec.run("0.6.4", None) is False
        assert rec.asked == []
        assert rec.started == []
        assert rec.notes  # still tells the user something


class TestUpgradeConfirmation:
    def test_names_both_versions_and_source(self) -> None:
        c = upgrade_confirmation("0.6.4", "v0.7.0")
        assert c.title == "Install Dictatem v0.7.0?"
        assert "v0.7.0" in c.text
        assert "v0.6.4" in c.text
        assert f"github.com/{GITHUB_REPO}" in c.text
        assert "install.ps1" in c.text
        assert "restart" in c.text

    def test_current_version_not_double_prefixed(self) -> None:
        c = upgrade_confirmation("v0.6.4", "v0.7.0")
        assert "vv0.6.4" not in c.text
