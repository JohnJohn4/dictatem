"""Pure-logic hotkey classifier — no OS dependencies.

Reasons about platform-neutral key identities (``Key``), never raw OS key
codes: each platform's keyboard hook translates its native codes to ``Key``
before feeding this classifier, and modifier names from config resolve to
``Key`` groups here. See ADR-0018 and ``CONTEXT.md#hotkey-combo``.
"""

from __future__ import annotations

import enum


class Key(enum.Enum):
    """A platform-neutral key identity the classifier reasons about.

    Each OS keyboard-hook adapter maps its native key codes onto these values
    (e.g. Windows ``0x5B`` and macOS Command both → ``LEFT_META``); unrecognised
    keys map to ``OTHER`` (tracked but inert). Left/right modifier variants are
    kept distinct so that holding either side sustains a combo — matching the
    per-side OS codes — while both belong to the same modifier group.
    """

    LEFT_META = "left_meta"
    RIGHT_META = "right_meta"
    LEFT_ALT = "left_alt"
    RIGHT_ALT = "right_alt"
    LEFT_CTRL = "left_ctrl"
    RIGHT_CTRL = "right_ctrl"
    LEFT_SHIFT = "left_shift"
    RIGHT_SHIFT = "right_shift"
    # Mouse buttons are trigger inputs in the same combo as modifiers (ADR-0020).
    # ``MOUSE_4``/``MOUSE_5`` are the two side buttons; ``MOUSE_MIDDLE`` is the
    # wheel click. Left/right click are never trigger inputs (primary interaction).
    MOUSE_4 = "mouse_4"
    MOUSE_5 = "mouse_5"
    MOUSE_MIDDLE = "mouse_middle"
    ESCAPE = "escape"
    LEFT = "left"
    UP = "up"
    RIGHT = "right"
    DOWN = "down"
    OTHER = "other"


META_KEYS = frozenset({Key.LEFT_META, Key.RIGHT_META})
ALT_KEYS = frozenset({Key.LEFT_ALT, Key.RIGHT_ALT})
CTRL_KEYS = frozenset({Key.LEFT_CTRL, Key.RIGHT_CTRL})
SHIFT_KEYS = frozenset({Key.LEFT_SHIFT, Key.RIGHT_SHIFT})
ARROW_KEYS = frozenset({Key.LEFT, Key.UP, Key.RIGHT, Key.DOWN})
# Mouse-button identities, kept distinct from modifier keys: a mouse button is
# conditionally suppressed (ADR-0020) whereas a modifier always passes through.
MOUSE_KEYS = frozenset({Key.MOUSE_4, Key.MOUSE_5, Key.MOUSE_MIDDLE})
# Modifiers whose *lone* release fires an OS side-effect: Alt activates the menu
# bar, Meta/Win pops the Start menu. When releasing a Win+Alt-style chord these
# can misfire and steal the caret (#171); see ``pending_mask``.
SIDE_EFFECT_KEYS = META_KEYS | ALT_KEYS

# Trigger-input name → neutral Key group. ``meta`` is the canonical name for the
# OS key (Windows key / Command); ``win`` is a permanent alias for it. Mouse
# buttons join the same map so the classifier reasons about them exactly like
# modifier keys. See ADR-0010, ADR-0018, ADR-0020, and ``CONTEXT.md#hotkey-combo``.
_MODIFIER_MAP: dict[str, frozenset[Key]] = {
    "meta": META_KEYS,
    "win": META_KEYS,
    "alt": ALT_KEYS,
    "ctrl": CTRL_KEYS,
    "shift": SHIFT_KEYS,
    "mouse4": frozenset({Key.MOUSE_4}),
    "mouse5": frozenset({Key.MOUSE_5}),
    "middle": frozenset({Key.MOUSE_MIDDLE}),
}


class KeyAction(enum.Enum):
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"


class HotkeyEvent(enum.Enum):
    TAP = "tap"
    HOLD_START = "hold_start"
    HOLD_END = "hold_end"
    ESC = "esc"


class HookDecision(enum.Enum):
    SUPPRESS = "suppress"
    PASS_THROUGH = "pass_through"


class HotkeyClassifier:
    def __init__(
        self,
        tap_threshold_ms: int = 200,
        modifiers: tuple[str, ...] = ("win", "alt"),
    ) -> None:
        self._tap_threshold_ms = tap_threshold_ms
        self._modifier_groups: list[frozenset[Key]] = [
            _MODIFIER_MAP[name] for name in modifiers if name in _MODIFIER_MAP
        ]
        self._keys_down: set[Key] = set()
        self._active = False
        self._combo_pressed_at: int | None = None
        self._hold_emitted = False
        # Mouse buttons whose DOWN was suppressed; their matching UP is
        # suppressed too, to keep the down/up pair balanced (ADR-0020).
        self._suppressed_mouse_down: set[Key] = set()
        # --- Alt/Win menu/Start mask (#171, #177) ---
        # Per side-effect key (Alt/Meta) currently down: whether its press
        # session is still "lone" (no non-combo keyboard key went down since it
        # did), and whether the hotkey combo was held at some point during that
        # session (a Dictatem session — only those are masked, so a user's own
        # lone Alt still opens the menu bar). Decided at THAT key's own key-up
        # and read via ``pending_mask``.
        #
        # The native mask is injected with Dictatem's injection tag, and the
        # Windows hook drops tagged events before they reach ``process_event``
        # (``win32_keymap.is_own_injection``) — so neither the mask nor the
        # replayed key-up nor the paste rail's Ctrl+V can perturb the combo.
        self._session_lone: dict[Key, bool] = {}
        self._session_dictated: set[Key] = set()
        self._pending_mask = False

    def set_active(self, active: bool) -> None:
        self._active = active

    @property
    def combo_held(self) -> bool:
        if not self._modifier_groups:
            return False
        return all(bool(self._keys_down & group) for group in self._modifier_groups)

    @property
    def pending_mask(self) -> bool:
        """Whether the just-processed KEY-UP must be swallowed and replayed behind
        a mask key (#171, #177).

        A lone Alt-up activates the menu bar and a lone Win-up pops the Start
        menu, which steals keyboard focus so the next Ctrl+V lands nowhere. True
        when *this* event is the key-up of a combo Alt/Meta key whose press
        session (a) saw the hotkey combo held — a Dictatem session, armed or
        just ended — and (b) is still lone (no non-combo keyboard key went down
        during it). The native hook then swallows the key-up and re-emits
        ``[mask down, mask up, same key-up]`` so the OS sees the session as not
        lone. Deciding at the key's own key-up (rather than when the combo
        breaks) is what makes it robust to both a fast tap — whose key-ups are
        already queued together — and a long-delayed second release (#177).

        Conservative on purpose: masking a session the OS wouldn't have treated
        as lone is harmless (the mask key is unassigned), whereas missing one
        pops the menu. Reflects only the most recent ``process_event`` call."""
        return self._pending_mask

    def process_event(
        self, key: Key, action: KeyAction, timestamp_ms: int
    ) -> tuple[HookDecision, HotkeyEvent | None]:
        # Recomputed for the current event only; a key-down/tick never masks.
        self._pending_mask = False
        if action is KeyAction.KEY_DOWN:
            return self._on_key_down(key, timestamp_ms)
        return self._on_key_up(key, timestamp_ms)

    def tick(self, timestamp_ms: int) -> HotkeyEvent | None:
        if (
            self._combo_pressed_at is not None
            and not self._hold_emitted
            and self.combo_held
            and (timestamp_ms - self._combo_pressed_at) >= self._tap_threshold_ms
        ):
            self._hold_emitted = True
            return HotkeyEvent.HOLD_START
        return None

    def _on_key_down(
        self, key: Key, timestamp_ms: int
    ) -> tuple[HookDecision, HotkeyEvent | None]:
        self._track_session_on_key_down(key)
        if key in self._keys_down:
            return HookDecision.PASS_THROUGH, None

        was_combo = self.combo_held
        self._keys_down.add(key)
        is_combo = self.combo_held
        if key in SIDE_EFFECT_KEYS and self._is_trigger_button(key):
            self._session_lone[key] = True
        if is_combo:
            self._mark_sessions_dictated()

        if not was_combo and is_combo:
            self._combo_pressed_at = timestamp_ms
            self._hold_emitted = False

        if is_combo and key in ARROW_KEYS:
            return HookDecision.SUPPRESS, None

        # A trigger mouse button is suppressed iff its press completes/sustains
        # the combo, so a bare button (e.g. Mouse4 = browser-back) still works
        # when the combo also needs a held modifier (ADR-0020). The matching UP
        # is paired off the recorded DOWN decision.
        if key in MOUSE_KEYS and self._is_trigger_button(key):
            if is_combo:
                self._suppressed_mouse_down.add(key)
                return HookDecision.SUPPRESS, None
            self._suppressed_mouse_down.discard(key)

        if key is Key.ESCAPE and self._active:
            return HookDecision.PASS_THROUGH, HotkeyEvent.ESC

        return HookDecision.PASS_THROUGH, None

    def _is_trigger_button(self, key: Key) -> bool:
        """True if *key* (a mouse button or a keyboard modifier) is bound in the
        configured combo."""
        return any(key in group for group in self._modifier_groups)

    def _on_key_up(
        self, key: Key, timestamp_ms: int
    ) -> tuple[HookDecision, HotkeyEvent | None]:
        if key not in self._keys_down:
            return HookDecision.PASS_THROUGH, None

        was_combo = self.combo_held
        self._keys_down.discard(key)
        is_combo = self.combo_held

        # Pair the mouse-button UP with its recorded DOWN decision, regardless of
        # whether the combo broke in between (ADR-0020).
        mouse_decision = HookDecision.PASS_THROUGH
        if key in MOUSE_KEYS and key in self._suppressed_mouse_down:
            self._suppressed_mouse_down.discard(key)
            mouse_decision = HookDecision.SUPPRESS

        # Decide the menu/Start mask for this release (#171/#177) at the
        # side-effect key's OWN key-up, then close its session.
        self._pending_mask = self._compute_keyup_mask(key)
        self._session_lone.pop(key, None)
        self._session_dictated.discard(key)

        if was_combo and not is_combo and self._combo_pressed_at is not None:
            pressed_at = self._combo_pressed_at
            self._combo_pressed_at = None

            if self._hold_emitted:
                self._hold_emitted = False
                return mouse_decision, HotkeyEvent.HOLD_END

            elapsed = timestamp_ms - pressed_at
            if elapsed < self._tap_threshold_ms:
                return mouse_decision, HotkeyEvent.TAP

        return mouse_decision, None

    def _compute_keyup_mask(self, released_key: Key) -> bool:
        """Whether *released_key*'s key-up must be masked (see ``pending_mask``).

        Only a configured Alt/Meta combo key, whose session was a Dictatem
        session (combo held during it) and is still lone. Mouse buttons and
        Ctrl/Shift never mask: they have no lone-release side-effect."""
        if released_key not in SIDE_EFFECT_KEYS:
            return False
        if not self._is_trigger_button(released_key):
            return False
        return released_key in self._session_dictated and self._session_lone.get(
            released_key, False
        )

    def _track_session_on_key_down(self, key: Key) -> None:
        """A non-combo keyboard key going down (including auto-repeat, and every
        ``Key.OTHER`` — which aggregates all unmapped keys) ends the loneness of
        every Alt/Meta session in progress: the OS won't fire the menu/Start
        side-effect on their release (e.g. Alt+Tab mid-hold). Combo modifiers
        and mouse buttons deliberately do NOT break loneness — whether the OS
        counts them is uncertain, and over-masking is harmless."""
        if key in MOUSE_KEYS or self._is_trigger_button(key):
            return
        for held in self._session_lone:
            self._session_lone[held] = False

    def _mark_sessions_dictated(self) -> None:
        """The combo is held: every Alt/Meta combo key down now is in a Dictatem
        session, until its own key-up (so a long-delayed second release is still
        masked, #177)."""
        for held in self._keys_down:
            if held in SIDE_EFFECT_KEYS and self._is_trigger_button(held):
                self._session_dictated.add(held)
