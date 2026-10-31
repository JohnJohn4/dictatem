"""Surface a hotkey hook that couldn't be installed (#245 / review F-15).

On Windows a low-level hook (``SetWindowsHookExW``) can be refused — the
hotkey is then dead. The hook adapters log the OS error and report a
:class:`HookFailure` on their own hook thread; the daemon turns the first one
into a single tray notification plus a tray hint ("dictate from the tray
menu"), mirroring the macOS event-tap failure path (#95).

Pure and platform-neutral: the copy comes from :func:`hook_failure_notice`,
and :class:`HookFailureReporter` is a thread-safe queue whose ``drain`` runs
on the Qt thread with the tray calls injected.
"""

from __future__ import annotations

import enum
import logging
import queue
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Tray hotkey-hint text while the hotkey hook is down: the hint row is where
# the user looks when the hotkey "does nothing", so it says what still works.
HOTKEY_UNREGISTERED_HINT = "Hotkey off — dictate from the tray menu"


class HookKind(enum.Enum):
    """Which native hook failed to install."""

    KEYBOARD = "keyboard"
    MOUSE = "mouse"


@dataclass(frozen=True)
class HookFailure:
    """A hook install refused by the OS, with its ``GetLastError`` code."""

    kind: HookKind
    error_code: int


@dataclass(frozen=True)
class HookFailureNotice:
    """What the tray shows for a hook failure."""

    title: str
    body: str
    hint: str


def hook_failure_notice(failure: HookFailure) -> HookFailureNotice:
    """Map a hook failure to its tray notification and hint."""
    if failure.kind is HookKind.MOUSE:
        body = (
            "The mouse-button hotkey couldn't be registered; dictate from the "
            "tray menu. Restarting Dictatem may fix it."
        )
    else:
        body = (
            "The hotkey couldn't be registered; dictate from the tray menu. "
            "Restarting Dictatem may fix it."
        )
    return HookFailureNotice(
        title="Hotkey unavailable", body=body, hint=HOTKEY_UNREGISTERED_HINT
    )


class HookFailureReporter:
    """Thread-safe hand-off from a hook thread to the Qt thread.

    ``report`` may be called from any thread (it only enqueues). ``drain``
    runs on the Qt thread and shows the first failure exactly once — both
    hooks failing together is still one notification and one hint.
    """

    def __init__(
        self,
        *,
        show_notification: Callable[[str, str], None],
        set_hotkey_hint: Callable[[str], None],
    ) -> None:
        self._show_notification = show_notification
        self._set_hotkey_hint = set_hotkey_hint
        self._queue: queue.SimpleQueue[HookFailure] = queue.SimpleQueue()
        self._surfaced = False

    def report(self, failure: HookFailure) -> None:
        self._queue.put(failure)

    def drain(self) -> None:
        while True:
            try:
                failure = self._queue.get_nowait()
            except queue.Empty:
                return
            logger.info(
                "Hotkey hook unavailable: %s (OS error %d)",
                failure.kind.value,
                failure.error_code,
            )
            if self._surfaced:
                continue
            self._surfaced = True
            notice = hook_failure_notice(failure)
            self._set_hotkey_hint(notice.hint)
            self._show_notification(notice.title, notice.body)
