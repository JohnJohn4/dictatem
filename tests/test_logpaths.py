"""Tests for the pure per-platform daemon.log path decision (#54)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dictatem.logpaths import daemon_log_path, default_daemon_log_path


class TestWindowsLogPath:
    def test_under_appdata(self) -> None:
        appdata = r"C:\Users\u\AppData\Roaming"
        path = daemon_log_path("win32", {"APPDATA": appdata}, Path(r"C:\Users\u"))
        assert path == Path(appdata) / "Dictatem" / "logs" / "daemon.log"

    def test_none_when_appdata_unset(self) -> None:
        assert daemon_log_path("win32", {}, Path(r"C:\Users\u")) is None

    def test_none_when_appdata_empty(self) -> None:
        assert daemon_log_path("win32", {"APPDATA": ""}, Path(r"C:\Users\u")) is None


class TestMacLogPath:
    def test_under_library_logs(self) -> None:
        home = Path("/Users/u")
        path = daemon_log_path("darwin", {}, home)
        assert path == home / "Library" / "Logs" / "Dictatem" / "daemon.log"


class TestOtherPlatforms:
    def test_no_log_path(self) -> None:
        assert daemon_log_path("linux", {}, Path("/home/u")) is None


class TestDefaultWrapper:
    def test_matches_pure_core_for_this_process(self) -> None:
        # The zero-arg wrapper is the one canonical production spelling; it
        # must agree with the pure core fed this process's ambient values.
        assert default_daemon_log_path() == daemon_log_path(
            sys.platform, os.environ, Path.home()
        )
