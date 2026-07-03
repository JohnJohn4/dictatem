"""Import-safety tests — two complementary directions.

1. :class:`TestImportSafety` guards the **pure core**: importing dictatem's
   pure modules must never transitively pull in heavy or platform-only
   dependencies (pywin32, PySide6, faster-whisper, …). This keeps the
   decision logic importable — and unit-testable — on any OS without the
   native stack.

2. :class:`TestNativeAdaptersImport` guards the **native adapters**: on each
   platform, every native adapter for *that* platform must import cleanly, so a
   broken ``pywin32`` / PyObjC binding fails in CI (the windows-latest and
   macos-latest legs, #81 / ADR-0018) rather than at runtime on a user's machine.
"""

import importlib
import sys
from pathlib import Path

import pytest

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
    "dictatem.logpaths",
    "dictatem.paste",
    "dictatem.paste.pipeline",
    "dictatem.state",
    "dictatem.hardware.mac_probe",
    "dictatem.hotkey.classifier",
    "dictatem.hotkey.mac_keymap",
    "dictatem.audio",
    "dictatem.audio.buffer",
    # The resampler is shared with the Windows WASAPI switch (#184); it must stay
    # pure numpy and never pull in an audio stack.
    "dictatem.audio.resampler",
    "dictatem.transcribe",
    "dictatem.transcribe.lifecycle",
    "dictatem.overlay.state",
    "dictatem.tray",
    "dictatem.tray.state",
    "dictatem.autostart.launch_agent",
    "dictatem.macapp",
    "dictatem.macapp.bundle",
    "dictatem.macapp.plist",
    "dictatem.permissions",
    "dictatem.permissions.mapper",
]

# A known native adapter per platform. The discovery glob below must surface
# these, otherwise a rename (or a broken glob) would turn the import test into a
# vacuous pass — so they double as a smoke check that discovery actually worked.
NATIVE_ADAPTER_SENTINELS = {
    "win32": ["dictatem.hotkey.wh_keyboard_ll", "dictatem.paste.win32_clipboard"],
    "darwin": ["dictatem.hotkey.mac_hook", "dictatem.paste.mac_clipboard"],
}


def _native_adapter_modules() -> list[str]:
    """Native adapter modules expected to import on the *current* platform.

    Discovered by glob so a newly-added adapter is covered automatically:
    ``win32_*`` / ``wh_*`` on Windows, ``mac_*`` on macOS (plus the macOS-only
    ``macapp.activation``, which is PyObjC-backed but not ``mac_``-prefixed).
    Each genuinely-native module imports its OS bindings at module level and
    raises off-platform, so the list is empty on any other OS.
    """
    import dictatem

    pkg_root = Path(dictatem.__file__).resolve().parent
    src_root = pkg_root.parent

    if sys.platform == "win32":
        patterns = ["win32_*.py", "wh_*.py"]
        extra: list[str] = []
    elif sys.platform == "darwin":
        patterns = ["mac_*.py"]
        extra = ["dictatem.macapp.activation"]
    else:
        return []

    mods = set(extra)
    for pattern in patterns:
        for path in pkg_root.rglob(pattern):
            rel = path.relative_to(src_root).with_suffix("")
            mods.add(".".join(rel.parts))
    return sorted(mods)


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


class TestNativeAdaptersImport:
    """Each platform's native adapters must import on that platform (#81)."""

    def test_native_adapters_import(self) -> None:
        sentinels = NATIVE_ADAPTER_SENTINELS.get(sys.platform)
        if sentinels is None:
            pytest.skip(f"no native adapters expected on {sys.platform}")

        modules = _native_adapter_modules()
        # Discovery must have found the known adapters, or it silently matched
        # nothing and the import loop below would be a no-op.
        missing = [s for s in sentinels if s not in modules]
        assert not missing, (
            f"native-adapter discovery missed expected module(s): {missing} "
            f"(discovered: {modules})"
        )

        for mod_name in modules:
            # A broken pywin32 / PyObjC import surfaces here as ImportError,
            # naming the offending adapter, instead of at runtime on a user box.
            importlib.import_module(mod_name)
