"""Unit tests for the pure macOS Info.plist renderer (#61 / ADR-0014).

The .app identity shell's Info.plist carries the stable bundle id TCC binds
permission grants to. The renderer is pure (string in, XML string out, no
filesystem), so its exact contents are asserted here on any OS. We parse the
output with the stdlib ``plistlib`` to prove it's well-formed and round-trips.
"""

from __future__ import annotations

import plistlib

from dictatem.macos.info_plist import (
    BUNDLE_DISPLAY_NAME,
    BUNDLE_ID,
    BundleInfo,
    render_info_plist,
)


class TestRendersValidPlist:
    def test_output_parses_as_plist(self) -> None:
        xml = render_info_plist(BundleInfo())
        parsed = plistlib.loads(xml.encode("utf-8"))
        assert isinstance(parsed, dict)

    def test_starts_with_xml_declaration(self) -> None:
        xml = render_info_plist(BundleInfo())
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')


class TestStableIdentity:
    def test_bundle_identifier_is_the_stable_id(self) -> None:
        parsed = plistlib.loads(render_info_plist(BundleInfo()).encode("utf-8"))
        assert parsed["CFBundleIdentifier"] == BUNDLE_ID

    def test_default_bundle_id_is_reverse_dns(self) -> None:
        # TCC binds to this; assert the canonical value so an accidental change
        # (which would void grants on upgrade) fails the test.
        assert BUNDLE_ID == "com.dictatem.Dictatem"

    def test_display_name_is_dictatem(self) -> None:
        parsed = plistlib.loads(render_info_plist(BundleInfo()).encode("utf-8"))
        assert parsed["CFBundleName"] == BUNDLE_DISPLAY_NAME
        assert parsed["CFBundleDisplayName"] == "Dictatem"


class TestBundleLayoutReferences:
    def test_executable_name_matches_default(self) -> None:
        parsed = plistlib.loads(render_info_plist(BundleInfo()).encode("utf-8"))
        assert parsed["CFBundleExecutable"] == "dictatem"

    def test_icon_file_is_the_committed_icns(self) -> None:
        parsed = plistlib.loads(render_info_plist(BundleInfo()).encode("utf-8"))
        assert parsed["CFBundleIconFile"] == "app.icns"

    def test_package_type_is_appl(self) -> None:
        parsed = plistlib.loads(render_info_plist(BundleInfo()).encode("utf-8"))
        assert parsed["CFBundlePackageType"] == "APPL"


class TestMenuBarAgent:
    def test_lsuielement_is_true(self) -> None:
        # Menu-bar agent, no Dock icon (ADR-0006 / ADR-0013).
        parsed = plistlib.loads(render_info_plist(BundleInfo()).encode("utf-8"))
        assert parsed["LSUIElement"] is True


class TestParameterised:
    def test_version_is_stamped_into_both_version_keys(self) -> None:
        parsed = plistlib.loads(
            render_info_plist(BundleInfo(version="1.2.3")).encode("utf-8")
        )
        assert parsed["CFBundleShortVersionString"] == "1.2.3"
        assert parsed["CFBundleVersion"] == "1.2.3"

    def test_custom_bundle_id_is_honoured(self) -> None:
        parsed = plistlib.loads(
            render_info_plist(BundleInfo(bundle_id="com.example.Test")).encode("utf-8")
        )
        assert parsed["CFBundleIdentifier"] == "com.example.Test"

    def test_special_characters_are_escaped(self) -> None:
        # A display name with XML-significant characters must still round-trip.
        xml = render_info_plist(BundleInfo(display_name="A & B <C>"))
        parsed = plistlib.loads(xml.encode("utf-8"))
        assert parsed["CFBundleName"] == "A & B <C>"
