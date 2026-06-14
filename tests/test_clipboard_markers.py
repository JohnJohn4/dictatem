"""Tests for the pure clutter-proof clipboard marker logic (#138 / ADR-0023).

The real ``SetClipboardData`` is Windows manual-QA (the Win+V eyeball lives in
``test_win32_clipboard_smoke`` on Windows + the QA handoff); the *decision* —
which formats are written and with what payload — is pure and tested here
against fake register/set_data primitives.
"""

from __future__ import annotations

from dictatem.paste.clipboard_markers import (
    CLIPBOARD_EXCLUSION_FORMATS,
    EXCLUSION_MARKER_PAYLOAD,
    apply_exclusion_markers,
)


class _FakeClipboardFormats:
    """Records RegisterClipboardFormat + SetClipboardData calls.

    Hands out a distinct, stable id per format name so a write can be traced
    back to the format it was registered under.
    """

    def __init__(self) -> None:
        self.registered: list[str] = []
        self.writes: list[tuple[int, bytes]] = []
        self.ids: dict[str, int] = {}

    def register(self, name: str) -> int:
        self.registered.append(name)
        return self.ids.setdefault(name, 0xC000 + len(self.ids))

    def set_data(self, fmt: int, data: bytes) -> object:
        self.writes.append((fmt, data))
        return fmt


class TestExclusionPayload:
    def test_payload_is_dword_zero(self) -> None:
        # A DWORD 0 == four little-endian zero bytes; the value Windows reads to
        # opt the write OUT of history and cloud sync.
        assert EXCLUSION_MARKER_PAYLOAD == b"\x00\x00\x00\x00"
        assert int.from_bytes(EXCLUSION_MARKER_PAYLOAD, "little") == 0

    def test_both_exclusion_formats_named(self) -> None:
        assert "CanIncludeInClipboardHistory" in CLIPBOARD_EXCLUSION_FORMATS
        assert "CanUploadToCloudClipboard" in CLIPBOARD_EXCLUSION_FORMATS


class TestApplyExclusionMarkers:
    def test_registers_both_exclusion_formats(self) -> None:
        fake = _FakeClipboardFormats()
        apply_exclusion_markers(fake.register, fake.set_data)
        assert fake.registered == list(CLIPBOARD_EXCLUSION_FORMATS)

    def test_writes_dword_zero_under_each_registered_format(self) -> None:
        fake = _FakeClipboardFormats()
        apply_exclusion_markers(fake.register, fake.set_data)
        # One write per format, each carrying the DWORD-0 payload, under the id
        # the matching register() returned.
        assert len(fake.writes) == len(CLIPBOARD_EXCLUSION_FORMATS)
        for (fmt, data), name in zip(
            fake.writes, CLIPBOARD_EXCLUSION_FORMATS, strict=True
        ):
            assert data == EXCLUSION_MARKER_PAYLOAD
            assert fmt == fake.ids[name]

    def test_each_format_gets_a_distinct_id(self) -> None:
        fake = _FakeClipboardFormats()
        apply_exclusion_markers(fake.register, fake.set_data)
        written_ids = {fmt for fmt, _ in fake.writes}
        assert len(written_ids) == len(CLIPBOARD_EXCLUSION_FORMATS)
