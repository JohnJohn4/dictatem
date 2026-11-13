"""Proving tests for the v0.7.0 bug hunt, paste stack.

See docs/reviews/2026-11-02-v0.7.0-bug-hunt.md. Each test asserts the intended
behaviour and fails on v0.7.0, so it is marked ``xfail(strict=True)`` with the
finding it proves; a fix flips it to XPASS and the strict marker forces removal.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from dictatem.paste.clipboard_snapshot import ClipboardSnapshot  # noqa: TC001
from dictatem.paste.pipeline import paste
from tests.fakes import FakeClipboardIO, FakeForegroundTracker, FakeKeystrokeSender

if TYPE_CHECKING:
    from collections.abc import Callable


def _no_sleep(_s: float) -> None:
    pass


class _Scheduler:
    def __init__(self) -> None:
        self.pending: list[Callable[[], None]] = []

    def __call__(self, _delay: float, cb: Callable[[], None]) -> None:
        self.pending.append(cb)

    def fire_all(self) -> None:
        while self.pending:
            self.pending.pop(0)()


def _paste(text: str, clip: FakeClipboardIO, sched: _Scheduler) -> None:
    paste(
        text,
        clipboard=clip,
        keystroke=FakeKeystrokeSender(),
        foreground=FakeForegroundTracker(),
        schedule_restore=sched,
        sleep=_no_sleep,
    )


@pytest.mark.xfail(strict=True, reason="bug-hunt H-1: a second dictation inside the 1.5 s restore window snapshots the first dictation, so the user's clipboard is lost")  # noqa: E501
def test_back_to_back_dictations_restore_user_clipboard() -> None:
    # Dictation B lands inside A's 1.5 s deferred-restore window: B's save()
    # snapshots A's transient text, so the LAST restore puts dictation A back
    # and the user's original clipboard is lost.
    clip = FakeClipboardIO()
    clip.text = "USER ORIGINAL"
    sched = _Scheduler()
    _paste("dictation a", clip, sched)
    _paste("dictation b", clip, sched)
    sched.fire_all()
    assert clip.text == "USER ORIGINAL"


@pytest.mark.xfail(strict=True, reason="bug-hunt M-3: the deferred restore overwrites a copy the user made within 1.5 s")  # noqa: E501
def test_deferred_restore_does_not_clobber_a_copy_made_meanwhile() -> None:
    # The user copies something within 1.5 s of a dictation (or uses the tray
    # "Copy last dictation"); the unconditional deferred restore overwrites it.
    clip = FakeClipboardIO()
    clip.text = "USER ORIGINAL"
    sched = _Scheduler()
    _paste("dictation", clip, sched)
    clip.copy("copied by user after the paste")
    sched.fire_all()
    assert clip.text == "copied by user after the paste"


class _SetTextFails(FakeClipboardIO):
    def set_text(self, text: str) -> None:
        self.calls.append(("set_text", text))
        self.text = None  # EmptyClipboard ran, SetClipboardData then failed
        msg = "win32 clipboard contention: SetClipboardData failed"
        raise OSError(msg)


@pytest.mark.xfail(strict=True, reason="bug-hunt L-3: a set_text failure leaves the clipboard open and emptied")  # noqa: E501
def test_set_text_failure_still_closes_clipboard_and_restores_user_data() -> None:
    clip = _SetTextFails()
    clip.text = "USER ORIGINAL"
    with pytest.raises(OSError):
        paste(
            "hello",
            clipboard=clip,
            keystroke=FakeKeystrokeSender(),
            foreground=FakeForegroundTracker(),
            sleep=_no_sleep,
        )
    # The clipboard was opened but never closed: on Windows the daemon's thread
    # keeps the system clipboard locked; and the emptied clipboard is not restored.
    assert ("close",) in clip.calls
    assert clip.text == "USER ORIGINAL"


class _SaveContendedOnce(FakeClipboardIO):
    def __init__(self) -> None:
        super().__init__()
        self._fail = True

    def save(self) -> ClipboardSnapshot:
        if self._fail:
            self._fail = False
            msg = "win32 clipboard contention: Access is denied"
            raise OSError(msg)
        return super().save()


@pytest.mark.xfail(strict=True, reason="bug-hunt M-4: save() opens the clipboard with no contention retry")  # noqa: E501
def test_transient_contention_on_save_is_retried_like_open() -> None:
    # save() does its own OpenClipboard but, unlike open(), gets no retry: one
    # 10 ms Win+V-monitor race fails the whole paste (held for recovery).
    clip = _SaveContendedOnce()
    clip.text = "USER ORIGINAL"
    ks = FakeKeystrokeSender()
    paste(
        "hello",
        clipboard=clip,
        keystroke=ks,
        foreground=FakeForegroundTracker(),
        sleep=_no_sleep,
    )
    assert ks.paste_count == 1


@pytest.mark.skipif(sys.platform != "win32", reason="win32 keystroke adapter")
@pytest.mark.xfail(strict=True, reason="bug-hunt L-4: Trigger Fire types the replacement after a short Backspace phase")  # noqa: E501
def test_trigger_fire_does_not_type_after_backspace_phase_fell_short() -> None:
    import dictatem.paste.win32_keystroke as wk

    sent_batches: list[int] = []
    calls = {"n": 0}

    def fake_send(inputs: object) -> int:
        calls["n"] += 1
        n = len(inputs)  # type: ignore[arg-type]
        sent_batches.append(n)
        # Second Backspace chunk is refused (desktop switch / UIPI mid-phase).
        return 0 if calls["n"] == 2 else n

    ks = wk.Win32KeystrokeSender(sleep=_no_sleep)
    with patch("dictatem.paste.win32_keystroke._send_input", side_effect=fake_send):
        ks.send_backspaces(40)  # only 8 of 40 Backspaces land
        n_before = len(sent_batches)
        ks.send_text("replacement text ")
    # The old Last Paste is only partly erased, yet the replacement is typed on
    # top of the remainder (and the daemon then arms Last Paste on it).
    assert len(sent_batches) == n_before
