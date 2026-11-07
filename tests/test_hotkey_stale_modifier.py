"""A missed key-up must not turn a lone Alt into the Win+Alt hotkey.

Field bug (owner, 2026-11-04): users' "Alt+Enter in Excel" sometimes started a
dictation, intermittently and hard to reproduce. Cause: the classifier tracked
held keys only from hook events, so a key whose key-up the hook never saw stayed
"held" forever:

* Win+L: Win goes down on the user desktop, but its key-up happens on the
  secure (lock) desktop, which low-level hooks don't see;
* releasing a key while an elevated (admin) window has focus is invisible to a
  non-elevated hook (UIPI).

With Win stuck, any later Alt press completed "Win+Alt". The fix asks the OS
for the physical state of the other combo keys at the moment a key-down would
complete the combo, and drops any that aren't really held.
"""

from __future__ import annotations

import random

import pytest

from dictatem.hotkey.classifier import HotkeyClassifier, HotkeyEvent, Key, KeyAction
from dictatem.hotkey.mac_keymap import (
    KVK_COMMAND,
    KVK_OPTION,
    NX_DEVICELALTKEYMASK,
    NX_DEVICELCMDKEYMASK,
    EventFlagsState,
    flags_changed_action,
    keycode_to_key,
)

DOWN, UP = KeyAction.KEY_DOWN, KeyAction.KEY_UP


def _feed(c: HotkeyClassifier, events: list[tuple[Key, KeyAction, int]]) -> list[HotkeyEvent]:
    out: list[HotkeyEvent] = []
    for key, action, t in events:
        _decision, event = c.process_event(key, action, t)
        if event is not None:
            out.append(event)
        tick = c.tick(t)
        if tick is not None:
            out.append(tick)
    return out


# Win+L: Win down seen; Win up happened on the lock screen (never seen). Later,
# Alt+Enter in Excel: Alt down, Enter down/up, Alt up, quickly (a "tap").
WIN_L_THEN_ALT_ENTER = [
    (Key.LEFT_META, DOWN, 0),
    (Key.OTHER, DOWN, 50),  # L
    (Key.OTHER, UP, 120),
    # ... locked, unlocked; Win's key-up was never delivered ...
    (Key.LEFT_ALT, DOWN, 600_000),
    (Key.OTHER, DOWN, 600_040),  # Enter
    (Key.OTHER, UP, 600_080),
    (Key.LEFT_ALT, UP, 600_120),
]


def test_reproduces_the_field_bug_without_a_physical_check() -> None:
    c = HotkeyClassifier(tap_threshold_ms=200)
    assert _feed(c, WIN_L_THEN_ALT_ENTER) == [HotkeyEvent.TAP]  # dictation toggled on


def test_physical_check_drops_the_stale_win_and_nothing_fires() -> None:
    physically_down = {Key.LEFT_ALT}  # Win is really up after the unlock
    c = HotkeyClassifier(
        tap_threshold_ms=200, physical_state=lambda k: k in physically_down
    )
    events: list[HotkeyEvent] = []
    dropped: list[tuple[Key, ...]] = []
    for key, action, t in WIN_L_THEN_ALT_ENTER:
        _d, ev = c.process_event(key, action, t)
        if c.last_dropped_stale:
            dropped.append(c.last_dropped_stale)
        if ev is not None:
            events.append(ev)
    assert events == []
    assert dropped == [(Key.LEFT_META,)]
    assert not c.combo_held


def test_a_real_win_alt_tap_still_works_with_the_check() -> None:
    held: set[Key] = set()
    c = HotkeyClassifier(tap_threshold_ms=200, physical_state=lambda k: k in held)

    def press(k: Key, t: int) -> HotkeyEvent | None:
        held.add(k)
        return c.process_event(k, DOWN, t)[1]

    def release(k: Key, t: int) -> HotkeyEvent | None:
        held.discard(k)
        return c.process_event(k, UP, t)[1]

    assert press(Key.LEFT_META, 0) is None
    assert press(Key.LEFT_ALT, 30) is None
    assert release(Key.LEFT_ALT, 120) is HotkeyEvent.TAP
    release(Key.LEFT_META, 140)
    assert c.last_dropped_stale == ()


def test_unknown_physical_state_trusts_the_events() -> None:
    c = HotkeyClassifier(tap_threshold_ms=200, physical_state=lambda k: None)
    assert _feed(c, WIN_L_THEN_ALT_ENTER) == [HotkeyEvent.TAP]


def test_stuck_alt_then_a_lone_win_press_is_also_ignored() -> None:
    # Alt released over an admin window (key-up unseen), later a lone Win tap.
    physically_down: set[Key] = set()
    c = HotkeyClassifier(
        tap_threshold_ms=200, physical_state=lambda k: k in physically_down
    )
    _feed(c, [(Key.LEFT_ALT, DOWN, 0)])
    physically_down.add(Key.LEFT_META)
    events = _feed(c, [(Key.LEFT_META, DOWN, 5_000)])
    physically_down.discard(Key.LEFT_META)
    events += _feed(c, [(Key.LEFT_META, UP, 5_080)])
    assert events == []


# --- "try a whole bunch of key presses" ---------------------------------------

_KEYS = [
    Key.LEFT_META, Key.RIGHT_META, Key.LEFT_ALT, Key.RIGHT_ALT, Key.LEFT_CTRL,
    Key.LEFT_SHIFT, Key.ESCAPE, Key.LEFT, Key.UP, Key.OTHER,
]
_META = {Key.LEFT_META, Key.RIGHT_META}
_ALT = {Key.LEFT_ALT, Key.RIGHT_ALT}


@pytest.mark.parametrize("seed", range(300))
def test_fuzz_never_fires_unless_win_and_alt_are_really_held_together(seed: int) -> None:
    """Random typing with randomly missed key-ups, never physically holding a
    Win key and an Alt key at the same time, must never start a dictation."""
    rng = random.Random(seed)
    physically_down: set[Key] = set()
    c = HotkeyClassifier(
        tap_threshold_ms=200, physical_state=lambda k: k in physically_down
    )
    t = 0
    for _ in range(200):
        t += rng.randint(5, 400)
        key = rng.choice(_KEYS)
        if key in physically_down:
            physically_down.discard(key)
            if rng.random() < 0.15:  # the hook misses this key-up (Win+L, UIPI)
                continue
            _d, ev = c.process_event(key, UP, t)
        else:
            other_group = _ALT if key in _META else _META if key in _ALT else set()
            if physically_down & other_group:
                continue  # would genuinely press the hotkey; not this test
            physically_down.add(key)
            _d, ev = c.process_event(key, DOWN, t)
        tick = c.tick(t)
        assert ev not in (HotkeyEvent.TAP, HotkeyEvent.HOLD_START), (seed, key, t)
        assert tick is not HotkeyEvent.HOLD_START, (seed, key, t)


@pytest.mark.parametrize("seed", range(100))
def test_fuzz_genuine_combos_still_fire_after_missed_key_ups(seed: int) -> None:
    """After random noise with missed key-ups, a real Win+Alt tap still fires."""
    rng = random.Random(seed)
    physically_down: set[Key] = set()
    c = HotkeyClassifier(
        tap_threshold_ms=200, physical_state=lambda k: k in physically_down
    )
    t = 0
    for _ in range(100):
        t += rng.randint(5, 400)
        key = rng.choice(_KEYS)
        if key in physically_down:
            physically_down.discard(key)
            if rng.random() < 0.15:
                continue
            c.process_event(key, UP, t)
        else:
            other_group = _ALT if key in _META else _META if key in _ALT else set()
            if physically_down & other_group:
                continue
            physically_down.add(key)
            c.process_event(key, DOWN, t)
    # Let go of everything (some key-ups missed), then a clean, real Win+Alt tap.
    for key in list(physically_down):
        physically_down.discard(key)
        t += 10
        if rng.random() < 0.5:
            c.process_event(key, UP, t)
    t += 1_000
    physically_down.add(Key.LEFT_META)
    c.process_event(Key.LEFT_META, DOWN, t)
    physically_down.add(Key.LEFT_ALT)
    c.process_event(Key.LEFT_ALT, DOWN, t + 30)
    assert c.combo_held
    physically_down.discard(Key.LEFT_ALT)
    _d, ev = c.process_event(Key.LEFT_ALT, UP, t + 120)
    assert ev is HotkeyEvent.TAP, seed


def test_physical_key_state_reads_the_high_bit() -> None:
    from dictatem.hotkey.win32_keymap import physical_key_state

    assert physical_key_state(Key.LEFT_META, lambda vk: 0x8000 if vk == 0x5B else 0) is True
    # Only the low "pressed since last call" bit set: not physically down.
    assert physical_key_state(Key.LEFT_META, lambda vk: 0x0001) is False
    assert physical_key_state(Key.OTHER, lambda vk: 0x8000) is None


# --- macOS (#308): a stuck Command/Option -------------------------------------
#
# The CGEventTap can miss a modifier release too (Secure Keyboard Entry in
# Terminal, the Control-Command-Q lock screen). macOS has no GetAsyncKeyState,
# but every kCGEventFlagsChanged event carries the full device-dependent
# modifier flags, so the event that would complete the combo already says
# whether the combo's other key is really down.

CMD, OPT = NX_DEVICELCMDKEYMASK, NX_DEVICELALTKEYMASK


def _feed_mac(events: list[tuple[int, int, int]]) -> list[HotkeyEvent]:
    """Feed (keycode, flags, t) flags-changed events the way the mac hook does:
    the event's flags are the physical state while the classifier runs."""
    state = EventFlagsState()
    c = HotkeyClassifier(tap_threshold_ms=200, physical_state=state)
    out: list[HotkeyEvent] = []
    for keycode, flags, t in events:
        action = flags_changed_action(keycode, flags)
        assert action is not None
        with state.classifying(flags):
            _d, ev = c.process_event(keycode_to_key(keycode), action, t)
        if ev is not None:
            out.append(ev)
    return out


def test_mac_stuck_command_then_a_lone_option_tap_is_ignored() -> None:
    events = _feed_mac(
        [
            (KVK_COMMAND, CMD, 0),
            # ... Command released under Secure Keyboard Entry: never seen ...
            (KVK_OPTION, OPT, 60_000),  # this event's flags: Command is up
            (KVK_OPTION, 0, 60_080),
        ]
    )
    assert events == []


def test_mac_a_real_command_option_tap_still_fires() -> None:
    events = _feed_mac(
        [
            (KVK_COMMAND, CMD, 0),
            (KVK_OPTION, CMD | OPT, 30),
            (KVK_OPTION, CMD, 120),
            (KVK_COMMAND, 0, 140),
        ]
    )
    assert events == [HotkeyEvent.TAP]
