"""Tests verifying that importing dictatem modules never transitively imports
heavy or Windows-only dependencies on Linux.
"""

import importlib
import sys

FORBIDDEN_MODULES = [
    "pywin32",
    "win32api",
    "win32con",
    "win32clipboard",
    "win32gui",
    "pywintypes",
    "PySide6",
    "sounddevice",
    "faster_whisper",
    "ctranslate2",
]

DICTATEM_MODULES = [
    "dictatem",
    "dictatem.types",
    "dictatem.config",
    "dictatem.interfaces",
    "dictatem.exceptions",
    "dictatem.daemon",
    "dictatem.tray",
    "dictatem.tray.state",
]


class TestImportSafety:
    def test_no_forbidden_transitive_imports(self) -> None:
        before = set(sys.modules.keys())
        for mod_name in DICTATEM_MODULES:
            importlib.import_module(mod_name)
        after = set(sys.modules.keys())
        new_modules = after - before
        for forbidden in FORBIDDEN_MODULES:
            violations = [
                m for m in new_modules
                if m == forbidden or m.startswith(forbidden + ".")
            ]
            assert violations == [], (
                f"Importing dictatem modules pulled in forbidden module(s): {violations}"
            )
