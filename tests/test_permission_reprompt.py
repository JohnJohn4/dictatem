"""Unit tests for the pure re-prompt-on-use throttle (#95).

When a gated action fails for a missing macOS permission (the hotkey event tap
can't be created, a paste's synthetic Cmd+V is dropped), the throttle decides
whether to show the guided dialog, a tray notification, or nothing — so the
failure is never silent, yet never a modal nag on every dictation. The launch
probe goes through the same throttle so nothing is shown twice. Pure: callers
pass ``now``; no Qt, no clock.
"""

from __future__ import annotations

from dictatem.permissions.mapper import MacPermission
from dictatem.permissions.reprompt import (
    DEFAULT_DIALOG_COOLDOWN_S,
    DEFAULT_NOTIFY_COOLDOWN_S,
    PermissionRepromptThrottle,
    RepromptAction,
)

ACC = MacPermission.ACCESSIBILITY
IM = MacPermission.INPUT_MONITORING


def _throttle() -> PermissionRepromptThrottle:
    return PermissionRepromptThrottle(dialog_cooldown_s=300.0, notify_cooldown_s=30.0)


class TestOnUse:
    def test_first_failed_use_shows_the_dialog(self) -> None:
        assert _throttle().on_use(ACC, now=0.0) is RepromptAction.DIALOG

    def test_dialog_decision_marks_it_open(self) -> None:
        t = _throttle()
        t.on_use(ACC, now=0.0)
        assert t.is_dialog_open(ACC)

    def test_reports_while_the_dialog_is_open_are_dropped(self) -> None:
        # Trigger Fire reports twice (backspaces + typed text) for one paste;
        # the second must not stack a second dialog or a note behind it.
        t = _throttle()
        t.on_use(ACC, now=0.0)
        assert t.on_use(ACC, now=0.1) is RepromptAction.NONE
        assert t.on_use(ACC, now=1000.0) is RepromptAction.NONE

    def test_repeat_inside_cooldown_notifies_instead_of_a_dialog(self) -> None:
        t = _throttle()
        t.on_use(ACC, now=0.0)
        t.dialog_closed(ACC, now=10.0)
        # Past the notify cool-down (which the dialog's close also started)
        # but inside the dialog cool-down: a note, not a modal.
        assert t.on_use(ACC, now=10.0 + 31.0) is RepromptAction.NOTIFY

    def test_notifications_are_rate_limited(self) -> None:
        t = _throttle()
        t.on_use(ACC, now=0.0)
        t.dialog_closed(ACC, now=0.0)
        assert t.on_use(ACC, now=40.0) is RepromptAction.NOTIFY
        assert t.on_use(ACC, now=50.0) is RepromptAction.NONE
        assert t.on_use(ACC, now=71.0) is RepromptAction.NOTIFY

    def test_report_right_after_closing_the_dialog_is_quiet(self) -> None:
        # The user just read the dialog; an immediate follow-up note is noise.
        t = _throttle()
        t.on_use(ACC, now=0.0)
        t.dialog_closed(ACC, now=5.0)
        assert t.on_use(ACC, now=6.0) is RepromptAction.NONE

    def test_dialog_returns_once_the_cooldown_has_passed(self) -> None:
        t = _throttle()
        t.on_use(ACC, now=0.0)
        t.dialog_closed(ACC, now=20.0)
        # The cool-down runs from the CLOSE, not from when it opened.
        assert t.on_use(ACC, now=20.0 + 299.0) is RepromptAction.NOTIFY
        assert t.on_use(ACC, now=20.0 + 300.0) is RepromptAction.DIALOG

    def test_permissions_are_throttled_independently(self) -> None:
        t = _throttle()
        assert t.on_use(ACC, now=0.0) is RepromptAction.DIALOG
        assert t.on_use(IM, now=0.0) is RepromptAction.DIALOG


class TestOnStartup:
    def test_nothing_missing_shows_nothing(self) -> None:
        assert _throttle().on_startup(set(), now=0.0) == frozenset()

    def test_first_launch_shows_every_missing_permission(self) -> None:
        t = _throttle()
        assert t.on_startup({ACC, IM}, now=2.0) == frozenset({ACC, IM})
        assert t.is_dialog_open(ACC)
        assert t.is_dialog_open(IM)

    def test_skips_a_permission_already_surfaced_on_use(self) -> None:
        # The event tap fails within ms of launch; if that report was shown
        # first, the 2 s startup probe must not show Input Monitoring again.
        t = _throttle()
        t.on_use(IM, now=0.1)
        t.dialog_closed(IM, now=1.5)
        assert t.on_startup({ACC, IM}, now=2.0) == frozenset({ACC})

    def test_skips_a_permission_whose_dialog_is_open(self) -> None:
        t = _throttle()
        t.on_use(IM, now=0.1)
        assert t.on_startup({IM}, now=2.0) == frozenset()

    def test_startup_dialog_then_tap_report_is_quiet(self) -> None:
        # The real launch order: the tap report is deferred behind the startup
        # dialog, then replayed right after it closes — no redundant note.
        t = _throttle()
        t.on_startup({IM}, now=2.0)
        t.dialog_closed(IM, now=8.0)
        assert t.on_use(IM, now=8.0) is RepromptAction.NONE

    def test_startup_never_notifies(self) -> None:
        t = _throttle()
        t.on_startup({ACC}, now=0.0)
        t.dialog_closed(ACC, now=0.0)
        # A second probe inside the cool-down shows nothing (no note either).
        assert t.on_startup({ACC}, now=60.0) == frozenset()


class TestDefaults:
    def test_dialog_cooldown_is_minutes_not_seconds(self) -> None:
        assert DEFAULT_DIALOG_COOLDOWN_S >= 60.0

    def test_notify_cooldown_is_shorter_than_the_dialog_cooldown(self) -> None:
        assert 0.0 < DEFAULT_NOTIFY_COOLDOWN_S < DEFAULT_DIALOG_COOLDOWN_S

    def test_default_construction_works(self) -> None:
        assert PermissionRepromptThrottle().on_use(ACC, now=0.0) is RepromptAction.DIALOG
