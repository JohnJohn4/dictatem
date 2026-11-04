"""Start-menu shortcut: the installer creates it, ``--uninstall`` removes it."""

from __future__ import annotations

from pathlib import Path

from dictatem.process.win32_start_menu import (
    SHORTCUT_NAME,
    remove_start_menu_shortcut,
    start_menu_shortcut_path,
)

_SCRIPT = (Path(__file__).resolve().parents[1] / "install.ps1").read_text(encoding="utf-8")


def test_shortcut_lives_in_the_per_user_start_menu(tmp_path: Path) -> None:
    path = start_menu_shortcut_path(str(tmp_path))
    assert path == tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Dictatem.lnk"


def test_no_appdata_means_no_path() -> None:
    assert start_menu_shortcut_path("") is None


def test_remove_deletes_an_existing_shortcut(tmp_path: Path) -> None:
    path = start_menu_shortcut_path(str(tmp_path))
    assert path is not None
    path.parent.mkdir(parents=True)
    path.write_bytes(b"lnk")
    assert remove_start_menu_shortcut(path) is True
    assert not path.exists()


def test_remove_is_a_no_op_when_absent(tmp_path: Path) -> None:
    assert remove_start_menu_shortcut(tmp_path / SHORTCUT_NAME) is False
    assert remove_start_menu_shortcut(None) is False


def test_installer_creates_the_shortcut_before_launching() -> None:
    created = _SCRIPT.index("CreateShortcut((Join-Path $programsDir 'Dictatem.lnk'))")
    launch = _SCRIPT.index("Start-Process -FilePath 'dictatem'")
    assert created < launch


def test_installer_shortcut_is_best_effort_and_targets_the_windowless_launcher() -> None:
    start = _SCRIPT.index("# --- 3.4 Start-menu shortcut")
    block = _SCRIPT[start : _SCRIPT.index("# --- 3.5", start)]
    assert block.count("try {") == 1
    assert "} catch {" in block
    assert "'dictatem.exe'" in block
    assert "GetFolderPath('Programs')" in block  # per-user, no admin
