"""Pure Info.plist renderer for the Dictatem ``.app`` shell (#61 / ADR-0014).

Identity inputs (bundle id, name, executable, icon filename) -> plist XML
bytes via stdlib ``plistlib``. No filesystem, no platform calls — the ``.app``
generator writes the returned bytes to ``Contents/Info.plist``; this module
only decides what they say, so it is unit-testable on any OS.
"""

from __future__ import annotations

import plistlib

#: Canonical bundle identifier. This is the *permanent* TCC identity
#: (ADR-0014): macOS binds Accessibility / Input-Monitoring / Microphone
#: grants to it, so changing it later re-prompts every existing user.
BUNDLE_ID = "com.dictatem.daemon"

#: Name shown in Finder, the menu bar, and the System Settings privacy panes.
APP_NAME = "Dictatem"

#: User-facing copy for the one-time macOS microphone (TCC) prompt.
MIC_USAGE_DESCRIPTION = (
    "Dictatem records your voice while the dictation hotkey is held and "
    "transcribes it locally. Audio never leaves this Mac."
)


def render_info_plist(
    *,
    bundle_id: str = BUNDLE_ID,
    name: str = APP_NAME,
    executable: str,
    icon_filename: str,
) -> bytes:
    """Render ``Contents/Info.plist`` for the generated ``.app`` shell.

    *executable* names the ``Contents/MacOS`` shim; *icon_filename* names the
    ``.icns`` placed in ``Contents/Resources`` (the renderer takes the name
    only — it never touches the asset). ``LSUIElement`` makes Dictatem a
    menu-bar app with no Dock icon; ``NSMicrophoneUsageDescription`` is the
    copy macOS shows in the automatic microphone permission prompt.
    """
    info: dict[str, object] = {
        "CFBundleIdentifier": bundle_id,
        "CFBundleName": name,
        "CFBundleDisplayName": name,
        "CFBundleExecutable": executable,
        "CFBundleIconFile": icon_filename,
        "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": MIC_USAGE_DESCRIPTION,
    }
    return plistlib.dumps(info, sort_keys=True)
