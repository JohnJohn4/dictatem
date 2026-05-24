"""Pure Info.plist renderer for the macOS .app identity shell (#61 / ADR-0014).

The locally-generated ``~/Applications/Dictatem.app`` gives TCC a stable identity
so permission grants survive ``uv tool`` upgrades (ADR-0014). The bundle's
``Info.plist`` carries that identity: a stable bundle id, display name, icon
reference, and the ``LSUIElement`` flag (menu-bar agent, no Dock icon).

This renderer is PURE: given the bundle parameters it returns the plist XML as a
string with no filesystem access, so the exact contents are unit-testable on any
OS (mirroring the other pure cores). The thin part — writing the bundle layout to
disk — lives in ``app_bundle.py`` (manual QA only).
"""

from __future__ import annotations

from dataclasses import dataclass

# Stable bundle identifier. TCC binds permission grants to this string, so it
# must NOT change across versions or upgrades void the grants (ADR-0014).
BUNDLE_ID = "com.dictatem.Dictatem"
BUNDLE_DISPLAY_NAME = "Dictatem"
# The Contents/MacOS executable name and the bundled icon file name.
EXECUTABLE_NAME = "dictatem"
ICON_FILE = "app.icns"


@dataclass(frozen=True)
class BundleInfo:
    """The identity fields baked into the .app's Info.plist.

    Defaults are the canonical Dictatem identity; ``version`` is threaded through
    so a release can stamp the bundle. ``executable`` and ``icon_file`` name the
    files inside ``Contents/MacOS`` and ``Contents/Resources``.
    """

    bundle_id: str = BUNDLE_ID
    display_name: str = BUNDLE_DISPLAY_NAME
    executable: str = EXECUTABLE_NAME
    icon_file: str = ICON_FILE
    version: str = "0.1.0"


def _escape(value: str) -> str:
    """XML-escape a plist string value."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_info_plist(info: BundleInfo) -> str:
    """Render *info* to a complete ``Info.plist`` XML document string.

    Pure — no filesystem, no PyObjC. ``LSUIElement`` is ``true`` so the agent
    runs in the menu bar with no Dock icon (ADR-0006 / ADR-0013); ``LSMinimum
    SystemVersion`` is conservative; the icon and executable names match the
    bundle layout ``app_bundle`` writes.
    """
    keys = {
        "CFBundleName": info.display_name,
        "CFBundleDisplayName": info.display_name,
        "CFBundleIdentifier": info.bundle_id,
        "CFBundleExecutable": info.executable,
        "CFBundleIconFile": info.icon_file,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": info.version,
        "CFBundleVersion": info.version,
        "LSMinimumSystemVersion": "12.0",
    }

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
    ]
    for key, value in keys.items():
        lines.append(f"\t<key>{key}</key>")
        lines.append(f"\t<string>{_escape(value)}</string>")
    # LSUIElement is a boolean: a menu-bar agent with no Dock icon.
    lines.append("\t<key>LSUIElement</key>")
    lines.append("\t<true/>")
    lines.append("</dict>")
    lines.append("</plist>")
    return "\n".join(lines) + "\n"
