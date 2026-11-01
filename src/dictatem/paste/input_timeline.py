"""Recent keyboard-input timeline + the pre-injection settle decision (#269).

Pure logic: no OS imports. The Windows keyboard hook feeds every event it sees
into an :class:`InputTimeline` (via the keystroke adapter), and the adapter
consults it right before injecting a paste or Trigger Fire. Times are
``time.monotonic()`` seconds supplied by the caller, so everything here is
unit-testable with a fake clock.

Why a settle: the hook swallows a lone Alt/Win key-up at the end of a Dictatem
session and re-emits it behind the menu mask key (#171/#177). That replayed
key-up is *asynchronous*: SendInput queues it, the hook sees it only after the
current hook callback returns, and only then is it posted to the foreground
thread, whose thread key state (``GetKeyState``, which Scintilla reads on
WM_KEYDOWN) changes only when that thread dequeues it. The paste rail sends its
Ctrl+V 0.2-1 s after the hotkey release, so this is normally long done; but on
the quick paths (a fast transcription, the "paste" voice action) the Ctrl+V can
land right behind the replay. The settle closes that window cheaply:

* if a masked replay was sent but the hook hasn't yet seen its key-up come
  back, wait for it (it's tagged, so the hook can signal it), up to
  ``REPLAY_OBSERVE_CAP_S``;
* then, if the last modifier key-up (physical, or the observed replay) was less
  than ``POST_RELEASE_SETTLE_S`` ago, wait out the remainder so the target's
  thread has dequeued it before our batch arrives.

Both are bounded and almost always zero (the user released the hotkey long
before transcription finished), so the common paste pays nothing.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# How long to wait for the hook to observe a replayed key-up it just sent. The
# replay is normally observed within a millisecond or two; the cap only bounds a
# pathological case (hook stalled / uninstalled) so the GUI thread can't hang.
REPLAY_OBSERVE_CAP_S = 0.25
# Minimum gap between the last modifier key-up and our injection.
POST_RELEASE_SETTLE_S = 0.050
# Poll interval while waiting for the replayed key-up to be observed.
SETTLE_POLL_S = 0.005
# "Did the hook swallow/replay a key-up recently?" window for the diagnostics.
RECENT_REPLAY_WINDOW_S = 1.0

# Hook-reported virtual-key codes, by modifier family. The low-level hook
# reports side-specific codes (VK_LMENU...) but a replay could in principle be
# reported generically, so the replay match is by family.
_ALT_VKS = frozenset({0x12, 0xA4, 0xA5})  # VK_MENU, VK_LMENU, VK_RMENU
_WIN_VKS = frozenset({0x5B, 0x5C})  # VK_LWIN, VK_RWIN
_CTRL_VKS = frozenset({0x11, 0xA2, 0xA3})  # VK_CONTROL, VK_LCONTROL, VK_RCONTROL
_SHIFT_VKS = frozenset({0x10, 0xA0, 0xA1})  # VK_SHIFT, VK_LSHIFT, VK_RSHIFT
_FAMILIES = (_ALT_VKS, _WIN_VKS, _CTRL_VKS, _SHIFT_VKS)
MODIFIER_HOOK_VKS = _ALT_VKS | _WIN_VKS | _CTRL_VKS | _SHIFT_VKS


def _same_family(a: int, b: int) -> bool:
    return any(a in fam and b in fam for fam in _FAMILIES)


@dataclass(frozen=True)
class TimelineView:
    """A consistent snapshot of :class:`InputTimeline` (all times monotonic s)."""

    last_modifier_up_s: float | None
    last_replay_sent_s: float | None
    replay_pending: bool


class InputTimeline:
    """Thread-safe record of recent modifier releases and masked replays.

    Written from the keyboard-hook thread, read from the GUI thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_modifier_up_s: float | None = None
        self._last_replay_sent_s: float | None = None
        self._pending_replay_vk: int | None = None

    def note_key(self, vk: int, is_down: bool, own_injection: bool, now: float) -> None:
        """Record one hooked key event (called for every event the hook sees)."""
        if is_down or vk not in MODIFIER_HOOK_VKS:
            return
        with self._lock:
            if not own_injection:
                # The user's own modifier release (incl. a key-up the hook is
                # about to swallow and replay).
                self._last_modifier_up_s = now
                return
            pending = self._pending_replay_vk
            if pending is not None and _same_family(vk, pending):
                # Our replayed key-up came back through the hook: it is now on
                # its way to the foreground thread — the effective release.
                self._pending_replay_vk = None
                self._last_modifier_up_s = now

    def note_replay_sent(self, vk: int, now: float) -> None:
        """The hook is re-emitting a swallowed key-up *vk* behind the mask key."""
        with self._lock:
            self._last_replay_sent_s = now
            self._pending_replay_vk = vk

    def note_replay_failed(self) -> None:
        """The replay was not (fully) injected; the original key-up passes through."""
        with self._lock:
            self._pending_replay_vk = None

    def view(self) -> TimelineView:
        with self._lock:
            return TimelineView(
                last_modifier_up_s=self._last_modifier_up_s,
                last_replay_sent_s=self._last_replay_sent_s,
                replay_pending=self._pending_replay_vk is not None,
            )


def ms_since(then_s: float | None, now: float) -> int | None:
    """Whole milliseconds from *then_s* to *now*, or None if never."""
    if then_s is None:
        return None
    return max(0, round((now - then_s) * 1000))


def replayed_recently(
    view: TimelineView, now: float, *, window_s: float = RECENT_REPLAY_WINDOW_S
) -> bool:
    """Whether the hook swallowed and replayed a key-up within *window_s*."""
    sent = view.last_replay_sent_s
    return sent is not None and 0 <= now - sent <= window_s


def settle_delay_s(
    view: TimelineView,
    now: float,
    *,
    settle_s: float = POST_RELEASE_SETTLE_S,
    replay_cap_s: float = REPLAY_OBSERVE_CAP_S,
    poll_s: float = SETTLE_POLL_S,
) -> tuple[float, str | None]:
    """How long to wait before injecting, and why (``"replay"``/``"settle"``).

    ``(0.0, None)`` means inject now. A pending replay yields a short poll
    interval (re-check, it is usually observed within ms) until *replay_cap_s*
    after it was sent; after that it is ignored.
    """
    sent = view.last_replay_sent_s
    if view.replay_pending and sent is not None:
        remaining = sent + replay_cap_s - now
        if remaining > 0:
            return min(poll_s, remaining), "replay"
    up = view.last_modifier_up_s
    if up is not None:
        remaining = up + settle_s - now
        if remaining > 0:
            return remaining, "settle"
    return 0.0, None


@dataclass(frozen=True)
class SettleResult:
    waited_s: float
    reasons: frozenset[str]
    replay_unobserved: bool

    @property
    def needed(self) -> bool:
        return bool(self.reasons)


def wait_for_input_settle(
    read_view: Callable[[], TimelineView],
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    settle_s: float = POST_RELEASE_SETTLE_S,
    replay_cap_s: float = REPLAY_OBSERVE_CAP_S,
    poll_s: float = SETTLE_POLL_S,
) -> SettleResult:
    """Sleep until :func:`settle_delay_s` says go. Bounded in time AND polls.

    Returns immediately (no sleep) in the common case.
    """
    start = clock()
    cap_s = replay_cap_s + settle_s
    max_polls = math.ceil(replay_cap_s / poll_s) + 4 if poll_s > 0 else 4
    reasons: set[str] = set()
    polls = 0
    while polls < max_polls:
        now = clock()
        delay, reason = settle_delay_s(
            read_view(), now, settle_s=settle_s, replay_cap_s=replay_cap_s, poll_s=poll_s
        )
        if reason is None:
            break
        remaining_cap = cap_s - (now - start)
        if remaining_cap <= 0:
            break
        reasons.add(reason)
        sleep(min(delay, remaining_cap))
        polls += 1
    view = read_view()
    return SettleResult(
        waited_s=clock() - start,
        reasons=frozenset(reasons),
        replay_unobserved=view.replay_pending and "replay" in reasons,
    )
