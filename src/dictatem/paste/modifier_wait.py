"""Wait for held modifier keys to be released before injecting keystrokes.

Pure decision logic: no OS imports. The modifier-state reader, clock and sleep
are injected so the wait is unit-testable without a keyboard.

Why: SendInput-injected keystrokes combine with whatever modifiers are
*logically* down at that instant. If the user is still holding the hotkey
(e.g. Win+Alt held slightly long, pressed again during TRANSCRIBING, or held
mid-press when a silence-timeout auto-stop fires), the injected Ctrl+V reaches
the target as Ctrl+Alt+V / Win+Ctrl+V (Notepad++'s Compare plugin opens "No SVN
data found"; other apps silently ignore it), and the Trigger Fire typed path's
Backspaces/characters become Alt/Win/Ctrl shortcuts. So the paste pipeline waits,
briefly and bounded, until no modifier is down.

Ctrl and the #171 neutralizing mask: the hook injects its masking Ctrl down+up
as ONE atomic SendInput batch, and the paste rail's own Ctrl+V is likewise one
batch, so an injected Ctrl is logically down for microseconds at most. A poll
that happens to land inside that window just sees Ctrl released on the next
poll — it can extend the wait by one interval, never deadlock it. Ctrl is kept
in the set (not excluded) because a physically held Ctrl genuinely corrupts the
typed path (Ctrl+Backspace deletes a whole word).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# Poll interval and cap. The cap covers a hotkey held slightly long or re-pressed
# during TRANSCRIBING (typically tens to a few hundred ms) while bounding how
# long the Qt GUI thread — which runs the paste — can be blocked in the
# pathological case (a key held down for seconds, or a logically stuck key).
MODIFIER_POLL_S = 0.015
MODIFIER_WAIT_CAP_S = 1.5
_EPSILON_S = 1e-6


# Windows virtual-key codes polled by the win32 adapter, by modifier name. The
# generic VK_SHIFT/VK_CONTROL/VK_MENU cover both sides; Win has no generic code.
WIN32_MODIFIER_VKS: tuple[tuple[str, int], ...] = (
    ("alt", 0x12),  # VK_MENU
    ("win", 0x5B),  # VK_LWIN
    ("win", 0x5C),  # VK_RWIN
    ("shift", 0x10),  # VK_SHIFT
    ("ctrl", 0x11),  # VK_CONTROL
)


def held_modifier_names(is_vk_down: Callable[[int], bool]) -> frozenset[str]:
    """Map a per-virtual-key "is down" probe to the set of held modifier names."""
    return frozenset(name for name, vk in WIN32_MODIFIER_VKS if is_vk_down(vk))


@dataclass(frozen=True)
class ModifierWait:
    """Outcome of :func:`wait_for_modifiers_released`.

    *released* is False only when the cap expired with a modifier still down.
    *initially_held* names the modifiers seen on the first poll (empty when no
    wait was needed); *still_held* the ones down at the end (empty on release).
    """

    released: bool
    waited_s: float
    initially_held: frozenset[str]
    still_held: frozenset[str]

    @property
    def needed(self) -> bool:
        """Whether any wait happened at all (a modifier was down on the first poll)."""
        return bool(self.initially_held)


def wait_for_modifiers_released(
    read_held: Callable[[], frozenset[str]],
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    cap_s: float = MODIFIER_WAIT_CAP_S,
    poll_s: float = MODIFIER_POLL_S,
) -> ModifierWait:
    """Poll *read_held* until it reports no modifier down, or *cap_s* elapses.

    Returns immediately (no sleep) when nothing is held — the common case.
    """
    start = clock()
    held = read_held()
    initially_held = held
    # Hard bound on polls as well as on time: floating-point rounding can leave
    # ``cap_s - elapsed`` a vanishing positive remainder (sleeping ever-smaller
    # slivers forever), and a stalled clock must never hang the GUI thread.
    max_polls = math.ceil(cap_s / poll_s) + 1 if poll_s > 0 else 0
    polls = 0
    while held:
        elapsed = clock() - start
        remaining = cap_s - elapsed
        if remaining <= _EPSILON_S or polls >= max_polls:
            return ModifierWait(
                released=False,
                waited_s=elapsed,
                initially_held=initially_held,
                still_held=held,
            )
        sleep(min(poll_s, remaining))
        polls += 1
        held = read_held()
    return ModifierWait(
        released=True,
        waited_s=clock() - start,
        initially_held=initially_held,
        still_held=frozenset(),
    )
