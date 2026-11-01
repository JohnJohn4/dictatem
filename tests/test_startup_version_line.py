"""The daemon logs one build-identity line at startup (#201)."""

from __future__ import annotations

from dictatem.daemon import startup_version_line


def test_includes_version_python_platform_and_arch() -> None:
    line = startup_version_line(
        "0.6.3", python_version="3.11.9", platform_name="win32", machine="AMD64"
    )
    assert line == "Dictatem v0.6.3 starting — Python 3.11.9, win32, AMD64"


def test_unreadable_version_is_labelled_not_blank() -> None:
    line = startup_version_line(
        None, python_version="3.12.4", platform_name="darwin", machine="arm64"
    )
    assert "unknown version" in line
    assert "v None" not in line
    assert line.startswith("Dictatem ")


def test_empty_machine_is_labelled() -> None:
    line = startup_version_line(
        "1.0.0", python_version="3.12.4", platform_name="linux", machine=""
    )
    assert line.endswith("unknown arch")
