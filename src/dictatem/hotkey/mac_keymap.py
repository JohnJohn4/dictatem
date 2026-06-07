"""Pure macOS key-code (CGKeyCode) → neutral ``Key`` translation.

Kept separate from the CGEventTap hook (which is macOS-only and
import-guarded) so the mapping is importable and unit-testable on any
platform. The Windows hook supplies its own analogous map (see ADR-0018).

The macOS-specific twist lives in :func:`flags_changed_action`: modifier
keys never produce keyDown/keyUp events through a CGEventTap — they arrive
as ``kCGEventFlagsChanged``, whose event type says nothing about press vs
release. The direction must be derived from the event's ``CGEventFlags``:
each physical modifier key has a stable device-dependent bit (the
``NX_DEVICE*`` masks from IOKit's ``IOLLEvent.h``) that is set exactly
while that key is down. Deriving the action is pure integer logic, so it
lives here — unit-tested on any platform — rather than in the native hook.
"""

from __future__ import annotations

from dictatem.hotkey.classifier import Key, KeyAction

# macOS virtual key codes the classifier cares about, named after their
# Carbon HIToolbox ``kVK_*`` constants (Events.h). Like Windows, the codes
# are side-specific (e.g. 0x37/0x36 for left/right Command).
KVK_COMMAND = 0x37
KVK_RIGHT_COMMAND = 0x36
KVK_OPTION = 0x3A
KVK_RIGHT_OPTION = 0x3D
KVK_CONTROL = 0x3B
KVK_RIGHT_CONTROL = 0x3E
KVK_SHIFT = 0x38
KVK_RIGHT_SHIFT = 0x3C
KVK_ESCAPE = 0x35
KVK_LEFT_ARROW = 0x7B
KVK_UP_ARROW = 0x7E
KVK_RIGHT_ARROW = 0x7C
KVK_DOWN_ARROW = 0x7D

_KEYCODE_TO_KEY: dict[int, Key] = {
    KVK_COMMAND: Key.LEFT_META,
    KVK_RIGHT_COMMAND: Key.RIGHT_META,
    KVK_OPTION: Key.LEFT_ALT,
    KVK_RIGHT_OPTION: Key.RIGHT_ALT,
    KVK_CONTROL: Key.LEFT_CTRL,
    KVK_RIGHT_CONTROL: Key.RIGHT_CTRL,
    KVK_SHIFT: Key.LEFT_SHIFT,
    KVK_RIGHT_SHIFT: Key.RIGHT_SHIFT,
    KVK_ESCAPE: Key.ESCAPE,
    KVK_LEFT_ARROW: Key.LEFT,
    KVK_UP_ARROW: Key.UP,
    KVK_RIGHT_ARROW: Key.RIGHT,
    KVK_DOWN_ARROW: Key.DOWN,
}


def keycode_to_key(keycode: int) -> Key:
    """Translate a macOS CGKeyCode to a neutral ``Key``.

    Unrecognised codes map to ``Key.OTHER`` — tracked by the classifier but
    inert (never part of a modifier combo, an arrow, or escape).
    """
    return _KEYCODE_TO_KEY.get(keycode, Key.OTHER)


# Device-dependent modifier bits in ``CGEventFlags``, from IOKit's
# ``IOLLEvent.h`` (``NX_DEVICE…KEYMASK``). The public ``kCGEventFlagMask*``
# bits are coalesced per modifier *group* — left and right Command both set
# the same 0x100000 — so they cannot say which side a flags-changed event is
# about; these per-key device bits are the only stable per-side state in the
# flags. They are "device-dependent" in name but stable in practice for
# keyboards, which is how left/right modifier tracking is conventionally done.
NX_DEVICELCTLKEYMASK = 0x00000001
NX_DEVICELSHIFTKEYMASK = 0x00000002
NX_DEVICERSHIFTKEYMASK = 0x00000004
NX_DEVICELCMDKEYMASK = 0x00000008
NX_DEVICERCMDKEYMASK = 0x00000010
NX_DEVICELALTKEYMASK = 0x00000020
NX_DEVICERALTKEYMASK = 0x00000040
NX_DEVICERCTLKEYMASK = 0x00002000

# Which device bit answers "is this modifier keycode down?". Only the eight
# side-specific combo modifiers belong here: caps lock and fn also arrive as
# ``kCGEventFlagsChanged`` but are not part of any hotkey vocabulary, so the
# hook skips them (``flags_changed_action`` returns ``None``).
_KEYCODE_TO_DEVICE_BIT: dict[int, int] = {
    KVK_COMMAND: NX_DEVICELCMDKEYMASK,
    KVK_RIGHT_COMMAND: NX_DEVICERCMDKEYMASK,
    KVK_OPTION: NX_DEVICELALTKEYMASK,
    KVK_RIGHT_OPTION: NX_DEVICERALTKEYMASK,
    KVK_CONTROL: NX_DEVICELCTLKEYMASK,
    KVK_RIGHT_CONTROL: NX_DEVICERCTLKEYMASK,
    KVK_SHIFT: NX_DEVICELSHIFTKEYMASK,
    KVK_RIGHT_SHIFT: NX_DEVICERSHIFTKEYMASK,
}


def flags_changed_action(keycode: int, flags: int) -> KeyAction | None:
    """Derive press vs release for a ``kCGEventFlagsChanged`` event.

    A CGEventTap never sees keyDown/keyUp for modifier keys — both press and
    release arrive as the same ``kCGEventFlagsChanged`` event type. The
    direction is encoded in the event's flags: the keycode's device-dependent
    bit is set while that key is down and clear once it is released, per side
    (releasing left Command while right Command stays held clears only the
    left bit). Returns ``None`` for keycodes that are not one of the eight
    side-specific modifiers (e.g. caps lock, fn) — the hook passes those
    events through untouched.
    """
    device_bit = _KEYCODE_TO_DEVICE_BIT.get(keycode)
    if device_bit is None:
        return None
    return KeyAction.KEY_DOWN if flags & device_bit else KeyAction.KEY_UP
