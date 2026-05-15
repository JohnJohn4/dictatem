"""Tests for LastPaste rails check."""

from __future__ import annotations

from dictatem.transform.last_paste import LastPaste


def _make(*, hwnd: int = 42, pasted_at_ms: int = 1_000) -> LastPaste:
    return LastPaste(
        text="hello world ",
        char_count=12,
        hwnd=hwnd,
        pasted_at_ms=pasted_at_ms,
    )


class TestRailsOk:
    def test_passes_when_hwnd_matches_and_within_ttl(self) -> None:
        lp = _make(hwnd=42, pasted_at_ms=1_000)
        assert lp.rails_ok(current_hwnd=42, now_ms=2_000, ttl_s=300.0) is True

    def test_fails_when_hwnd_differs(self) -> None:
        lp = _make(hwnd=42, pasted_at_ms=1_000)
        assert lp.rails_ok(current_hwnd=99, now_ms=2_000, ttl_s=300.0) is False

    def test_fails_when_age_exceeds_ttl(self) -> None:
        lp = _make(hwnd=42, pasted_at_ms=1_000)
        # 301 s = 301_000 ms after; TTL is 300 s
        assert lp.rails_ok(current_hwnd=42, now_ms=302_000, ttl_s=300.0) is False

    def test_fails_at_exactly_ttl_boundary(self) -> None:
        """Age == TTL is considered expired (strict <)."""
        lp = _make(hwnd=42, pasted_at_ms=0)
        assert lp.rails_ok(current_hwnd=42, now_ms=300_000, ttl_s=300.0) is False

    def test_passes_just_before_ttl(self) -> None:
        lp = _make(hwnd=42, pasted_at_ms=0)
        assert lp.rails_ok(current_hwnd=42, now_ms=299_999, ttl_s=300.0) is True

    def test_hwnd_mismatch_dominates_ttl(self) -> None:
        """Even within TTL, a wrong HWND fails."""
        lp = _make(hwnd=42, pasted_at_ms=1_000)
        assert lp.rails_ok(current_hwnd=99, now_ms=1_100, ttl_s=300.0) is False


class TestImmutability:
    def test_frozen(self) -> None:
        lp = _make()
        try:
            lp.text = "other"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("LastPaste should be frozen")
