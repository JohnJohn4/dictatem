"""Alt/Win menu-mask decision (#171 / #177) and own-injection hazards (#269).

Lone Alt/Win releases that end a Dictatem combo session are masked at their
OWN key-up: the native hook swallows the key-up and replays
``[mask, mask-up, key-up]`` so the menu bar / Start menu never activates and
steals keyboard focus from the next paste. The classifier only DECIDES
(``pending_mask``); the hook swallows and re-emits (see test_wh_keyboard_ll).
"""

from __future__ import annotations

import pytest

from dictatem.hotkey.classifier import HotkeyClassifier, HotkeyEvent, Key, KeyAction
from dictatem.hotkey.win32_keymap import (
    DICTATEM_INJECTION_TAG,
    LLKHF_INJECTED,
    is_own_injection,
    swallow_after_masked_replay,
)

_D = KeyAction.KEY_DOWN
_U = KeyAction.KEY_UP


def _masked_releases(
    c: HotkeyClassifier, events: list[tuple[Key, KeyAction, int]]
) -> list[Key]:
    """Feed *events*; return the key-ups the classifier asked to mask, in order."""
    masked: list[Key] = []
    for key, action, ts in events:
        c.process_event(key, action, ts)
        if c.pending_mask:
            assert action is _U, "only a key-up may ever be masked"
            masked.append(key)
    return masked


def _win_alt() -> HotkeyClassifier:
    return HotkeyClassifier(tap_threshold_ms=200)  # default win+alt


class TestWinAltReleaseOrders:
    def test_simultaneous_tap_masks_both_releases(self) -> None:
        # The observed failure: a quick tap-to-toggle whose two key-ups are
        # queued 1-2 ms apart. Each side-effect key is masked at its own key-up.
        masked = _masked_releases(
            _win_alt(),
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 1),
                (Key.LEFT_META, _U, 60),
                (Key.LEFT_ALT, _U, 61),
            ],
        )
        assert masked == [Key.LEFT_META, Key.LEFT_ALT]

    def test_win_first_press_alt_released_first(self) -> None:
        masked = _masked_releases(
            _win_alt(),
            [
                (Key.LEFT_META, _D, 0),
                (Key.LEFT_ALT, _D, 10),
                (Key.LEFT_ALT, _U, 900),
                (Key.LEFT_META, _U, 910),
            ],
        )
        assert masked == [Key.LEFT_ALT, Key.LEFT_META]

    def test_alt_first_press_win_released_first(self) -> None:
        masked = _masked_releases(
            _win_alt(),
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 10),
                (Key.LEFT_META, _U, 900),
                (Key.LEFT_ALT, _U, 910),
            ],
        )
        assert masked == [Key.LEFT_META, Key.LEFT_ALT]

    @pytest.mark.parametrize("first", [Key.LEFT_META, Key.LEFT_ALT])
    def test_delayed_second_release_still_masked(self, first: Key) -> None:
        # #177: the second modifier held for seconds after the combo broke must
        # still be masked when it finally goes up, in either order.
        second = Key.LEFT_ALT if first is Key.LEFT_META else Key.LEFT_META
        masked = _masked_releases(
            _win_alt(),
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 10),
                (first, _U, 900),
                (second, _U, 3500),
            ],
        )
        assert masked == [first, second]

    def test_hold_to_talk_masks(self) -> None:
        c = _win_alt()
        c.process_event(Key.LEFT_ALT, _D, 0)
        c.process_event(Key.LEFT_META, _D, 10)
        assert c.tick(300) is HotkeyEvent.HOLD_START
        assert _masked_releases(
            c, [(Key.LEFT_META, _U, 2000), (Key.LEFT_ALT, _U, 2010)]
        ) == [Key.LEFT_META, Key.LEFT_ALT]

    def test_doubled_modifiers_left_and_right(self) -> None:
        # Both Win keys + both Alts: every side-effect key's release is masked
        # (each had its own Dictatem session); harmless even mid-hold.
        masked = _masked_releases(
            _win_alt(),
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 10),
                (Key.RIGHT_META, _D, 20),
                (Key.RIGHT_ALT, _D, 30),
                (Key.LEFT_META, _U, 500),
                (Key.RIGHT_ALT, _U, 550),
                (Key.RIGHT_META, _U, 600),
                (Key.LEFT_ALT, _U, 700),
            ],
        )
        assert masked == [Key.LEFT_META, Key.RIGHT_ALT, Key.RIGHT_META, Key.LEFT_ALT]

    def test_autorepeat_of_held_modifiers_keeps_sessions_lone(self) -> None:
        masked = _masked_releases(
            _win_alt(),
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 10),
                (Key.LEFT_ALT, _D, 500),  # auto-repeat
                (Key.LEFT_META, _D, 530),  # auto-repeat
                (Key.LEFT_META, _U, 900),
                (Key.LEFT_ALT, _U, 910),
            ],
        )
        assert masked == [Key.LEFT_META, Key.LEFT_ALT]


class TestNotLone:
    def test_other_key_during_session(self) -> None:
        # e.g. Alt+Tab mid-hold: the OS won't open the menu, so don't mask.
        masked = _masked_releases(
            _win_alt(),
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 10),
                (Key.OTHER, _D, 100),
                (Key.OTHER, _U, 110),
                (Key.LEFT_META, _U, 900),
                (Key.LEFT_ALT, _U, 910),
            ],
        )
        assert masked == []

    def test_other_key_after_first_release_unlones_only_the_held_key(self) -> None:
        masked = _masked_releases(
            _win_alt(),
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 10),
                (Key.LEFT_META, _U, 900),  # masked: still lone
                (Key.OTHER, _D, 1000),  # Alt+<key> while Alt still down
                (Key.OTHER, _U, 1010),
                (Key.LEFT_ALT, _U, 1100),
            ],
        )
        assert masked == [Key.LEFT_META]

    def test_escape_during_session(self) -> None:
        c = _win_alt()
        c.set_active(True)
        masked = _masked_releases(
            c,
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 10),
                (Key.ESCAPE, _D, 100),
                (Key.ESCAPE, _U, 110),
                (Key.LEFT_META, _U, 900),
                (Key.LEFT_ALT, _U, 910),
            ],
        )
        assert masked == []


class TestOutsideDictatemSession:
    def test_user_lone_alt_keeps_menu_access(self) -> None:
        # Alt is part of win+alt, but Alt ALONE never formed the combo: the
        # user's normal Alt (menu bar) must keep working.
        assert _masked_releases(_win_alt(), [(Key.LEFT_ALT, _D, 0), (Key.LEFT_ALT, _U, 100)]) == []

    def test_user_lone_win_keeps_start_menu(self) -> None:
        events = [(Key.LEFT_META, _D, 0), (Key.LEFT_META, _U, 100)]
        assert _masked_releases(_win_alt(), events) == []

    def test_no_stale_mask_after_previous_dictation(self) -> None:
        c = _win_alt()
        _masked_releases(
            c,
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_META, _D, 10),
                (Key.LEFT_META, _U, 500),
                (Key.LEFT_ALT, _U, 520),
            ],
        )
        assert _masked_releases(c, [(Key.LEFT_ALT, _D, 2000), (Key.LEFT_ALT, _U, 2100)]) == []

    def test_non_combo_alt_never_masked(self) -> None:
        # ctrl+shift combo with Alt also held: Alt isn't a combo modifier.
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "shift"))
        masked = _masked_releases(
            c,
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.LEFT_CTRL, _D, 10),
                (Key.LEFT_SHIFT, _D, 20),
                (Key.LEFT_SHIFT, _U, 500),
                (Key.LEFT_CTRL, _U, 510),
                (Key.LEFT_ALT, _U, 520),
            ],
        )
        assert masked == []

    def test_key_down_never_masks(self) -> None:
        c = _win_alt()
        c.process_event(Key.LEFT_ALT, _D, 0)
        assert c.pending_mask is False
        c.process_event(Key.LEFT_META, _D, 10)
        assert c.pending_mask is False


class TestOtherCombos:
    @pytest.mark.parametrize("ctrl_first", [True, False])
    def test_ctrl_alt_masks_alt_only(self, ctrl_first: bool) -> None:
        # Ctrl has no lone-release side-effect: only Alt's key-up is masked, with
        # the 0xE8 mask key, which can't touch the Ctrl+Alt combo.
        ups = [(Key.LEFT_CTRL, _U, 500), (Key.LEFT_ALT, _U, 501)]
        if not ctrl_first:
            ups.reverse()
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "alt"))
        masked = _masked_releases(c, [(Key.LEFT_CTRL, _D, 0), (Key.LEFT_ALT, _D, 10), *ups])
        assert masked == [Key.LEFT_ALT]

    def test_ctrl_win_masks_win_only(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "win"))
        masked = _masked_releases(
            c,
            [
                (Key.LEFT_META, _D, 0),
                (Key.LEFT_CTRL, _D, 10),
                (Key.LEFT_CTRL, _U, 500),
                (Key.LEFT_META, _U, 2500),
            ],
        )
        assert masked == [Key.LEFT_META]

    def test_alt_only_combo_is_masked(self) -> None:
        # Previously a known limitation (#171): an alt-ONLY hotkey had no second
        # key to inject under. Swallow-and-replay covers it.
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("alt",))
        assert _masked_releases(c, [(Key.LEFT_ALT, _D, 0), (Key.LEFT_ALT, _U, 100)]) == [
            Key.LEFT_ALT
        ]

    def test_mouse_plus_alt_masks_alt_not_mouse(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("alt", "mouse4"))
        masked = _masked_releases(
            c,
            [
                (Key.LEFT_ALT, _D, 0),
                (Key.MOUSE_4, _D, 10),
                (Key.MOUSE_4, _U, 500),
                (Key.LEFT_ALT, _U, 510),
            ],
        )
        assert masked == [Key.LEFT_ALT]

    def test_mouse_only_combo_never_masks(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("mouse4",))
        assert _masked_releases(c, [(Key.MOUSE_4, _D, 0), (Key.MOUSE_4, _U, 100)]) == []


class TestCtrlAltOwnInjectionHazard:
    """With Ctrl in the combo, an injected Ctrl reaches the Windows hook as
    LEFT_CTRL (verified on Windows 11). These pin why the hook must drop
    Dictatem's own tagged injections before the classifier (#269 follow-up:
    the zero-audio first Ctrl+Alt dictation)."""

    def test_unfiltered_injected_ctrl_tap_would_stop_a_toggle_recording(self) -> None:
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "alt"))
        c.process_event(Key.LEFT_CTRL, _D, 0)
        c.process_event(Key.LEFT_ALT, _D, 10)
        _, ev = c.process_event(Key.LEFT_CTRL, _U, 80)
        assert ev is HotkeyEvent.TAP  # the user's toggle-start
        # An injected Ctrl down, if it reached the classifier, re-forms the
        # combo -> the bridge emits KEY_DOWN, which stops the toggle recording
        # milliseconds after it started (zero audio).
        c.process_event(Key.LEFT_CTRL, _D, 81)
        assert c.combo_held is True

    def test_unfiltered_injected_ctrl_up_during_paste_would_break_a_held_combo(
        self,
    ) -> None:
        # User still holding Ctrl+Alt when Ctrl+V is injected: the injected
        # Ctrl-up would drop LEFT_CTRL from the classifier while it's physically
        # down, faking a HOLD_END.
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "alt"))
        c.process_event(Key.LEFT_CTRL, _D, 0)
        c.process_event(Key.LEFT_ALT, _D, 10)
        assert c.tick(300) is HotkeyEvent.HOLD_START
        _, ev = c.process_event(Key.LEFT_CTRL, _U, 400)  # injected (unfiltered)
        assert ev is HotkeyEvent.HOLD_END

    def test_user_only_events_toggle_cleanly(self) -> None:
        # What the classifier sees with own injections filtered: one TAP, and no
        # combo until the user presses it again.
        c = HotkeyClassifier(tap_threshold_ms=200, modifiers=("ctrl", "alt"))
        c.process_event(Key.LEFT_CTRL, _D, 0)
        c.process_event(Key.LEFT_ALT, _D, 10)
        _, ev = c.process_event(Key.LEFT_CTRL, _U, 80)
        assert ev is HotkeyEvent.TAP
        c.process_event(Key.LEFT_ALT, _U, 85)
        assert c.combo_held is False
        assert c.tick(5000) is None


class TestOwnInjectionFilter:
    def test_tagged_injected_event_is_ours(self) -> None:
        assert is_own_injection(LLKHF_INJECTED, DICTATEM_INJECTION_TAG) is True

    def test_extended_flag_does_not_matter(self) -> None:
        assert is_own_injection(LLKHF_INJECTED | 0x01 | 0x80, DICTATEM_INJECTION_TAG)

    def test_physical_event_is_never_ours_even_with_tag(self) -> None:
        assert is_own_injection(0, DICTATEM_INJECTION_TAG) is False

    def test_other_tools_injection_is_not_ours(self) -> None:
        # An on-screen keyboard / AutoHotkey remap keeps driving the hotkey.
        assert is_own_injection(LLKHF_INJECTED, None) is False
        assert is_own_injection(LLKHF_INJECTED, 0x12345) is False


class TestSwallowOnlyAfterReplay:
    """Never-stuck invariant: a key-up is swallowed only if it was re-emitted."""

    def test_full_replay_allows_swallow(self) -> None:
        assert swallow_after_masked_replay(lambda: True) is True

    def test_short_sendinput_passes_key_up_through(self) -> None:
        assert swallow_after_masked_replay(lambda: False) is False

    def test_exception_passes_key_up_through(self) -> None:
        def boom() -> bool:
            raise OSError("SendInput blocked")

        assert swallow_after_masked_replay(boom) is False

    def test_non_bool_truthy_result_does_not_swallow(self) -> None:
        # Only an explicit True means "the key-up was re-injected".
        assert swallow_after_masked_replay(lambda: 3) is False  # type: ignore[return-value]
