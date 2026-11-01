"""Held-modifier wait before injecting a paste (#269) — pure, fake clock."""

from __future__ import annotations

import logging

import pytest

from dictatem.exceptions import ModifiersHeldError
from dictatem.paste.modifier_wait import (
    MODIFIER_POLL_S,
    MODIFIER_WAIT_CAP_S,
    WIN32_MODIFIER_VKS,
    held_modifier_names,
    wait_for_modifiers_released,
)
from dictatem.paste.pipeline import paste
from tests.fakes import FakeClipboardIO, FakeForegroundTracker, FakeKeystrokeSender

_ALT = frozenset({"alt"})
_WIN_ALT = frozenset({"win", "alt"})
_NONE: frozenset[str] = frozenset()


class _FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def _reader(script: list[frozenset[str]]):  # type: ignore[no-untyped-def]
    polls = list(script)

    def read() -> frozenset[str]:
        return polls.pop(0) if len(polls) > 1 else polls[0]

    return read


class TestWaitForModifiersReleased:
    def test_nothing_held_returns_immediately_without_sleeping(self) -> None:
        clock = _FakeClock()
        r = wait_for_modifiers_released(_reader([_NONE]), clock=clock, sleep=clock.sleep)
        assert r.released and not r.needed
        assert clock.sleeps == []
        assert r.waited_s == 0

    def test_waits_until_released(self) -> None:
        clock = _FakeClock()
        r = wait_for_modifiers_released(
            _reader([_WIN_ALT, _ALT, _ALT, _NONE]), clock=clock, sleep=clock.sleep
        )
        assert r.released and r.needed
        assert r.initially_held == _WIN_ALT
        assert r.still_held == _NONE
        assert len(clock.sleeps) == 3
        assert r.waited_s == pytest.approx(3 * MODIFIER_POLL_S)

    def test_gives_up_at_the_cap(self) -> None:
        clock = _FakeClock()
        r = wait_for_modifiers_released(_reader([_ALT]), clock=clock, sleep=clock.sleep)
        assert not r.released
        assert r.still_held == _ALT
        assert r.waited_s == pytest.approx(MODIFIER_WAIT_CAP_S)
        # Bounded: never sleeps past the cap.
        assert sum(clock.sleeps) == pytest.approx(MODIFIER_WAIT_CAP_S)

    def test_transient_injected_ctrl_does_not_deadlock(self) -> None:
        # The #171-style injected Ctrl tap is atomic; a poll that lands inside
        # it sees Ctrl once, then released.
        clock = _FakeClock()
        r = wait_for_modifiers_released(
            _reader([frozenset({"ctrl"}), _NONE]), clock=clock, sleep=clock.sleep
        )
        assert r.released
        assert clock.sleeps == [MODIFIER_POLL_S]

    def test_stalled_clock_still_terminates(self) -> None:
        # A clock that never advances must not hang the GUI thread.
        sleeps: list[float] = []
        r = wait_for_modifiers_released(
            _reader([_ALT]), clock=lambda: 5.0, sleep=sleeps.append
        )
        assert not r.released
        assert len(sleeps) <= int(MODIFIER_WAIT_CAP_S / MODIFIER_POLL_S) + 2

    def test_custom_cap_and_poll(self) -> None:
        clock = _FakeClock()
        r = wait_for_modifiers_released(
            _reader([_ALT]), clock=clock, sleep=clock.sleep, cap_s=0.05, poll_s=0.02
        )
        assert not r.released
        assert clock.sleeps == pytest.approx([0.02, 0.02, 0.01])


class TestHeldModifierNames:
    def test_maps_each_vk(self) -> None:
        down = {0x12, 0x5C}  # VK_MENU, VK_RWIN
        assert held_modifier_names(lambda vk: vk in down) == frozenset({"alt", "win"})

    def test_none_down(self) -> None:
        assert held_modifier_names(lambda vk: False) == _NONE

    def test_covers_alt_both_wins_shift_ctrl(self) -> None:
        vks = {vk for _name, vk in WIN32_MODIFIER_VKS}
        assert vks == {0x12, 0x5B, 0x5C, 0x10, 0x11}


class TestPastePipelineWaits:
    def _paste(self, ks: FakeKeystrokeSender, replace: int = 0) -> tuple[
        FakeClipboardIO, FakeForegroundTracker, _FakeClock
    ]:
        clip = FakeClipboardIO()
        fg = FakeForegroundTracker(target_id=7)
        clock = _FakeClock()
        paste(
            "hello",
            clipboard=clip,
            keystroke=ks,
            foreground=fg,
            replace_chars=replace,
            target_id=7,
            schedule_restore=lambda _d, _cb: None,
            sleep=clock.sleep,
            clock=clock,
        )
        return clip, fg, clock

    def test_ctrl_v_sent_only_after_release(self) -> None:
        ks = FakeKeystrokeSender()
        ks.held_script = [_WIN_ALT, _ALT, _NONE]
        _clip, _fg, clock = self._paste(ks)
        assert ks.paste_count == 1
        assert ks.held_polls == 3
        assert len(clock.sleeps) == 2

    def test_typed_trigger_fire_waits_too(self) -> None:
        ks = FakeKeystrokeSender()
        ks.held_script = [_ALT, _NONE]
        self._paste(ks, replace=3)
        assert ks.backspace_counts == [3]
        assert ks.typed_texts == ["hello "]
        assert ks.held_polls == 2

    @pytest.mark.parametrize("replace", [0, 4])
    def test_cap_expiry_raises_with_nothing_injected(self, replace: int) -> None:
        ks = FakeKeystrokeSender()
        ks.held_script = [_ALT]
        clip = FakeClipboardIO()
        clip.text = "user clipboard"
        fg = FakeForegroundTracker(target_id=7)
        clock = _FakeClock()
        with pytest.raises(ModifiersHeldError) as info:
            paste(
                "hello",
                clipboard=clip,
                keystroke=ks,
                foreground=fg,
                replace_chars=replace,
                target_id=7,
                sleep=clock.sleep,
                clock=clock,
            )
        assert info.value.held == _ALT
        assert ks.events == []  # no Ctrl+V, no backspaces, no typed text
        assert fg.restored == []  # focus not touched
        assert clip.calls == []  # clipboard not touched
        assert clip.text == "user clipboard"

    def test_logs_wait_without_text(self, caplog: pytest.LogCaptureFixture) -> None:
        ks = FakeKeystrokeSender()
        ks.held_script = [_WIN_ALT, _NONE]
        with caplog.at_level(logging.INFO, logger="dictatem.paste.pipeline"):
            self._paste(ks)
        msgs = [r.getMessage() for r in caplog.records]
        waited = [m for m in msgs if "waited" in m]
        assert waited and "alt, win" in waited[0]
        assert not any("hello" in m for m in msgs)

    def test_no_wait_logged_when_nothing_held(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        ks = FakeKeystrokeSender()
        with caplog.at_level(logging.INFO, logger="dictatem.paste.pipeline"):
            self._paste(ks)
        assert not any("modifier" in r.getMessage() for r in caplog.records)
