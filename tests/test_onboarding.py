"""Tests for the first-run Usage Guide auto-open gate (#122 / ADR-0021).

The gate decision and the marker path/write are pure (filesystem only, no Qt) so
they're unit-tested here; the daemon's Qt open + on-show mark is manual-QA.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dictatem.onboarding import (
    daemon_ready_marker,
    mark_usage_guide_seen,
    should_auto_open_usage_guide,
    usage_guide_seen_marker,
    write_daemon_ready_marker,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestUsageGuideSeenMarker:
    def test_marker_path_under_dictatem_home(self, tmp_path: Path) -> None:
        marker = usage_guide_seen_marker(tmp_path)
        assert marker == tmp_path / ".dictatem" / ".usage_guide_seen"


class TestShouldAutoOpen:
    def test_opens_on_first_run_when_marker_absent(self, tmp_path: Path) -> None:
        marker = tmp_path / ".usage_guide_seen"
        assert should_auto_open_usage_guide(
            marker_path=marker, permissions_pending=False
        )

    def test_does_not_open_when_marker_present(self, tmp_path: Path) -> None:
        marker = tmp_path / ".usage_guide_seen"
        marker.touch()
        assert not should_auto_open_usage_guide(
            marker_path=marker, permissions_pending=False
        )

    def test_deferred_while_permissions_pending(self, tmp_path: Path) -> None:
        # macOS: a grant relaunches the daemon, so defer rather than compete with
        # the permission dialog. The marker stays absent (unseen), so the next
        # clean launch still shows it.
        marker = tmp_path / ".usage_guide_seen"
        assert not should_auto_open_usage_guide(
            marker_path=marker, permissions_pending=True
        )

    def test_does_not_open_when_seen_and_pending(self, tmp_path: Path) -> None:
        marker = tmp_path / ".usage_guide_seen"
        marker.touch()
        assert not should_auto_open_usage_guide(
            marker_path=marker, permissions_pending=True
        )


class TestMarkUsageGuideSeen:
    def test_writes_marker_creating_parent(self, tmp_path: Path) -> None:
        marker = usage_guide_seen_marker(tmp_path)
        assert not marker.exists()
        mark_usage_guide_seen(marker)
        assert marker.exists()

    def test_mark_then_gate_returns_false(self, tmp_path: Path) -> None:
        # The round trip: after a show + mark, a later launch must not re-open.
        marker = usage_guide_seen_marker(tmp_path)
        assert should_auto_open_usage_guide(
            marker_path=marker, permissions_pending=False
        )
        mark_usage_guide_seen(marker)
        assert not should_auto_open_usage_guide(
            marker_path=marker, permissions_pending=False
        )

    def test_idempotent(self, tmp_path: Path) -> None:
        marker = usage_guide_seen_marker(tmp_path)
        mark_usage_guide_seen(marker)
        mark_usage_guide_seen(marker)  # a second call must not raise
        assert marker.exists()

    def test_unwritable_home_degrades_without_raising(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        # A plain file where the marker's parent dir should be makes mkdir raise
        # OSError (FileExistsError). The write must log-and-degrade, never crash
        # the daemon — at worst onboarding re-shows next launch.
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir", encoding="utf-8")
        marker = blocker / ".usage_guide_seen"
        with caplog.at_level(logging.WARNING, logger="dictatem.onboarding"):
            mark_usage_guide_seen(marker)  # must not raise
        assert not marker.exists()
        assert any(r.levelname == "WARNING" for r in caplog.records)


class TestDaemonReadyMarker:
    """The installer waits on this marker to know the menu-bar icon is up (#95)."""

    def test_marker_path_under_dictatem_home(self, tmp_path: Path) -> None:
        assert daemon_ready_marker(tmp_path) == tmp_path / ".dictatem" / ".daemon_ready"

    def test_path_matches_the_one_install_sh_waits_on(self) -> None:
        # install.sh hardcodes the same path; the two must never drift.
        from pathlib import Path as _Path

        script = (_Path(__file__).resolve().parents[1] / "install.sh").read_text(
            encoding="utf-8"
        )
        assert 'ready_marker="$HOME/.dictatem/.daemon_ready"' in script

    def test_write_records_the_pid_creating_parent(self, tmp_path: Path) -> None:
        marker = daemon_ready_marker(tmp_path)
        write_daemon_ready_marker(marker, pid=4242)
        assert marker.read_text(encoding="ascii").strip() == "4242"

    def test_rewrite_overwrites(self, tmp_path: Path) -> None:
        marker = daemon_ready_marker(tmp_path)
        write_daemon_ready_marker(marker, pid=1)
        write_daemon_ready_marker(marker, pid=2)
        assert marker.read_text(encoding="ascii").strip() == "2"

    def test_unwritable_home_degrades_without_raising(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="dictatem.onboarding"):
            write_daemon_ready_marker(blocker / ".daemon_ready", pid=1)
        assert any(r.levelname == "WARNING" for r in caplog.records)
