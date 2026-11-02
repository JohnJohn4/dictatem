"""Guard the PySide6 meta -> PySide6-Essentials swap and its upgrade migration.

dictatem only uses QtCore/QtGui/QtWidgets, so it depends on PySide6-Essentials
rather than the ``PySide6`` meta package (which adds ~450 MB of Addons/WebEngine).
The meta and Essentials wheels share ``PySide6/__init__.py``, so an in-place
upgrade from a meta-based install (<= v0.7.0) that uninstalls the meta breaks Qt
unless Essentials is reinstalled in the same uv transaction. Both installers
carry that one-time migration; these tests keep the pieces from drifting apart.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO / "pyproject.toml"
_INSTALLERS = [_REPO / "install.ps1", _REPO / "install.sh"]
_QT_MODULES_IN_ESSENTIALS = {"QtCore", "QtGui", "QtWidgets", "QtSvg", "QtNetwork"}


def _runtime_requirement_names() -> list[str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    reqs = data["project"]["optional-dependencies"]["runtime"]
    return [re.split(r"[\s<>=!~;\[]", r, maxsplit=1)[0].lower() for r in reqs]


def test_runtime_depends_on_essentials_not_the_meta_package() -> None:
    names = _runtime_requirement_names()
    assert "pyside6-essentials" in names
    assert "pyside6" not in names, (
        "the PySide6 meta package pulls ~450 MB of unused Addons; depend on "
        "PySide6-Essentials (add PySide6-Addons explicitly if a module needs it)"
    )


def test_source_only_imports_qt_modules_shipped_in_essentials() -> None:
    used: set[str] = set()
    for path in (_REPO / "src").rglob("*.py"):
        used |= set(re.findall(r"PySide6\.(Qt\w+)", path.read_text(encoding="utf-8")))
    assert used, "expected some PySide6 imports under src/"
    assert used <= _QT_MODULES_IN_ESSENTIALS, (
        f"Qt module(s) {sorted(used - _QT_MODULES_IN_ESSENTIALS)} are not in "
        "PySide6-Essentials; add PySide6-Addons to the runtime extra"
    )


def test_installers_migrate_meta_based_envs_by_reinstalling_essentials() -> None:
    for installer in _INSTALLERS:
        text = installer.read_text(encoding="utf-8")
        assert "--reinstall-package" in text and "pyside6-essentials" in text, (
            f"{installer.name} lost the one-time PySide6 meta -> Essentials "
            "migration; an in-place upgrade from <= v0.7.0 would break Qt"
        )
