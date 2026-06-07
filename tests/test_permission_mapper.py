"""Unit tests for the pure macOS permission → guidance mapper.

The mapper turns the set of permissions the native probes found missing
into the exact System Settings deep links and user-facing copy for the
guided dialog — or the empty tuple (no dialog) when nothing is missing. It is
pure: no TCC probing, no AppKit, no I/O, so it runs on any OS. Microphone
is deliberately unmapped (macOS auto-prompts for it). See ADR-0014 and
issue #57.
"""

from __future__ import annotations

import pytest

from dictatem.permissions.mapper import (
    MacPermission,
    PermissionGuidance,
    map_missing_permissions,
)

# The exact deep links from issue #57 / ADR-0014, asserted verbatim so a
# refactor can never silently drift the URLs the dialog opens.
_ACCESSIBILITY_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)
_INPUT_MONITORING_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
)


def _single(missing: set[MacPermission]) -> PermissionGuidance:
    result = map_missing_permissions(missing)
    assert len(result) == 1
    return result[0]


class TestNothingMissing:
    def test_empty_set_signals_no_dialog(self) -> None:
        assert map_missing_permissions(set()) == ()

    def test_empty_frozenset_signals_no_dialog(self) -> None:
        assert map_missing_permissions(frozenset()) == ()


class TestAccessibilityOnly:
    def test_returns_one_accessibility_guidance(self) -> None:
        guidance = _single({MacPermission.ACCESSIBILITY})
        assert guidance.permission is MacPermission.ACCESSIBILITY

    def test_deep_link_is_exactly_the_accessibility_pane(self) -> None:
        guidance = _single({MacPermission.ACCESSIBILITY})
        assert guidance.settings_url == _ACCESSIBILITY_URL

    def test_message_names_the_permission(self) -> None:
        guidance = _single({MacPermission.ACCESSIBILITY})
        assert "Accessibility" in guidance.message


class TestInputMonitoringOnly:
    def test_returns_one_input_monitoring_guidance(self) -> None:
        guidance = _single({MacPermission.INPUT_MONITORING})
        assert guidance.permission is MacPermission.INPUT_MONITORING

    def test_deep_link_is_exactly_the_input_monitoring_pane(self) -> None:
        guidance = _single({MacPermission.INPUT_MONITORING})
        assert guidance.settings_url == _INPUT_MONITORING_URL

    def test_message_names_the_permission(self) -> None:
        guidance = _single({MacPermission.INPUT_MONITORING})
        assert "Input Monitoring" in guidance.message


class TestBothMissing:
    def test_returns_guidance_for_each_in_declaration_order(self) -> None:
        result = map_missing_permissions(
            {MacPermission.INPUT_MONITORING, MacPermission.ACCESSIBILITY}
        )
        assert [g.permission for g in result] == [
            MacPermission.ACCESSIBILITY,
            MacPermission.INPUT_MONITORING,
        ]

    def test_each_guidance_carries_its_own_deep_link(self) -> None:
        result = map_missing_permissions(set(MacPermission))
        urls = {g.permission: g.settings_url for g in result}
        assert urls == {
            MacPermission.ACCESSIBILITY: _ACCESSIBILITY_URL,
            MacPermission.INPUT_MONITORING: _INPUT_MONITORING_URL,
        }


class TestCopy:
    @pytest.fixture(params=list(MacPermission), ids=lambda p: p.name)
    def message(self, request: pytest.FixtureRequest) -> str:
        return _single({request.param}).message

    def test_explains_the_one_time_relaunch(self, message: str) -> None:
        lowered = message.lower()
        assert "relaunch" in lowered
        assert "once" in lowered

    def test_user_grants_in_system_settings(self, message: str) -> None:
        # The copy must direct the *user* to System Settings — granting is
        # something only they can do.
        assert "System Settings" in message
        assert "turn on Dictatem" in message

    def test_never_claims_dictatem_grants_anything(self, message: str) -> None:
        lowered = message.lower()
        for forbidden in (
            "dictatem will grant",
            "dictatem grants",
            "grant it for you",
            "on your behalf",
            "automatically grant",
            "grant automatically",
        ):
            assert forbidden not in lowered


class TestMicrophoneNotMapped:
    def test_enum_has_no_microphone_member(self) -> None:
        # Microphone gets macOS's standard automatic TCC prompt on first
        # capture — Dictatem never shows custom guidance for it (ADR-0014).
        assert not hasattr(MacPermission, "MICROPHONE")

    def test_mapper_knows_exactly_the_two_guided_permissions(self) -> None:
        assert {p.name for p in MacPermission} == {"ACCESSIBILITY", "INPUT_MONITORING"}
