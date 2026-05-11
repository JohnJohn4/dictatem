"""Pure-logic hotkey classifier — no OS dependencies."""

from __future__ import annotations

import enum

# Windows virtual-key codes (subset needed by the classifier)
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_ESCAPE = 0x1B
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28

CTRL_VKS = frozenset({VK_LCONTROL, VK_RCONTROL})
WIN_VKS = frozenset({VK_LWIN, VK_RWIN})
ARROW_VKS = frozenset({VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN})


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
    def __init__(self, tap_threshold_ms: int = 200) -> None:
        self._tap_threshold_ms = tap_threshold_ms
        self._keys_down: set[int] = set()
        self._active = False
        self._combo_pressed_at: int | None = None
        self._hold_emitted = False

    def set_active(self, active: bool) -> None:
        self._active = active

    @property
    def combo_held(self) -> bool:
        return bool(self._keys_down & CTRL_VKS) and bool(self._keys_down & WIN_VKS)

    def process_event(
        self, vk: int, action: KeyAction, timestamp_ms: int
    ) -> tuple[HookDecision, HotkeyEvent | None]:
        if action is KeyAction.KEY_DOWN:
            return self._on_key_down(vk, timestamp_ms)
        return self._on_key_up(vk, timestamp_ms)

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

    def _on_key_down(self, vk: int, timestamp_ms: int) -> tuple[HookDecision, HotkeyEvent | None]:
        if vk in self._keys_down:
            return HookDecision.PASS_THROUGH, None

        was_combo = self.combo_held
        self._keys_down.add(vk)
        is_combo = self.combo_held

        if not was_combo and is_combo:
            self._combo_pressed_at = timestamp_ms
            self._hold_emitted = False

        if is_combo and vk in ARROW_VKS:
            return HookDecision.SUPPRESS, None

        if vk == VK_ESCAPE and self._active:
            return HookDecision.PASS_THROUGH, HotkeyEvent.ESC

        return HookDecision.PASS_THROUGH, None

    def _on_key_up(self, vk: int, timestamp_ms: int) -> tuple[HookDecision, HotkeyEvent | None]:
        if vk not in self._keys_down:
            return HookDecision.PASS_THROUGH, None

        was_combo = self.combo_held
        self._keys_down.discard(vk)
        is_combo = self.combo_held

        if was_combo and not is_combo and self._combo_pressed_at is not None:
            pressed_at = self._combo_pressed_at
            self._combo_pressed_at = None

            if self._hold_emitted:
                self._hold_emitted = False
                return HookDecision.PASS_THROUGH, HotkeyEvent.HOLD_END

            elapsed = timestamp_ms - pressed_at
            if elapsed < self._tap_threshold_ms:
                return HookDecision.PASS_THROUGH, HotkeyEvent.TAP

        return HookDecision.PASS_THROUGH, None
