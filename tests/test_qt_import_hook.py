"""PySide6's import hook skips the source scan for non-dictatem modules."""

from __future__ import annotations

import types

from dictatem.qt_import_hook import limit_pyside_source_scan


def _fake_feature() -> tuple[types.SimpleNamespace, list[str]]:
    scanned: list[str] = []

    def _mod_uses_pyside(module: object) -> bool:
        scanned.append(getattr(module, "__name__", "?"))
        return True

    return types.SimpleNamespace(_mod_uses_pyside=_mod_uses_pyside), scanned


def test_other_packages_are_not_source_scanned() -> None:
    feature, scanned = _fake_feature()
    assert limit_pyside_source_scan({"shibokensupport.feature": feature})

    assert feature._mod_uses_pyside(types.ModuleType("huggingface_hub.hf_api")) is False
    assert feature._mod_uses_pyside(types.ModuleType("dictatemx")) is False
    assert scanned == []


def test_dictatem_modules_keep_the_original_check() -> None:
    feature, scanned = _fake_feature()
    limit_pyside_source_scan({"shibokensupport.feature": feature})

    assert feature._mod_uses_pyside(types.ModuleType("dictatem.tray.qt_tray")) is True
    assert feature._mod_uses_pyside(types.ModuleType("dictatem")) is True
    assert scanned == ["dictatem.tray.qt_tray", "dictatem"]


def test_idempotent() -> None:
    feature, scanned = _fake_feature()
    limit_pyside_source_scan({"shibokensupport.feature": feature})
    patched = feature._mod_uses_pyside
    assert limit_pyside_source_scan({"shibokensupport.feature": feature})
    assert feature._mod_uses_pyside is patched


def test_missing_hook_is_a_no_op() -> None:
    assert limit_pyside_source_scan({}) is False
    assert limit_pyside_source_scan({"shibokensupport.feature": object()}) is False


def test_real_pyside6_hook_is_patched() -> None:
    import sys

    import pytest

    pytest.importorskip("PySide6.QtCore")
    if "shibokensupport.feature" not in sys.modules:
        pytest.skip("this PySide6 build has no feature hook")
    assert limit_pyside_source_scan() is True
