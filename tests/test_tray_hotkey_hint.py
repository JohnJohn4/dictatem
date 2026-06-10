"""Tests for the pure tray hotkey-hint formatter (#104).

New users see Start/Stop in the tray but aren't told the global hotkey, which
differs by platform (Windows **Win+Alt**, macOS **⌥⌘** — the same
``[hotkey].modifiers`` config mapped per platform). The formatter derives the
hint from the live config and the running platform; it is pure (no Qt, no OS) so
the full modifier matrix is unit-tested here. The menu wiring is manual-QA.
"""

from __future__ import annotations

from dictatem.tray.hotkey_hint import format_hotkey, hotkey_hint_label


class TestFormatHotkeyWindows:
    def test_default_is_win_plus_alt(self) -> None:
        assert format_hotkey(("win", "alt"), platform="win32") == "Win+Alt"

    def test_preserves_config_order(self) -> None:
        assert format_hotkey(("alt", "win"), platform="win32") == "Alt+Win"

    def test_ctrl_shift(self) -> None:
        assert format_hotkey(("ctrl", "shift"), platform="win32") == "Ctrl+Shift"

    def test_single_modifier(self) -> None:
        assert format_hotkey(("ctrl",), platform="win32") == "Ctrl"

    def test_meta_is_alias_for_win(self) -> None:
        # ADR-0018: `meta` is the canonical OS-key name with `win` as an alias.
        assert format_hotkey(("meta", "alt"), platform="win32") == "Win+Alt"


class TestFormatHotkeyMacOS:
    def test_default_is_option_command(self) -> None:
        assert format_hotkey(("win", "alt"), platform="darwin") == "⌥⌘"

    def test_canonical_symbol_order_regardless_of_config_order(self) -> None:
        # macOS orders modifiers ⌃⌥⇧⌘ by convention, not by config order.
        assert format_hotkey(("alt", "win"), platform="darwin") == "⌥⌘"
        assert (
            format_hotkey(("win", "shift", "alt", "ctrl"), platform="darwin")
            == "⌃⌥⇧⌘"
        )

    def test_single_modifier(self) -> None:
        assert format_hotkey(("ctrl",), platform="darwin") == "⌃"

    def test_meta_maps_to_command(self) -> None:
        assert format_hotkey(("meta",), platform="darwin") == "⌘"


class TestFormatHotkeyEdgeCases:
    def test_empty_modifiers_is_empty_string(self) -> None:
        assert format_hotkey((), platform="win32") == ""
        assert format_hotkey((), platform="darwin") == ""

    def test_unknown_names_are_dropped(self) -> None:
        # Config validation already rejects unknown names, but never render junk.
        assert format_hotkey(("turbo",), platform="win32") == ""

    def test_unknown_platform_uses_word_names(self) -> None:
        # A platform without a glyph table falls back to readable word names.
        assert format_hotkey(("win", "alt"), platform="linux") == "Win+Alt"


class TestHotkeyHintLabel:
    def test_windows_label_conveys_hold_and_tap(self) -> None:
        label = hotkey_hint_label(("win", "alt"), platform="win32")
        assert label == "Hotkey: Win+Alt (hold to talk · tap to toggle)"

    def test_macos_label_uses_symbols(self) -> None:
        label = hotkey_hint_label(("win", "alt"), platform="darwin")
        assert label.startswith("Hotkey: ⌥⌘")
        assert "hold to talk" in label
        assert "tap to toggle" in label

    def test_custom_modifiers_change_the_hint(self) -> None:
        label = hotkey_hint_label(("ctrl", "shift"), platform="win32")
        assert "Ctrl+Shift" in label

    def test_empty_modifiers_yield_empty_label(self) -> None:
        # No usable chord → no hint (the tray hides the header item).
        assert hotkey_hint_label((), platform="win32") == ""
