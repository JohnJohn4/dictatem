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


class TestMouseIdentities:
    """Mouse buttons are neutral Key identities in the same combo as modifiers.

    See ADR-0020. ``mouse4``/``mouse5`` are the side buttons and ``middle`` is
    the wheel click; each resolves to a ``Key`` the classifier reasons about
    exactly like a modifier group.
    """

    def test_standalone_mouse4_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse4",))

        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)

        _decision, event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 100)
        assert event == HotkeyEvent.TAP

    def test_standalone_mouse4_hold_start(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse4",))

        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)

        event = c.tick(210)
        assert event == HotkeyEvent.HOLD_START

    def test_standalone_mouse4_hold_end(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse4",))

        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        c.tick(210)

        _decision, event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 500)
        assert event == HotkeyEvent.HOLD_END

    def test_standalone_mouse5_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse5",))

        c.process_event(Key.MOUSE_5, KeyAction.KEY_DOWN, 0)

        _decision, event = c.process_event(Key.MOUSE_5, KeyAction.KEY_UP, 100)
        assert event == HotkeyEvent.TAP

    def test_standalone_middle_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("middle",))

        c.process_event(Key.MOUSE_MIDDLE, KeyAction.KEY_DOWN, 0)

        _decision, event = c.process_event(Key.MOUSE_MIDDLE, KeyAction.KEY_UP, 100)
        assert event == HotkeyEvent.TAP

    def test_ctrl_mouse4_combined_tap(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 10)

        _decision, event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 150)
        assert event == HotkeyEvent.TAP

    def test_ctrl_mouse4_combined_hold_start(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 10)

        event = c.tick(210)
        assert event == HotkeyEvent.HOLD_START

    def test_ctrl_mouse4_requires_ctrl(self) -> None:
        """Bare Mouse4 must NOT form the ctrl+mouse4 combo."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)

        _decision, event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 100)
        assert event is None
        assert c.combo_held is False


class TestMouseSuppression:
    """Conditional suppression of mouse-button events (ADR-0020).

    A mouse-button press SUPPRESSES iff it completes/sustains the configured
    combo; modifier keys always pass through. The matching button-up is
    suppressed iff its down was, keeping the down/up pair balanced.
    """

    def test_standalone_mouse4_press_suppressed(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse4",))

        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        assert decision == HookDecision.SUPPRESS

    def test_standalone_mouse4_up_suppressed(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse4",))

        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 100)
        assert decision == HookDecision.SUPPRESS

    def test_combined_mouse4_press_suppressed_while_ctrl_held(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 10)
        assert decision == HookDecision.SUPPRESS

    def test_combined_mouse4_up_suppressed_while_ctrl_held(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 10)
        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 150)
        assert decision == HookDecision.SUPPRESS

    def test_bare_mouse4_press_passes_through_when_combo_needs_ctrl(self) -> None:
        """Bare Mouse4 (no Ctrl) must pass through so browser-back still works."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        assert decision == HookDecision.PASS_THROUGH

    def test_bare_mouse4_up_passes_through_when_down_did(self) -> None:
        """A down that passed through means its up must pass through too."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 100)
        assert decision == HookDecision.PASS_THROUGH

    def test_up_pairs_with_its_down_when_ctrl_released_first(self) -> None:
        """If the down was suppressed, its up is suppressed even if the combo
        already broke (Ctrl released) before the button-up arrives."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        down, _ = c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 10)
        assert down == HookDecision.SUPPRESS

        # Ctrl is released before the mouse button comes up.
        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_UP, 20)
        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 30)
        assert decision == HookDecision.SUPPRESS

    def test_up_passes_through_when_down_passed_even_if_ctrl_pressed_later(
        self,
    ) -> None:
        """A bare-Mouse4 down passes through; pressing Ctrl afterwards must not
        retroactively suppress the matching up (down/up stay paired)."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        down, _ = c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        assert down == HookDecision.PASS_THROUGH

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 10)
        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 20)
        assert decision == HookDecision.PASS_THROUGH

    def test_modifier_key_in_mouse_combo_passes_through(self) -> None:
        """Modifier keys always pass through even in a mouse combo."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "mouse4"))

        decision, _event = c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        assert decision == HookDecision.PASS_THROUGH

    def test_mouse4_not_in_combo_passes_through(self) -> None:
        """A mouse button that is not configured at all passes through."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "win"))

        decision, _event = c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        assert decision == HookDecision.PASS_THROUGH

    def test_unconfigured_mouse_button_passes_through_while_combo_held(self) -> None:
        """An unbound mouse button must pass through even while a keyboard-only
        combo is held — only the *configured* trigger button is suppressed."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl",))

        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)  # combo now held
        down, _ = c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 10)
        assert down == HookDecision.PASS_THROUGH
        up, _ = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 20)
        assert up == HookDecision.PASS_THROUGH

    def test_repeat_mouse_down_does_not_unbalance_pairing(self) -> None:
        """A duplicate down (auto-repeat) is ignored and the single up still
        pairs with the original suppressed down."""
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse4",))

        first, _ = c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        assert first == HookDecision.SUPPRESS
        # Duplicate down ignored.
        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 10)
        up, _ = c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 50)
        assert up == HookDecision.SUPPRESS


class TestMenuMaskOnRelease:
    """A neutralizing keystroke is requested on a staggered Win+Alt chord release
    so a lone Alt-up doesn't activate the menu bar / a lone Win-up the Start menu
    (#171). The classifier only DECIDES (pending_mask); the native hook injects.
    """

    def _arm_win_alt(self, c: HotkeyClassifier) -> None:
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)

    def test_mask_on_win_up_while_alt_held(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)  # win+alt default
        self._arm_win_alt(c)
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 500)
        # Win released first, Alt still held → mask to protect Alt's lone release.
        assert c.pending_mask is True

    def test_no_mask_on_final_alt_up(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)
        self._arm_win_alt(c)
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 500)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 520)
        # Alt is the last to go up — nothing left to protect; it was already
        # neutralized while Win was released.
        assert c.pending_mask is False

    def test_mask_on_alt_up_while_win_held_reverse_order(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)
        self._arm_win_alt(c)
        # Alt released first, Win (a side-effect key) still held → mask.
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 500)
        assert c.pending_mask is True
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 520)
        assert c.pending_mask is False

    def test_tap_release_also_masks(self) -> None:
        # Even a quick tap (toggle) must neutralize the chord release.
        c = HotkeyClassifier(tap_threshold_ms=200)
        self._arm_win_alt(c)
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 50)
        assert c.pending_mask is True

    def test_no_mask_for_lone_alt_not_forming_combo(self) -> None:
        # Alt is part of win+alt, but pressing Alt ALONE never armed the combo —
        # so its release keeps its normal menu-bar behaviour (no mask).
        c = HotkeyClassifier(tap_threshold_ms=200)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 100)
        assert c.pending_mask is False

    def test_no_mask_for_lone_win_not_forming_combo(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 100)
        assert c.pending_mask is False

    def test_key_down_never_masks(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        assert c.pending_mask is False
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)
        assert c.pending_mask is False

    def test_non_combo_key_release_does_not_mask(self) -> None:
        # A stray letter released mid-chord is not a combo modifier → no mask.
        c = HotkeyClassifier(tap_threshold_ms=200)
        self._arm_win_alt(c)
        c.process_event(Key.OTHER, KeyAction.KEY_DOWN, 100)
        c.process_event(Key.OTHER, KeyAction.KEY_UP, 110)
        assert c.pending_mask is False

    def test_shift_win_combo_masks_on_shift_release(self) -> None:
        # shift+win: releasing shift leaves Win (side-effect) held → mask. Ctrl is
        # not a trigger here, so the Ctrl neutralizer is safe to inject.
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("shift", "win"))
        c.process_event(Key.LEFT_SHIFT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)
        c.process_event(Key.LEFT_SHIFT, KeyAction.KEY_UP, 500)
        assert c.pending_mask is True

    def test_ctrl_alt_combo_masks_safely(self) -> None:
        # ctrl+alt: releasing Ctrl leaves Alt about to be lone → mask to protect
        # Alt's menu side-effect. This is safe even though the neutralizer is a
        # Ctrl tap, because the native layer taps a *generic* Ctrl, which feeds
        # back as Key.OTHER and so can never re-complete the ctrl+alt combo.
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "alt"))
        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 10)
        c.process_event(Key.LEFT_CTRL, KeyAction.KEY_UP, 500)
        assert c.pending_mask is True

    def test_doubled_modifier_release_mid_hold_does_not_mask(self) -> None:
        # Both Meta keys + Alt held; releasing ONE Meta leaves the combo still
        # fully held (the other Meta sustains it), so nothing becomes lone and no
        # OS side-effect would fire — injecting a Ctrl tap mid-hold would be wrong.
        c = HotkeyClassifier(tap_threshold_ms=200)  # win+alt
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_META, KeyAction.KEY_DOWN, 10)
        c.process_event(Key.RIGHT_META, KeyAction.KEY_DOWN, 20)
        assert c.combo_held is True
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 500)
        assert c.combo_held is True  # RIGHT_META still sustains the combo
        assert c.pending_mask is False

    def test_mouse_release_does_not_mask(self) -> None:
        # A mouse trigger has no menu side-effect and is suppressed anyway.
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse4",))
        c.process_event(Key.MOUSE_4, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.MOUSE_4, KeyAction.KEY_UP, 100)
        assert c.pending_mask is False

    def test_single_side_effect_modifier_combo_does_not_mask(self) -> None:
        # Known limitation: an alt-ONLY combo has no second key to leave held, so
        # its lone release cannot be pre-neutralized (it would need suppress-and-
        # resynthesize). The default win+alt is unaffected; documented in #171.
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("alt",))
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 0)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 100)
        assert c.pending_mask is False

    def test_no_stale_mask_after_previous_dictation(self) -> None:
        # After a full chord release, a later lone Alt tap (which never re-forms
        # the combo) must not mask.
        c = HotkeyClassifier(tap_threshold_ms=200)
        self._arm_win_alt(c)
        c.process_event(Key.LEFT_META, KeyAction.KEY_UP, 500)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 520)
        # New, unrelated lone Alt press/release.
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 2000)
        c.process_event(Key.LEFT_ALT, KeyAction.KEY_UP, 2100)
        assert c.pending_mask is False
