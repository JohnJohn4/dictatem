"""Tests for the Windows hotkey-hook failure surface (#245 / review F-15).

When ``SetWindowsHookExW`` refuses a low-level hook the hotkey is dead; the
hook reports that through a callback (on its own thread) and the daemon turns
it into one tray notification plus a tray hint, so the failure is never
silent. The message copy comes from a pure mapper; the reporter is the
thread-safe queue the daemon tick drains.
"""

from __future__ import annotations

import threading

from dictatem.hotkey.hook_failure import (
    HOTKEY_UNREGISTERED_HINT,
    HookFailure,
    HookFailureReporter,
    HookKind,
    hook_failure_notice,
)


class _FakeTray:
    def __init__(self) -> None:
        self.notifications: list[tuple[str, str]] = []
        self.hints: list[str] = []

    def show_notification(self, title: str, body: str) -> None:
        self.notifications.append((title, body))

    def set_hotkey_hint(self, text: str) -> None:
        self.hints.append(text)


def _reporter(tray: _FakeTray) -> HookFailureReporter:
    return HookFailureReporter(
        show_notification=tray.show_notification,
        set_hotkey_hint=tray.set_hotkey_hint,
    )


class TestNoticeMapper:
    def test_notice_tells_the_user_to_dictate_from_the_tray(self) -> None:
        notice = hook_failure_notice(HookFailure(HookKind.KEYBOARD, error_code=5))
        assert "couldn't be registered" in notice.body
        assert "tray menu" in notice.body
        assert notice.title

    def test_hint_points_at_the_tray_menu(self) -> None:
        notice = hook_failure_notice(HookFailure(HookKind.MOUSE, error_code=5))
        assert notice.hint == HOTKEY_UNREGISTERED_HINT
        assert "tray menu" in HOTKEY_UNREGISTERED_HINT

    def test_mouse_failure_names_the_mouse_button(self) -> None:
        notice = hook_failure_notice(HookFailure(HookKind.MOUSE, error_code=5))
        assert "mouse" in notice.body.lower()


class TestReporter:
    def test_nothing_reported_shows_nothing(self) -> None:
        tray = _FakeTray()
        _reporter(tray).drain()
        assert tray.notifications == []
        assert tray.hints == []

    def test_a_failure_produces_one_notification_and_hint(self) -> None:
        tray = _FakeTray()
        reporter = _reporter(tray)
        reporter.report(HookFailure(HookKind.KEYBOARD, error_code=1428))
        reporter.drain()
        expected = hook_failure_notice(HookFailure(HookKind.KEYBOARD, 1428))
        assert tray.notifications == [(expected.title, expected.body)]
        assert tray.hints == [HOTKEY_UNREGISTERED_HINT]

    def test_both_hooks_failing_still_shows_exactly_one(self) -> None:
        tray = _FakeTray()
        reporter = _reporter(tray)
        reporter.report(HookFailure(HookKind.KEYBOARD, error_code=5))
        reporter.report(HookFailure(HookKind.MOUSE, error_code=5))
        reporter.drain()
        reporter.drain()
        assert len(tray.notifications) == 1
        assert tray.hints == [HOTKEY_UNREGISTERED_HINT]

    def test_report_is_safe_from_another_thread(self) -> None:
        # The hook calls report() on its own hook thread; drain() runs on Qt.
        tray = _FakeTray()
        reporter = _reporter(tray)
        t = threading.Thread(
            target=reporter.report, args=(HookFailure(HookKind.MOUSE, 5),)
        )
        t.start()
        t.join()
        reporter.drain()
        assert len(tray.notifications) == 1

    def test_report_alone_does_not_touch_the_tray(self) -> None:
        # Only the Qt-thread drain may touch widgets.
        tray = _FakeTray()
        _reporter(tray).report(HookFailure(HookKind.KEYBOARD, 5))
        assert tray.notifications == []
        assert tray.hints == []
