"""Tests for the pure-logic hotkey classifier."""

from __future__ import annotations

from dictatem.hotkey.classifier import (
    HookDecision,
    HotkeyClassifier,
    HotkeyEvent,
    Key,
    KeyAction,
)


class TestTapDetection:
    def test_win_alt_press_release_within_threshold_emits_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_tap_emits_only_once(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)

        _decision, event = c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 160)
        assert event is None


class TestHoldDetection:
    def test_hold_start_after_threshold(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        event = c.tick(210)
        assert event == HotkeyEvent.HOLD_START

    def test_hold_end_on_release_after_hold_start(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)
        c.tick(210)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 500)
        assert event == HotkeyEvent.HOLD_END

    def test_tick_before_threshold_emits_nothing(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        event = c.tick(100)
        assert event is None

    def test_hold_start_emits_only_once(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        c.tick(210)
        event = c.tick(300)
        assert event is None


class TestAutoRepeatSuppression:
    def test_duplicate_keydown_ignored(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        _decision, event = c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 50)
        assert event is None

    def test_auto_repeat_does_not_break_combo(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 50)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP


class TestArrowSuppression:
    def test_arrow_suppressed_while_combo_held(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        decision, _event = c.process_event(Key.LEFT, KeyAction.KEY_DOWN, 100)
        assert decision == HookDecision.SUPPRESS

    def test_arrow_not_suppressed_without_combo(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        decision, _event = c.process_event(Key.LEFT, KeyAction.KEY_DOWN, 0)
        assert decision == HookDecision.PASS_THROUGH


class TestEscDetection:
    def test_esc_emits_event_when_active(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)
        c.set_active(True)

        _decision, event = c.process_event(Key.ESCAPE, KeyAction.KEY_DOWN, 0)
        assert event == HotkeyEvent.ESC

    def test_esc_does_not_emit_when_inactive(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)
        c.set_active(False)

        _decision, event = c.process_event(Key.ESCAPE, KeyAction.KEY_DOWN, 0)
        assert event is None


class TestEdgeCases:
    def test_right_side_modifiers_trigger_combo(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.RIGHT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.RIGHT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.RIGHT_META, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_mixed_left_right_modifier_sides_sustain_combo(self) -> None:
        """Holding either side of a modifier sustains the combo: pressing both
        meta keys and releasing one must NOT break it."""
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)
        c.process_event(Key.RIGHT_META, KeyAction.KEY_DOWN, 20)

        # Release the left meta — right meta still satisfies the meta group.
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 30)
        assert c.combo_held is True

    def test_single_modifier_release_no_event(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        _decision, event = c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 100)
        assert event is None

    def test_second_tap_after_first(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 100)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 110)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 500)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 510)
        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 650)
        assert event == HotkeyEvent.TAP

    def test_spurious_keyup_ignored(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)

        _decision, event = c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 0)
        assert event is None

    def test_other_keys_are_inert(self) -> None:
        """Untracked keys (Key.OTHER) never form a combo or emit an event."""
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.OTHER, KeyAction.KEY_DOWN, 0)
        decision, event = c.process_event(Key.OTHER, KeyAction.KEY_UP, 50)
        assert c.combo_held is False
        assert decision == HookDecision.PASS_THROUGH
        assert event is None


class TestConfigurableModifiers:
    """HotkeyClassifier honours any configured modifier set."""

    def test_ctrl_win_combo_fires_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "win"))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_ctrl_win_does_not_treat_win_alt_as_combo(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "win"))

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)
        assert event is None

    def test_right_ctrl_right_win_fires_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "win"))

        c.process_event(Key.RIGHT_CTRL, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.RIGHT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.RIGHT_META, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_single_modifier_ctrl_fires_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl",))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)

        _decision, event = c.process_event(Key.LEFT_CTRL, KeyAction.KEY_UP, 100)
        assert event == HotkeyEvent.TAP

    def test_single_modifier_ctrl_fires_hold_start(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl",))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)

        event = c.tick(210)
        assert event == HotkeyEvent.HOLD_START

    def test_shift_modifier_fires_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("shift",))

        c.process_event(Key.LEFT_SHIFT, KeyAction.KEY_DOWN, 0)

        _decision, event = c.process_event(Key.LEFT_SHIFT, KeyAction.KEY_UP, 100)
        assert event == HotkeyEvent.TAP

    def test_right_shift_fires_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("shift",))

        c.process_event(Key.RIGHT_SHIFT, KeyAction.KEY_DOWN, 0)

        _decision, event = c.process_event(Key.RIGHT_SHIFT, KeyAction.KEY_UP, 100)
        assert event == HotkeyEvent.TAP

    def test_three_modifier_combo_requires_all_three(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "shift", "win"))

        # Only ctrl + win — shift missing, no combo
        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)
        assert event is None

    def test_three_modifier_combo_fires_when_all_held(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "shift", "win"))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_SHIFT, KeyAction.KEY_DOWN, 5)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_empty_modifiers_combo_never_held(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=())

        # Press every known modifier — still no combo
        for key in (
            Key.LEFT_META, Key.RIGHT_META, Key.LEFT_ALT, Key.RIGHT_ALT,
            Key.LEFT_CTRL, Key.RIGHT_CTRL, Key.LEFT_SHIFT, Key.RIGHT_SHIFT,
        ):
            c.process_event(key, KeyAction.KEY_DOWN, 0)

        assert c.combo_held is False

    def test_empty_modifiers_tick_never_emits_hold(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=())

        for key in (
            Key.LEFT_META, Key.RIGHT_META, Key.LEFT_ALT, Key.RIGHT_ALT,
            Key.LEFT_CTRL, Key.RIGHT_CTRL, Key.LEFT_SHIFT, Key.RIGHT_SHIFT,
        ):
            c.process_event(key, KeyAction.KEY_DOWN, 0)

        event = c.tick(500)
        assert event is None

    def test_all_unknown_modifiers_combo_never_held(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("bogus", "unknown"))

        for key in (
            Key.LEFT_META, Key.RIGHT_META, Key.LEFT_ALT, Key.RIGHT_ALT,
            Key.LEFT_CTRL, Key.RIGHT_CTRL, Key.LEFT_SHIFT, Key.RIGHT_SHIFT,
        ):
            c.process_event(key, KeyAction.KEY_DOWN, 0)

        assert c.combo_held is False

    def test_default_modifiers_unchanged(self) -> None:
        """Constructor default still resolves to win+alt (backwards compat)."""
        c = HotkeyClassifier(tap_threshold_ms=200)

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_meta_alias_matches_win(self) -> None:
        """`meta` resolves to the same Key group as the `win` alias."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("meta", "alt"))

        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP
