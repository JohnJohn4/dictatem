"""Tests for the single-instance guard (#92).

``_acquire_single_instance_lock`` is the testable core of the guard wired into
``_run_daemon``: the daemon must refuse to start a second instance (two
daemons each register the global hotkey hook and paste every dictation twice),
while a lock left behind by a crashed daemon must never block a fresh start.

The acquisition is backed by ``QtCore.QLockFile``; these tests exercise the
real thing rather than a fake so the stale-lock and contention semantics we
rely on are the ones Qt actually provides.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from dictatem.daemon import _acquire_single_instance_lock

if TYPE_CHECKING:
    from pathlib import Path


def _release(lock: object) -> None:
    lock.unlock()  # type: ignore[attr-defined]


class TestSingleInstanceGuard:
    def test_fresh_acquire_returns_a_lock(self, tmp_path: Path) -> None:
        lock = _acquire_single_instance_lock(tmp_path / "daemon.lock")
        try:
            assert lock is not None
        finally:
            if lock is not None:
                _release(lock)

    def test_creates_missing_parent_directory(self, tmp_path: Path) -> None:
        # The guard runs before config load on first run, so ~/.dictatem may
        # not exist yet — it must create the directory, not fail.
        lock_path = tmp_path / "nonexistent" / "daemon.lock"
        lock = _acquire_single_instance_lock(lock_path)
        try:
            assert lock is not None
            assert lock_path.parent.is_dir()
        finally:
            if lock is not None:
                _release(lock)

    def test_second_acquire_while_held_returns_none(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "daemon.lock"
        first = _acquire_single_instance_lock(lock_path)
        try:
            assert first is not None  # keep it alive across the second attempt
            second = _acquire_single_instance_lock(lock_path)
            assert second is None
        finally:
            if first is not None:
                _release(first)

    def test_reacquire_after_release(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "daemon.lock"
        first = _acquire_single_instance_lock(lock_path)
        assert first is not None
        _release(first)

        # A cleanly-stopped daemon releases the lock, so the next launch must
        # be able to acquire it again.
        second = _acquire_single_instance_lock(lock_path)
        try:
            assert second is not None
        finally:
            if second is not None:
                _release(second)

    def test_stale_lock_from_crashed_daemon_is_stolen(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "daemon.lock"

        # A child acquires the lock then hard-exits without unlocking, leaving
        # the lock file behind with a now-dead PID — exactly the residue a
        # kill -9'd daemon leaves. QLockFile records the creating PID and steals
        # a lock whose owner is gone, so a fresh start must not deadlock.
        child = (
            "import sys, os\n"
            "from PySide6.QtCore import QLockFile\n"
            "lk = QLockFile(sys.argv[1])\n"
            "assert lk.tryLock(0)\n"
            "os._exit(0)\n"
        )
        subprocess.run(
            [sys.executable, "-c", child, str(lock_path)], check=True
        )
        assert lock_path.exists(), "crashed child should leave the lock file behind"

        lock = _acquire_single_instance_lock(lock_path)
        try:
            assert lock is not None
        finally:
            if lock is not None:
                _release(lock)

    def test_unestablishable_lock_path_degrades_without_blocking_start(
        self, tmp_path: Path
    ) -> None:
        # If the lock file cannot be ESTABLISHED at all — here the parent "dir"
        # is actually a file, so mkdir fails — the guard must DEGRADE (return a
        # non-None lock so the daemon starts), not block startup or raise. #92
        # must never be the reason a daemon fails to start (cf. ADR-0023's
        # best-effort clipboard markers); only a genuinely-held lock returns None.
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("x")
        lock = _acquire_single_instance_lock(blocker / "daemon.lock")
        assert lock is not None  # degraded → proceed, not a silent "already running"
