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
    HOTKEY_OFF_HINT,
    MacPermission,
    PermissionGuidance,
    PromptContext,
    map_missing_permissions,
    reprompt_notification,
    tcc_entry_name,
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
    @pytest.fixture(
        params=[(p, c) for p in MacPermission for c in PromptContext],
        ids=lambda pc: f"{pc[0].name}-{pc[1].name}",
    )
    def guidance(self, request: pytest.FixtureRequest) -> PermissionGuidance:
        permission, context = request.param
        (only,) = map_missing_permissions(
            {permission}, context=context, listed_as="python3.12"
        )
        return only

    def test_explains_the_one_time_relaunch_via_restart(
        self, guidance: PermissionGuidance
    ) -> None:
        # The grant only applies after a relaunch, and the copy points at the
        # tray Restart item that does it (#95).
        assert "relaunch" in guidance.message.lower()
        assert "Restart" in guidance.message

    def test_user_turns_it_on_in_system_settings(
        self, guidance: PermissionGuidance
    ) -> None:
        # The copy must direct the *user* to System Settings — granting is
        # something only they can do.
        assert "System Settings" in guidance.message
        assert "turn on" in guidance.message

    def test_names_the_exact_entry_and_says_it_is_dictatem(
        self, guidance: PermissionGuidance
    ) -> None:
        # Until the signed bundle (#91) gives Dictatem its own identity, the
        # pane lists the interpreter ("python3.12"), not "Dictatem". The copy
        # names that exact row, or the user hunts for one that isn't there.
        assert "python3.12" in guidance.message
        assert "Dictatem" in guidance.message

    def test_is_short_and_action_first(self, guidance: PermissionGuidance) -> None:
        # #95: the old copy was too wordy. A short headline plus a few lines.
        assert len(guidance.title) <= 60
        assert len(guidance.message) <= 320
        assert guidance.message.startswith("In System Settings")

    def test_never_claims_dictatem_grants_anything(
        self, guidance: PermissionGuidance
    ) -> None:
        lowered = (guidance.title + " " + guidance.message).lower()
        for forbidden in (
            "dictatem will grant",
            "dictatem grants",
            "grant it for you",
            "on your behalf",
            "automatically grant",
            "grant automatically",
        ):
            assert forbidden not in lowered

    def test_defaults_to_the_generic_python_entry(self) -> None:
        (only,) = map_missing_permissions({MacPermission.ACCESSIBILITY})
        assert "“Python”" in only.message


class TestContext:
    def test_default_context_is_startup(self) -> None:
        assert map_missing_permissions(
            {MacPermission.ACCESSIBILITY}
        ) == map_missing_permissions(
            {MacPermission.ACCESSIBILITY}, context=PromptContext.STARTUP
        )

    def test_startup_titles_ask_for_the_permission(self) -> None:
        acc, im = map_missing_permissions(set(MacPermission))
        assert acc.title == "Allow Dictatem to paste your text"
        assert im.title == "Allow Dictatem to hear its hotkey"

    def test_on_use_titles_say_what_just_failed(self) -> None:
        acc, im = map_missing_permissions(
            set(MacPermission), context=PromptContext.ON_USE
        )
        assert "couldn't paste" in acc.title
        assert "hotkey isn't working" in im.title

    def test_on_use_accessibility_points_at_the_recovery_item(self) -> None:
        # The blocked paste's text is in the Most-recent dictation buffer
        # (ADR-0023), so the re-prompt tells the user how to get it back.
        (acc,) = map_missing_permissions(
            {MacPermission.ACCESSIBILITY}, context=PromptContext.ON_USE
        )
        assert "Copy last dictation" in acc.message

    def test_on_use_input_monitoring_points_at_the_menu_fallback(self) -> None:
        (im,) = map_missing_permissions(
            {MacPermission.INPUT_MONITORING}, context=PromptContext.ON_USE
        )
        assert "record from the menu-bar menu" in im.message

    def test_context_never_changes_the_deep_link(self) -> None:
        for permission in MacPermission:
            (startup,) = map_missing_permissions({permission})
            (on_use,) = map_missing_permissions(
                {permission}, context=PromptContext.ON_USE
            )
            assert startup.settings_url == on_use.settings_url


class TestTccEntryName:
    def test_formats_major_minor(self) -> None:
        assert tcc_entry_name(3, 12) == "python3.12"

    def test_tracks_the_running_interpreter(self) -> None:
        assert tcc_entry_name(3, 11) == "python3.11"


class TestRepromptNotification:
    @pytest.mark.parametrize("permission", list(MacPermission), ids=lambda p: p.name)
    def test_title_matches_the_on_use_dialog(self, permission: MacPermission) -> None:
        title, _body = reprompt_notification(permission)
        (on_use,) = map_missing_permissions(
            {permission}, context=PromptContext.ON_USE
        )
        assert title == on_use.title

    def test_body_names_entry_pane_and_restart(self) -> None:
        _title, body = reprompt_notification(
            MacPermission.INPUT_MONITORING, listed_as="python3.12"
        )
        assert "python3.12" in body
        assert "Input Monitoring" in body
        assert "Restart" in body


class TestHotkeyOffHint:
    def test_hint_names_the_missing_permission(self) -> None:
        assert "Input Monitoring" in HOTKEY_OFF_HINT


class TestMicrophoneNotMapped:
    def test_enum_has_no_microphone_member(self) -> None:
        # Microphone gets macOS's standard automatic TCC prompt on first
        # capture — Dictatem never shows custom guidance for it (ADR-0014).
        assert not hasattr(MacPermission, "MICROPHONE")

    def test_mapper_knows_exactly_the_two_guided_permissions(self) -> None:
        assert {p.name for p in MacPermission} == {"ACCESSIBILITY", "INPUT_MONITORING"}
