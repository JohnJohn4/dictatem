"""Clipboard Capture Plan — the pure decision of which offered formats to save.

The plan is platform-neutral: the Win32 adapter (and the macOS adapter, #244)
describe each format on offer as an ``OfferedFormat`` (opaque id, display name,
kind, size) and capture exactly what ``plan_capture`` returns. See
``CONTEXT.md#clipboard-snapshot``.
"""

from __future__ import annotations

from dictatem.paste.clipboard_snapshot import (
    SNAPSHOT_SIZE_CAP_BYTES,
    ClipboardSnapshot,
    FormatKind,
    OfferedFormat,
    plan_capture,
)


def _mem(fid: object, name: str, size: int, *, is_text: bool = False) -> OfferedFormat:
    return OfferedFormat(
        format_id=fid, name=name, kind=FormatKind.MEMORY, size=size, is_text=is_text
    )


class TestCapturePlan:
    def test_memory_backed_formats_kept_in_offered_order(self) -> None:
        offered = [
            _mem(49300, "PNG", 2_000),
            _mem(8, "CF_DIB", 8_000),
            _mem(13, "CF_UNICODETEXT", 40, is_text=True),
        ]
        plan = plan_capture(offered)
        assert [f.format_id for f in plan.capture] == [49300, 8, 13]
        assert plan.over_cap is False
        assert plan.warning is None

    def test_skipped_kinds_are_excluded(self) -> None:
        offered = [
            OfferedFormat(2, "CF_BITMAP", FormatKind.HANDLE, None),
            _mem(8, "CF_DIB", 8_000),
            OfferedFormat(17, "CF_DIBV5", FormatKind.SYNTHESIZED, None),
            OfferedFormat(0x80, "CF_OWNERDISPLAY", FormatKind.DELAYED, None),
            _mem(13, "CF_UNICODETEXT", 40, is_text=True),
        ]
        plan = plan_capture(offered)
        assert [f.format_id for f in plan.capture] == [8, 13]
        # Skipping uncapturable kinds is routine, not a degradation: no warning.
        assert plan.warning is None

    def test_over_cap_falls_back_to_text_only(self) -> None:
        offered = [
            _mem(8, "CF_DIB", 900),
            _mem(13, "CF_UNICODETEXT", 200, is_text=True),
            _mem(49400, "HTML Format", 300),
        ]
        plan = plan_capture(offered, cap_bytes=1_000)
        assert [f.format_id for f in plan.capture] == [13]
        assert plan.over_cap is True

    def test_exactly_at_cap_is_not_over(self) -> None:
        offered = [_mem(8, "CF_DIB", 600), _mem(13, "CF_UNICODETEXT", 400, is_text=True)]
        plan = plan_capture(offered, cap_bytes=1_000)
        assert [f.format_id for f in plan.capture] == [8, 13]
        assert plan.over_cap is False

    def test_over_cap_warning_names_formats_and_sizes(self) -> None:
        offered = [
            _mem(8, "CF_DIB", 900),
            _mem(13, "CF_UNICODETEXT", 200, is_text=True),
        ]
        plan = plan_capture(offered, cap_bytes=1_000)
        assert plan.warning is not None
        assert "CF_DIB=900" in plan.warning
        assert "CF_UNICODETEXT=200" in plan.warning
        assert "1100" in plan.warning  # the total
        assert "1000" in plan.warning  # the cap

    def test_unmeasured_memory_format_counts_as_over_cap(self) -> None:
        # An adapter that ran out of its time budget before sizing a format
        # reports size=None; the plan must not capture blind, so it falls back.
        offered = [
            _mem(13, "CF_UNICODETEXT", 20, is_text=True),
            OfferedFormat(49500, "Biff12", FormatKind.MEMORY, None),
        ]
        plan = plan_capture(offered)
        assert [f.format_id for f in plan.capture] == [13]
        assert plan.over_cap is True
        assert plan.warning is not None
        assert "Biff12=unmeasured" in plan.warning

    def test_over_cap_without_text_captures_nothing(self) -> None:
        plan = plan_capture([_mem(8, "CF_DIB", 5_000)], cap_bytes=1_000)
        assert plan.capture == ()
        assert plan.over_cap is True

    def test_empty_clipboard_gives_empty_plan(self) -> None:
        plan = plan_capture([])
        assert plan.capture == ()
        assert plan.over_cap is False
        assert plan.warning is None

    def test_default_cap_fits_a_4k_screenshot(self) -> None:
        # A 3840x2160 32-bpp DIB plus a PNG of it must survive a dictation.
        dib = 3840 * 2160 * 4 + 124
        assert dib + dib // 2 <= SNAPSHOT_SIZE_CAP_BYTES


class TestClipboardSnapshot:
    def test_empty_snapshot_is_empty(self) -> None:
        assert ClipboardSnapshot.empty().is_empty

    def test_snapshot_with_entries_is_not_empty(self) -> None:
        snap = ClipboardSnapshot(entries=((13, b"h\x00i\x00\x00\x00"),))
        assert not snap.is_empty

    def test_snapshot_repr_never_shows_content(self) -> None:
        # Logs may repr a snapshot; it must show formats and sizes, never bytes.
        snap = ClipboardSnapshot(entries=((13, "secret".encode("utf-16-le")),))
        assert "secret" not in repr(snap)
        assert "s\\x00e" not in repr(snap)
