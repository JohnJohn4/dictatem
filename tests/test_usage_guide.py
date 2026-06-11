"""Tests for the pure Usage Guide HTML builder (#113).

The Usage Guide (CONTEXT.md / ADR-0019) is the in-app help window opened from
the tray's "How to use Dictatem…" item. Its content is generated as a single
HTML string here so it can be unit-tested without Qt; the menu wiring and the
window itself are manual-QA. The guide reflects the live Hotkey Combo, so the
chord must follow ``[hotkey].modifiers`` and the running platform.
"""

from __future__ import annotations

from dictatem.tray.usage_guide import usage_guide_html


class TestDictatingSection:
    def test_shows_the_live_windows_chord(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "Win+Alt" in html

    def test_shows_the_live_macos_chord(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="darwin")
        assert "⌥⌘" in html

    def test_reflects_a_rebound_chord(self) -> None:
        html = usage_guide_html(("ctrl", "shift"), platform="win32")
        assert "Ctrl+Shift" in html

    def test_teaches_both_modes_and_the_release_nuance(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "Hold to talk" in html
        assert "Tap to toggle" in html
        # The release nuance the old one-line header couldn't fit (#112/#113).
        assert "release" in html
        assert "let go" in html

    def test_mentions_the_overlay_pill(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "pill" in html


class TestFirstUseSection:
    def test_explains_model_load_and_preload(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "First use" in html
        assert "Preload Model" in html


class TestDocumentShape:
    def test_is_wrapped_html(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert html.startswith("<html>")
        assert html.endswith("</html>")

    def test_dictating_precedes_first_use(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert html.index("Dictating") < html.index("First use")
