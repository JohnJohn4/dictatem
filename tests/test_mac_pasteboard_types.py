"""macOS pasteboard-type classification — pure, runs on every platform (#244).

The macOS clipboard adapter describes each pasteboard item's types to the
shared Clipboard Capture Plan and writes the captured ones back item by item.
These tests pin the type -> kind mapping and the restore grouping without
importing AppKit.
"""

from __future__ import annotations

from dictatem.paste.clipboard_snapshot import FormatKind
from dictatem.paste.mac_pasteboard_types import (
    classify_pasteboard_item,
    is_text_type,
    items_for_restore,
)


def _kinds(types: list[str]) -> list[FormatKind]:
    return [kind for _, kind in classify_pasteboard_item(types)]


class TestClassifyPasteboardItem:
    def test_screenshot_png_and_tiff_are_captured(self) -> None:
        assert _kinds(["public.png", "public.tiff"]) == [FormatKind.MEMORY, FormatKind.MEMORY]

    def test_legacy_aliases_beside_utis_are_synthesized(self) -> None:
        # The shape of a Finder file copy: real UTIs plus the legacy/dynamic
        # aliases the pasteboard bridges from them.
        types = [
            "public.file-url",
            "CorePasteboardFlavorType 0x6675726C",
            "dyn.ah62d4rv4gu8y6y4grf0gn5xbrzw1gydcr7u1e3cytf2gn",
            "NSFilenamesPboardType",
            "Apple URL pasteboard type",
            "public.utf8-plain-text",
            "NSStringPboardType",
        ]
        assert _kinds(types) == [
            FormatKind.MEMORY,
            FormatKind.SYNTHESIZED,
            FormatKind.SYNTHESIZED,
            FormatKind.SYNTHESIZED,
            FormatKind.SYNTHESIZED,
            FormatKind.MEMORY,
            FormatKind.SYNTHESIZED,
        ]

    def test_legacy_only_item_keeps_its_types(self) -> None:
        # An old app that offers no UTI at all: the aliases are all there is.
        assert _kinds(["NeXT RTFD pasteboard type", "dyn.abc123"]) == [
            FormatKind.MEMORY,
            FormatKind.MEMORY,
        ]

    def test_file_promises_are_delayed(self) -> None:
        types = [
            "com.apple.pasteboard.promised-file-url",
            "com.apple.pasteboard.promised-file-content-type",
            "com.apple.NSFilePromiseItemMetaData",
            "public.utf8-plain-text",
        ]
        assert _kinds(types) == [
            FormatKind.DELAYED,
            FormatKind.DELAYED,
            FormatKind.DELAYED,
            FormatKind.MEMORY,
        ]

    def test_rich_text_and_app_private_utis_are_captured(self) -> None:
        types = ["public.rtf", "public.html", "com.apple.webarchive", "com.example.private"]
        assert _kinds(types) == [FormatKind.MEMORY] * 4

    def test_preserves_offered_order(self) -> None:
        types = ["public.html", "public.utf8-plain-text", "public.rtf"]
        assert [t for t, _ in classify_pasteboard_item(types)] == types


class TestIsTextType:
    def test_plain_text_utis_are_text(self) -> None:
        for uti in (
            "public.utf8-plain-text",
            "public.utf16-plain-text",
            "public.utf16-external-plain-text",
            "public.plain-text",
        ):
            assert is_text_type(uti), uti

    def test_rich_and_binary_types_are_not_text(self) -> None:
        for uti in ("public.rtf", "public.html", "public.png", "NSStringPboardType"):
            assert not is_text_type(uti), uti


class TestItemsForRestore:
    def test_groups_entries_by_item_in_snapshot_order(self) -> None:
        entries = (
            ((0, "public.png"), b"png"),
            ((0, "public.tiff"), b"tiff"),
            ((1, "public.file-url"), b"file:///a"),
            ((2, "public.file-url"), b"file:///b"),
        )
        assert items_for_restore(entries) == [
            [("public.png", b"png"), ("public.tiff", b"tiff")],
            [("public.file-url", b"file:///a")],
            [("public.file-url", b"file:///b")],
        ]

    def test_items_dropped_by_the_plan_leave_no_empty_item(self) -> None:
        # Over the cap only item 2's text was kept: one item, not three.
        entries = (((2, "public.utf8-plain-text"), b"hi"),)
        assert items_for_restore(entries) == [[("public.utf8-plain-text", b"hi")]]

    def test_empty_snapshot_restores_no_items(self) -> None:
        assert items_for_restore(()) == []
