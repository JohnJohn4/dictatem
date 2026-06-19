"""Tests for the pure tray state logic (no Qt dependencies)."""

from __future__ import annotations

import enum
import importlib
import sys

from dictatem.tray.state import IconVariant, MenuItem, TrayState, glyph_tint_rgba


class TestIconVariant:
    def test_idle_when_nothing_active(self) -> None:
        state = TrayState(is_recording=False, is_model_loaded=False, has_error=False)
        assert state.current_icon_variant() == IconVariant.Idle

    def test_recording_when_recording(self) -> None:
        state = TrayState(is_recording=True, is_model_loaded=False, has_error=False)
        assert state.current_icon_variant() == IconVariant.Recording

    def test_error_when_has_error(self) -> None:
        state = TrayState(is_recording=False, is_model_loaded=False, has_error=True)
        assert state.current_icon_variant() == IconVariant.Error

    def test_error_takes_priority_over_recording(self) -> None:
        state = TrayState(is_recording=True, is_model_loaded=True, has_error=True)
        assert state.current_icon_variant() == IconVariant.Error

    def test_recording_when_model_loaded_and_recording(self) -> None:
        state = TrayState(is_recording=True, is_model_loaded=True, has_error=False)
        assert state.current_icon_variant() == IconVariant.Recording

    def test_idle_when_only_model_loaded(self) -> None:
        state = TrayState(is_recording=False, is_model_loaded=True, has_error=False)
        assert state.current_icon_variant() == IconVariant.Idle


class TestGlyphTint:
    def test_dark_background_yields_light_glyph(self) -> None:
        r, g, b, _a = glyph_tint_rgba(is_dark_background=True)
        assert (r, g, b) == (255, 255, 255)

    def test_light_background_yields_dark_glyph(self) -> None:
        r, g, b, _a = glyph_tint_rgba(is_dark_background=False)
        assert (r, g, b) == (0, 0, 0)

    def test_tint_is_fully_opaque(self) -> None:
        assert glyph_tint_rgba(is_dark_background=True)[3] == 255
        assert glyph_tint_rgba(is_dark_background=False)[3] == 255


class TestMenuItemEnabled:
    def test_stop_enabled_only_when_recording(self) -> None:
        recording = TrayState(is_recording=True, is_model_loaded=False, has_error=False)
        not_recording = TrayState(is_recording=False, is_model_loaded=False, has_error=False)
        assert recording.menu_item_enabled(MenuItem.STOP) is True
        assert not_recording.menu_item_enabled(MenuItem.STOP) is False

    def test_unload_enabled_only_when_model_loaded(self) -> None:
        loaded = TrayState(is_recording=False, is_model_loaded=True, has_error=False)
        not_loaded = TrayState(is_recording=False, is_model_loaded=False, has_error=False)
        assert loaded.menu_item_enabled(MenuItem.UNLOAD) is True
        assert not_loaded.menu_item_enabled(MenuItem.UNLOAD) is False

    def test_preload_enabled_only_when_model_not_loaded(self) -> None:
        loaded = TrayState(is_recording=False, is_model_loaded=True, has_error=False)
        not_loaded = TrayState(is_recording=False, is_model_loaded=False, has_error=False)
        assert loaded.menu_item_enabled(MenuItem.PRELOAD) is False
        assert not_loaded.menu_item_enabled(MenuItem.PRELOAD) is True

    def test_preload_disabled_while_loading(self) -> None:
        loading = TrayState(
            is_recording=False, is_model_loaded=False, has_error=False,
            is_model_loading=True,
        )
        assert loading.menu_item_enabled(MenuItem.PRELOAD) is False

    def test_unload_disabled_while_loading(self) -> None:
        loading = TrayState(
            is_recording=False, is_model_loaded=True, has_error=False,
            is_model_loading=True,
        )
        assert loading.menu_item_enabled(MenuItem.UNLOAD) is False

    def test_always_enabled_items(self) -> None:
        state = TrayState(is_recording=False, is_model_loaded=False, has_error=False)
        for item in (MenuItem.START, MenuItem.AUTOSTART, MenuItem.SHOW_LOG,
                     MenuItem.OPEN_CONFIG, MenuItem.HELP, MenuItem.RESTART,
                     MenuItem.UPGRADE, MenuItem.QUIT):
            assert state.menu_item_enabled(item) is True, f"{item} should always be enabled"

    def test_always_enabled_items_during_recording(self) -> None:
        state = TrayState(is_recording=True, is_model_loaded=True, has_error=True)
        for item in (MenuItem.START, MenuItem.AUTOSTART, MenuItem.SHOW_LOG,
                     MenuItem.OPEN_CONFIG, MenuItem.HELP, MenuItem.RESTART,
                     MenuItem.UPGRADE, MenuItem.QUIT):
            assert state.menu_item_enabled(item) is True, f"{item} should be enabled even in error"


    def test_copy_last_dictation_enabled_only_when_dictation_exists(self) -> None:
        # Disabled before any dictation; enabled once one has been retained
        # (ADR-0023 / #119) — independent of recording / model state.
        none_yet = TrayState(
            is_recording=False, is_model_loaded=False, has_error=False,
            has_last_dictation=False,
        )
        have_one = TrayState(
            is_recording=False, is_model_loaded=False, has_error=False,
            has_last_dictation=True,
        )
        assert none_yet.menu_item_enabled(MenuItem.COPY_LAST_DICTATION) is False
        assert have_one.menu_item_enabled(MenuItem.COPY_LAST_DICTATION) is True

    def test_copy_last_dictation_defaults_disabled(self) -> None:
        # has_last_dictation defaults False, so a freshly-built state (no kwarg)
        # leaves the item disabled.
        state = TrayState(is_recording=False, is_model_loaded=False, has_error=False)
        assert state.menu_item_enabled(MenuItem.COPY_LAST_DICTATION) is False

    def test_copy_last_dictation_enabled_even_while_recording(self) -> None:
        # The buffer persists across states, so recovery stays available.
        state = TrayState(
            is_recording=True, is_model_loaded=True, has_error=False,
            has_last_dictation=True,
        )
        assert state.menu_item_enabled(MenuItem.COPY_LAST_DICTATION) is True

    def test_hotkey_hint_and_version_are_always_disabled(self) -> None:
        # The hotkey header and version footer are non-interactive labels.
        for state in (
            TrayState(is_recording=False, is_model_loaded=False, has_error=False),
            TrayState(is_recording=True, is_model_loaded=True, has_error=True),
        ):
            assert state.menu_item_enabled(MenuItem.HOTKEY_HINT) is False
            assert state.menu_item_enabled(MenuItem.VERSION) is False


class TestMenuItemOrder:
    def test_enum_order_matches_documented_spec(self) -> None:
        expected = ["HOTKEY_HINT", "START", "STOP", "COPY_LAST_DICTATION",
                    "PRELOAD", "UNLOAD", "AUTOSTART", "SHOW_LOG", "OPEN_CONFIG",
                    "HELP", "RESTART", "UPGRADE", "QUIT", "VERSION"]
        actual = [m.name for m in MenuItem]
        assert actual == expected

    def test_menu_item_is_enum(self) -> None:
        assert issubclass(MenuItem, enum.Enum)

    def test_icon_variant_is_enum(self) -> None:
        assert issubclass(IconVariant, enum.Enum)


class TestTrayStateImmutability:
    def test_is_dataclass(self) -> None:
        import dataclasses
        assert dataclasses.is_dataclass(TrayState)

    def test_fields(self) -> None:
        state = TrayState(is_recording=True, is_model_loaded=False, has_error=True)
        assert state.is_recording is True
        assert state.is_model_loaded is False
        assert state.has_error is True


class TestImportSafety:
    def test_tray_state_has_no_pyside6_imports(self) -> None:
        before = set(sys.modules.keys())
        importlib.import_module("dictatem.tray.state")
        after = set(sys.modules.keys())
        new_modules = after - before
        pyside_violations = [
            m for m in new_modules if m == "PySide6" or m.startswith("PySide6.")
        ]
        assert pyside_violations == [], (
            f"tray.state pulled in PySide6: {pyside_violations}"
        )
