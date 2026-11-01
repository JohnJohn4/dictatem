"""Windows AppUserModelID for toast attribution — pure decisions + orchestration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from dictatem.assets import asset_path
from dictatem.process.app_identity import (
    APP_USER_MODEL_ID,
    DISPLAY_NAME,
    ICON_ASSET,
    apply_app_identity,
    aumid_registry_subkey,
    aumid_registry_values,
    remove_app_identity,
)


def test_stable_id_and_key() -> None:
    assert APP_USER_MODEL_ID == "Matavex.Dictatem"
    assert aumid_registry_subkey() == r"Software\Classes\AppUserModelId\Matavex.Dictatem"


def test_values() -> None:
    icon = Path(r"C:\x\icon-256.png")
    assert aumid_registry_values(icon) == {"DisplayName": DISPLAY_NAME, "IconUri": str(icon)}
    assert DISPLAY_NAME == "Dictatem"


def test_bundled_icon_exists_and_is_png() -> None:
    icon = asset_path(ICON_ASSET)
    assert icon.is_file()
    assert icon.suffix == ".png"


def test_apply_sets_id_then_registers() -> None:
    calls: list[tuple[str, object]] = []
    icon = Path("icon.png")
    apply_app_identity(
        set_process_app_id=lambda app_id: calls.append(("id", app_id)),
        write_registration=lambda key, values: calls.append(("reg", (key, dict(values)))),
        icon_path=icon,
    )
    assert calls == [
        ("id", APP_USER_MODEL_ID),
        ("reg", (aumid_registry_subkey(), aumid_registry_values(icon))),
    ]


def test_apply_is_idempotent() -> None:
    writes: list[dict[str, str]] = []
    for _ in range(2):
        apply_app_identity(
            set_process_app_id=lambda _id: None,
            write_registration=lambda _k, v: writes.append(dict(v)),
            icon_path=Path("icon.png"),
        )
    assert writes[0] == writes[1]


def test_apply_never_raises_and_still_registers(caplog: pytest.LogCaptureFixture) -> None:
    registered: list[str] = []

    def fail_id(_id: str) -> None:
        raise OSError("E_FAIL")

    def fail_reg(key: str, _values: object) -> None:
        registered.append(key)
        raise PermissionError("denied")

    with caplog.at_level(logging.WARNING):
        apply_app_identity(
            set_process_app_id=fail_id, write_registration=fail_reg, icon_path=Path("i.png")
        )
    assert registered == [aumid_registry_subkey()]  # attempted despite the ID failure
    assert len(caplog.records) == 2


def test_apply_without_icon_skips_registration() -> None:
    ids: list[str] = []
    regs: list[str] = []
    apply_app_identity(
        set_process_app_id=ids.append,
        write_registration=lambda k, _v: regs.append(k),
        icon_path=None,
    )
    assert ids == [APP_USER_MODEL_ID]
    assert regs == []


def test_remove_deletes_key_and_never_raises() -> None:
    deleted: list[str] = []
    remove_app_identity(delete_registration=deleted.append)
    assert deleted == [aumid_registry_subkey()]

    def boom(_key: str) -> None:
        raise OSError("nope")

    remove_app_identity(delete_registration=boom)  # must not raise


@pytest.mark.skipif(sys.platform != "win32", reason="winreg adapter is Windows-only")
def test_win32_registration_roundtrip_under_a_scratch_key() -> None:
    """The real winreg glue, against a throwaway HKCU key (never the real AUMID)."""
    import winreg

    from dictatem.process.win32_app_identity import delete_registration, write_registration

    subkey = r"Software\Classes\AppUserModelId\Matavex.Dictatem.Test-" + str(id(object()))
    values = aumid_registry_values(asset_path(ICON_ASSET))
    try:
        write_registration(subkey, values)
        write_registration(subkey, values)  # idempotent
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            assert winreg.QueryValueEx(key, "DisplayName")[0] == "Dictatem"
            assert winreg.QueryValueEx(key, "IconUri")[0] == values["IconUri"]
    finally:
        delete_registration(subkey)
    delete_registration(subkey)  # already absent: no error
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey)
