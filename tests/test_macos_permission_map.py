"""Unit tests for the pure macOS permission mapper (#57 / ADR-0014).

Given the SET of missing permissions, the mapper returns the exact System
Settings deep-link targets and user-facing copy for the guided first-run dialog.
It is pure: no PyObjC, no AX calls, no I/O — every branch (including the
nothing-missing case) is covered here, mirroring the failure-classifier tests.
Microphone is intentionally NOT in the mapper (it's the automatic TCC prompt).
"""

from __future__ import annotations

from dictatem.macos.permission_map import (
    ACCESSIBILITY_URL,
    INPUT_MONITORING_URL,
    MacPermission,
    map_missing_permissions,
)


class TestNothingMissing:
    """Empty missing-set -> all granted, no steps, no dialog."""

    def test_empty_set_is_all_granted(self) -> None:
        prompt = map_missing_permissions(frozenset())
        assert prompt.all_granted is True

    def test_empty_set_has_no_steps(self) -> None:
        prompt = map_missing_permissions(frozenset())
        assert prompt.steps == ()


class TestAccessibilityMissing:
    def test_maps_to_accessibility_pane_url(self) -> None:
        prompt = map_missing_permissions(frozenset({MacPermission.ACCESSIBILITY}))
        assert prompt.all_granted is False
        assert len(prompt.steps) == 1
        assert prompt.steps[0].permission is MacPermission.ACCESSIBILITY
        assert prompt.steps[0].url == ACCESSIBILITY_URL

    def test_accessibility_url_anchor_is_correct(self) -> None:
        # Deep-link must target the Privacy_Accessibility anchor exactly.
        assert ACCESSIBILITY_URL.endswith("Privacy_Accessibility")
        assert ACCESSIBILITY_URL.startswith("x-apple.systempreferences:")

    def test_accessibility_step_names_the_pane(self) -> None:
        prompt = map_missing_permissions(frozenset({MacPermission.ACCESSIBILITY}))
        assert prompt.steps[0].pane == "Accessibility"

    def test_accessibility_only_does_not_include_input_monitoring(self) -> None:
        prompt = map_missing_permissions(frozenset({MacPermission.ACCESSIBILITY}))
        perms = {step.permission for step in prompt.steps}
        assert MacPermission.INPUT_MONITORING not in perms


class TestInputMonitoringMissing:
    def test_maps_to_input_monitoring_pane_url(self) -> None:
        prompt = map_missing_permissions(frozenset({MacPermission.INPUT_MONITORING}))
        assert prompt.all_granted is False
        assert len(prompt.steps) == 1
        assert prompt.steps[0].permission is MacPermission.INPUT_MONITORING
        assert prompt.steps[0].url == INPUT_MONITORING_URL

    def test_input_monitoring_url_anchor_is_correct(self) -> None:
        assert INPUT_MONITORING_URL.endswith("Privacy_ListenEvent")
        assert INPUT_MONITORING_URL.startswith("x-apple.systempreferences:")

    def test_input_monitoring_step_names_the_pane(self) -> None:
        prompt = map_missing_permissions(frozenset({MacPermission.INPUT_MONITORING}))
        assert prompt.steps[0].pane == "Input Monitoring"


class TestBothMissing:
    def test_both_missing_yields_two_steps(self) -> None:
        prompt = map_missing_permissions(
            frozenset({MacPermission.ACCESSIBILITY, MacPermission.INPUT_MONITORING})
        )
        assert prompt.all_granted is False
        assert len(prompt.steps) == 2

    def test_order_is_stable_input_monitoring_first(self) -> None:
        # Order must be deterministic regardless of set iteration order: the
        # hotkey (Input Monitoring) is the first thing the user hits, so it
        # comes first.
        prompt = map_missing_permissions(
            frozenset({MacPermission.ACCESSIBILITY, MacPermission.INPUT_MONITORING})
        )
        assert prompt.steps[0].permission is MacPermission.INPUT_MONITORING
        assert prompt.steps[1].permission is MacPermission.ACCESSIBILITY

    def test_both_urls_present_and_distinct(self) -> None:
        prompt = map_missing_permissions(
            frozenset({MacPermission.ACCESSIBILITY, MacPermission.INPUT_MONITORING})
        )
        urls = {step.url for step in prompt.steps}
        assert urls == {ACCESSIBILITY_URL, INPUT_MONITORING_URL}


class TestRelaunchCopy:
    def test_message_explains_one_time_relaunch(self) -> None:
        prompt = map_missing_permissions(frozenset({MacPermission.INPUT_MONITORING}))
        assert "relaunch" in prompt.message.lower()

    def test_message_names_each_missing_pane(self) -> None:
        prompt = map_missing_permissions(
            frozenset({MacPermission.ACCESSIBILITY, MacPermission.INPUT_MONITORING})
        )
        assert "Input Monitoring" in prompt.message
        assert "Accessibility" in prompt.message

    def test_each_step_has_a_non_empty_reason(self) -> None:
        prompt = map_missing_permissions(
            frozenset({MacPermission.ACCESSIBILITY, MacPermission.INPUT_MONITORING})
        )
        for step in prompt.steps:
            assert step.reason.strip() != ""

    def test_title_is_actionable_when_missing(self) -> None:
        prompt = map_missing_permissions(frozenset({MacPermission.ACCESSIBILITY}))
        assert prompt.title.strip() != ""
