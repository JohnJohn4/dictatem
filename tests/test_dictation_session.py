"""Tests for the pure Dictation Session (#234).

The session holds the per-dictation state that used to be scattered across
``DaemonCore`` plus a monotonically increasing epoch, so later tickets can tag
async results with the epoch they were started under.
"""

from __future__ import annotations

from dictatem.session import DictationSession


def _dirty(session: DictationSession) -> None:
    session.transcription_outstanding = True
    session.transform_outstanding = True
    session.pending_replace_chars = 7
    session.record_start_target_id = 42
    session.text_to_paste = "pending words"


def _assert_clear(session: DictationSession) -> None:
    assert session.transcription_outstanding is False
    assert session.transform_outstanding is False
    assert session.pending_replace_chars == 0
    assert session.record_start_target_id is None
    assert session.text_to_paste is None


class TestFreshSession:
    def test_starts_at_epoch_zero_with_nothing_pending(self) -> None:
        session = DictationSession()
        assert session.epoch == 0
        _assert_clear(session)


class TestBegin:
    def test_begin_bumps_the_epoch(self) -> None:
        session = DictationSession()
        session.begin()
        assert session.epoch == 1
        session.begin()
        assert session.epoch == 2

    def test_begin_clears_leftover_fields(self) -> None:
        session = DictationSession()
        session.begin()
        _dirty(session)
        session.begin()
        _assert_clear(session)


class TestEnd:
    def test_end_bumps_the_epoch_and_clears_fields(self) -> None:
        session = DictationSession()
        session.begin()
        _dirty(session)
        session.end()
        assert session.epoch == 2
        _assert_clear(session)

    def test_end_while_idle_still_bumps(self) -> None:
        # Recovery can run with no dictation in flight; the epoch still moves
        # so any result captured before it is stale.
        session = DictationSession()
        session.end()
        assert session.epoch == 1


class TestEpochIsMonotonic:
    def test_mixed_begin_and_end_never_repeat_an_epoch(self) -> None:
        session = DictationSession()
        seen = [session.epoch]
        for op in ("begin", "end", "end", "begin", "begin", "end"):
            getattr(session, op)()
            seen.append(session.epoch)
        assert seen == [0, 1, 2, 3, 4, 5, 6]
