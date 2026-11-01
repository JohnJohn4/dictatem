"""Input timeline + pre-injection settle decision (#269) — pure, fake clock."""

from __future__ import annotations

import pytest

from dictatem.paste.input_timeline import (
    POST_RELEASE_SETTLE_S,
    REPLAY_OBSERVE_CAP_S,
    SETTLE_POLL_S,
    InputTimeline,
    TimelineView,
    ms_since,
    replayed_recently,
    settle_delay_s,
    wait_for_input_settle,
)

VK_LMENU = 0xA4
VK_LWIN = 0x5B
VK_LCONTROL = 0xA2
VK_MASK = 0xE8
VK_A = 0x41


class _FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def _view(
    up: float | None = None, sent: float | None = None, pending: bool = False
) -> TimelineView:
    return TimelineView(last_modifier_up_s=up, last_replay_sent_s=sent, replay_pending=pending)


class TestInputTimeline:
    def test_starts_empty(self) -> None:
        assert InputTimeline().view() == _view()

    def test_user_modifier_key_up_is_recorded(self) -> None:
        t = InputTimeline()
        t.note_key(VK_LWIN, False, False, 5.0)
        assert t.view().last_modifier_up_s == 5.0

    @pytest.mark.parametrize(("vk", "is_down"), [(VK_A, False), (VK_LWIN, True)])
    def test_non_modifier_or_key_down_is_ignored(self, vk: int, is_down: bool) -> None:
        t = InputTimeline()
        t.note_key(vk, is_down, False, 5.0)
        assert t.view() == _view()

    def test_replay_pending_until_its_key_up_comes_back_through_the_hook(self) -> None:
        t = InputTimeline()
        t.note_key(VK_LMENU, False, False, 1.0)  # the physical key-up being swallowed
        t.note_replay_sent(VK_LMENU, 1.001)
        assert t.view() == _view(up=1.0, sent=1.001, pending=True)
        t.note_key(VK_MASK, True, True, 1.002)  # the mask key: not the replay
        t.note_key(VK_MASK, False, True, 1.002)
        assert t.view().replay_pending
        t.note_key(VK_LMENU, False, True, 1.003)  # the replayed key-up
        assert t.view() == _view(up=1.003, sent=1.001, pending=False)

    def test_own_ctrl_v_does_not_count_as_the_replay_or_a_release(self) -> None:
        t = InputTimeline()
        t.note_replay_sent(VK_LWIN, 1.0)
        t.note_key(VK_LCONTROL, False, True, 1.1)
        assert t.view() == _view(sent=1.0, pending=True)

    def test_replay_matches_by_family(self) -> None:
        t = InputTimeline()
        t.note_replay_sent(VK_LMENU, 1.0)
        t.note_key(0x12, False, True, 1.1)  # reported as generic VK_MENU
        assert not t.view().replay_pending

    def test_failed_replay_clears_pending(self) -> None:
        t = InputTimeline()
        t.note_replay_sent(VK_LWIN, 1.0)
        t.note_replay_failed()
        assert not t.view().replay_pending
        assert t.view().last_replay_sent_s == 1.0


class TestHelpers:
    def test_ms_since(self) -> None:
        assert ms_since(None, 5.0) is None
        assert ms_since(4.5, 5.0) == 500
        assert ms_since(6.0, 5.0) == 0

    def test_replayed_recently(self) -> None:
        assert not replayed_recently(_view(), 10.0)
        assert replayed_recently(_view(sent=9.2), 10.0)
        assert not replayed_recently(_view(sent=8.9), 10.0)


class TestSettleDelay:
    def test_nothing_recent_injects_now(self) -> None:
        assert settle_delay_s(_view(), 10.0) == (0.0, None)
        assert settle_delay_s(_view(up=9.0, sent=9.0), 10.0) == (0.0, None)

    def test_recent_release_waits_out_the_remainder(self) -> None:
        delay, reason = settle_delay_s(_view(up=9.98), 10.0)
        assert reason == "settle"
        assert delay == pytest.approx(POST_RELEASE_SETTLE_S - 0.02)

    def test_pending_replay_polls(self) -> None:
        delay, reason = settle_delay_s(_view(up=9.99, sent=9.99, pending=True), 10.0)
        assert reason == "replay"
        assert delay == pytest.approx(SETTLE_POLL_S)

    def test_pending_replay_is_ignored_after_the_cap(self) -> None:
        sent = 10.0 - REPLAY_OBSERVE_CAP_S - 0.001
        assert settle_delay_s(_view(up=sent, sent=sent, pending=True), 10.0) == (0.0, None)


class TestWaitForInputSettle:
    def test_common_case_never_sleeps(self) -> None:
        clock = _FakeClock()
        r = wait_for_input_settle(lambda: _view(up=1.0), clock=clock, sleep=clock.sleep)
        assert not r.needed and clock.sleeps == [] and r.waited_s == 0

    def test_waits_for_replay_then_settles(self) -> None:
        clock = _FakeClock(100.0)
        t = InputTimeline()
        t.note_replay_sent(VK_LWIN, 100.0)

        def read() -> TimelineView:
            # The hook observes the replayed key-up after ~2 polls.
            if clock.now >= 100.0 + 2 * SETTLE_POLL_S - 1e-9 and t.view().replay_pending:
                t.note_key(VK_LWIN, False, True, clock.now)
            return t.view()

        r = wait_for_input_settle(read, clock=clock, sleep=clock.sleep)
        assert r.reasons == {"replay", "settle"}
        assert not r.replay_unobserved
        observed_at = 100.0 + 2 * SETTLE_POLL_S
        assert clock.now == pytest.approx(observed_at + POST_RELEASE_SETTLE_S)

    def test_unobserved_replay_is_bounded(self) -> None:
        clock = _FakeClock(100.0)
        view = _view(sent=100.0, pending=True)
        r = wait_for_input_settle(lambda: view, clock=clock, sleep=clock.sleep)
        assert r.replay_unobserved
        assert r.waited_s <= REPLAY_OBSERVE_CAP_S + POST_RELEASE_SETTLE_S + 1e-9

    def test_stalled_clock_cannot_hang(self) -> None:
        r = wait_for_input_settle(
            lambda: _view(up=100.0, sent=100.0, pending=True),
            clock=lambda: 100.0,
            sleep=lambda s: None,
        )
        assert r.needed  # gave up after the poll bound instead of looping forever
