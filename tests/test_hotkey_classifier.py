"""Tests for the pure-logic hotkey classifier."""

from __future__ import annotations

from dictatem.hotkey.classifier import (
    VK_ESCAPE,
    VK_LEFT,
    VK_LMENU,
    VK_LWIN,
    VK_RMENU,
    VK_RWIN,
    HookDecision,
    HotkeyClassifier,
    HotkeyEvent,
    KeyAction,
)


class TestTapDetection:
    def test_win_alt_press_release_within_threshold_emits_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(VK_LWIN, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_tap_emits_only_once(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)
        c.process_event(VK_LWIN, KeyAction.KEY_UP, 150)

        _decision, event = c.process_event(VK_LMENU, KeyAction.KEY_UP, 160)
        assert event is None


class TestHoldDetection:
    def test_hold_start_after_threshold(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)

        event = c.tick(210)
        assert event == HotkeyEvent.HOLD_START

    def test_hold_end_on_release_after_hold_start(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)
        c.tick(210)

        _decision, event = c.process_event(VK_LWIN, KeyAction.KEY_UP, 500)
        assert event == HotkeyEvent.HOLD_END

    def test_tick_before_threshold_emits_nothing(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)

        event = c.tick(100)
        assert event is None

    def test_hold_start_emits_only_once(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)

        c.tick(210)
        event = c.tick(300)
        assert event is None


class TestAutoRepeatSuppression:
    def test_duplicate_keydown_ignored(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        _decision, event = c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 50)
        assert event is None

    def test_auto_repeat_does_not_break_combo(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)
        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 50)

        _decision, event = c.process_event(VK_LWIN, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP


class TestArrowSuppression:
    def test_arrow_suppressed_while_combo_held(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)

        decision, _event = c.process_event(VK_LEFT, KeyAction.KEY_DOWN, 100)
        assert decision == HookDecision.SUPPRESS

    def test_arrow_not_suppressed_without_combo(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        decision, _event = c.process_event(VK_LEFT, KeyAction.KEY_DOWN, 0)
        assert decision == HookDecision.PASS_THROUGH


class TestEscDetection:
    def test_esc_emits_event_when_active(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)
        c.set_active(True)

        _decision, event = c.process_event(VK_ESCAPE, KeyAction.KEY_DOWN, 0)
        assert event == HotkeyEvent.ESC

    def test_esc_does_not_emit_when_inactive(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)
        c.set_active(False)

        _decision, event = c.process_event(VK_ESCAPE, KeyAction.KEY_DOWN, 0)
        assert event is None


class TestEdgeCases:
    def test_right_side_modifiers_trigger_combo(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_RMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_RWIN, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(VK_RWIN, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_single_modifier_release_no_event(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        _decision, event = c.process_event(VK_LMENU, KeyAction.KEY_UP, 100)
        assert event is None

    def test_second_tap_after_first(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 0)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 10)
        c.process_event(VK_LWIN, KeyAction.KEY_UP, 100)
        c.process_event(VK_LMENU, KeyAction.KEY_UP, 110)

        c.process_event(VK_LMENU, KeyAction.KEY_DOWN, 500)
        c.process_event(VK_LWIN, KeyAction.KEY_DOWN, 510)
        _decision, event = c.process_event(VK_LWIN, KeyAction.KEY_UP, 650)
        assert event == HotkeyEvent.TAP

    def test_spurious_keyup_ignored(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        _decision, event = c.process_event(VK_LMENU, KeyAction.KEY_UP, 0)
        assert event is None
