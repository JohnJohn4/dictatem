"""Tests for the pure Info.plist renderer (#61 / ADR-0014).

The renderer turns identity inputs into plist bytes for the locally-generated
``Dictatem.app`` shell. Every assertion round-trips the bytes through
``plistlib.loads`` and checks keys/values — never string-matching XML.
"""

from __future__ import annotations

import plistlib
from typing import Any

from dictatem.macapp.plist import (
    APP_NAME,
    BUNDLE_ID,
    MIC_USAGE_DESCRIPTION,
    render_info_plist,
)


def _render(**overrides: str) -> dict[str, Any]:
    rendered = render_info_plist(
        executable=overrides.get("executable", "dictatem"),
        icon_filename=overrides.get("icon_filename", "app.icns"),
        bundle_id=overrides.get("bundle_id", BUNDLE_ID),
        name=overrides.get("name", APP_NAME),
    )
    info = plistlib.loads(rendered)
    assert isinstance(info, dict)
    return info


class TestInfoPlistIdentity:
    """The standard CFBundle* identity keys carry the inputs through."""

    def test_identity_keys_round_trip(self) -> None:
        info = _render(
            bundle_id="com.example.test",
            name="TestApp",
            executable="testapp",
            icon_filename="test.icns",
        )
        assert info["CFBundleIdentifier"] == "com.example.test"
        assert info["CFBundleName"] == "TestApp"
        assert info["CFBundleDisplayName"] == "TestApp"
        assert info["CFBundleExecutable"] == "testapp"
        assert info["CFBundleIconFile"] == "test.icns"

    def test_canonical_bundle_id_is_default(self) -> None:
        # The permanent TCC identity — changing it re-prompts every user.
        assert BUNDLE_ID == "com.dictatem.daemon"
        info = _render()
        assert info["CFBundleIdentifier"] == "com.dictatem.daemon"

    def test_app_name_is_default(self) -> None:
        info = _render()
        assert info["CFBundleName"] == APP_NAME == "Dictatem"

    def test_bundle_is_an_application(self) -> None:
        info = _render()
        assert info["CFBundlePackageType"] == "APPL"


class TestInfoPlistMenuBarApp:
    """LSUIElement makes Dictatem a menu-bar app with no Dock icon."""

    def test_lsuielement_is_boolean_true(self) -> None:
        info = _render()
        assert info["LSUIElement"] is True


class TestInfoPlistMicrophonePrompt:
    """NSMicrophoneUsageDescription is the user-facing TCC mic prompt copy."""

    def test_mic_usage_description_present(self) -> None:
        info = _render()
        assert info["NSMicrophoneUsageDescription"] == MIC_USAGE_DESCRIPTION

    def test_mic_usage_copy_is_user_facing_prose(self) -> None:
        info = _render()
        description = info["NSMicrophoneUsageDescription"]
        assert isinstance(description, str)
        assert description.strip()


class TestInfoPlistIsPure:
    """Same inputs -> identical bytes, so the renderer needs no I/O to test."""

    def test_rendering_is_deterministic(self) -> None:
        first = render_info_plist(executable="dictatem", icon_filename="app.icns")
        second = render_info_plist(executable="dictatem", icon_filename="app.icns")
        assert first == second
