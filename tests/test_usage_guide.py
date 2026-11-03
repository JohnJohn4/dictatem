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

    def test_says_the_hotkey_is_ignored_while_working_and_esc_cancels(self) -> None:
        # #240: a press mid-transcription shows a busy caption, not a new take.
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "ignored while Dictatem is working" in html
        assert "<b>Esc</b> cancels" in html

    def test_mentions_the_overlay_pill(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "pill" in html


class TestTriggerWordsSection:
    def test_lists_configured_trigger_words(self) -> None:
        html = usage_guide_html(
            ("win", "alt"), platform="win32", trigger_words=["fix", "rewrite"]
        )
        assert "Trigger words" in html
        assert "fix" in html
        assert "rewrite" in html

    def test_explains_the_same_window_rail(self) -> None:
        html = usage_guide_html(
            ("win", "alt"), platform="win32", trigger_words=["fix"]
        )
        assert "same window" in html

    def test_empty_state_when_no_trigger_words(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32", trigger_words=[])
        assert "haven't added any trigger words" in html
        assert "~/.dictatem/prompts/" in html

    def test_trigger_words_are_html_escaped(self) -> None:
        html = usage_guide_html(
            ("win", "alt"), platform="win32", trigger_words=["a&b"]
        )
        assert "a&amp;b" in html
        assert "a&b" not in html

    def test_explains_cleanup_over_last_dictation(self) -> None:
        # #127: the guide teaches the built-in cleanup trigger over your last
        # dictation — naming `polish` and what it does to the just-pasted text.
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "Clean up your last dictation" in html
        assert "polish" in html
        assert "filler" in html

    def test_lists_configured_paste_aliases(self) -> None:
        # #250: the live [trigger_words].paste_aliases are shown with the
        # trigger words, labelled as words that also mean `paste`.
        html = usage_guide_html(
            ("win", "alt"), platform="win32", trigger_words=["fix"],
            paste_aliases=["haste", "a<b"],
        )
        assert "also mean <i>paste</i>" in html
        assert "haste" in html
        assert "a&lt;b" in html

    def test_paste_aliases_shown_even_with_no_trigger_words(self) -> None:
        html = usage_guide_html(
            ("win", "alt"), platform="win32", trigger_words=[], paste_aliases=["haste"]
        )
        assert "haste" in html
        assert "also mean <i>paste</i>" in html

    def test_no_paste_alias_row_when_none_configured(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32", trigger_words=["fix"])
        assert "also mean <i>paste</i>" not in html


class TestChoosingTriggerWordsSection:
    """#251: how to pick reliable Trigger Words, and what the startup warning means."""

    def _html(self) -> str:
        return usage_guide_html(("win", "alt"), platform="win32")

    def test_has_its_own_heading(self) -> None:
        assert "Choosing trigger words" in self._html()

    def test_recommends_multi_syllable_distinct_words(self) -> None:
        html = self._html()
        assert "more than one syllable" in html
        assert "sound different" in html

    def test_explains_why_bare_paste_needs_help(self) -> None:
        html = self._html()
        assert "haste" in html
        assert "paste_aliases" in html

    def test_explains_the_startup_warning_and_how_to_rename(self) -> None:
        html = self._html()
        assert "daemon.log" in html
        assert "sound alike" in html
        assert "aliases:" in html  # rename by editing the prompt file's aliases list


class TestRecoverySection:
    def test_explains_paste_recovery(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "Recovering a lost dictation" in html
        # The built-in recovery word and the tray fallback are both named.
        assert "paste" in html
        assert "Copy last dictation" in html

    def test_recovery_after_triggers_before_first_use(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert html.index("Trigger words") < html.index("Recovering a lost dictation")
        assert html.index("Recovering a lost dictation") < html.index("First use")


class TestFirstUseSection:
    def test_explains_model_load_and_preload(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "First use" in html
        assert "preload_model" in html
        assert "Unload model" in html

    def test_explains_one_time_download_then_offline(self) -> None:
        # ADR-0025 / #164: the model downloads once on first run, then offline.
        html = usage_guide_html(("win", "alt"), platform="win32").lower()
        assert "download" in html
        assert "offline" in html

    def test_mentions_loading_and_downloading_pill_captions(self) -> None:
        # The two distinct loading-pill captions the user may see (#162/#164).
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "Loading Dict. Model" in html
        assert "Downloading model" in html


class TestChangingHotkeySection:
    """The config-discoverability "Changing your hotkey" section (#123)."""

    def _section(self, html: str) -> str:
        # Scope assertions to this section's text (the live combo also appears in
        # the dictating section, so an unscoped check would be ambiguous).
        return html[html.index("Changing your hotkey"):]

    def test_shows_the_live_windows_chord(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "Changing your hotkey" in html
        assert "Win+Alt" in self._section(html)

    def test_reflects_a_rebound_chord(self) -> None:
        html = usage_guide_html(("ctrl", "shift"), platform="win32")
        assert "Ctrl+Shift" in self._section(html)

    def test_names_the_config_file_and_key(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "config.toml" in html
        assert "[hotkey].modifiers" in html

    def test_mentions_restart_applies_changes(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert "restart" in self._section(html).lower()

    def test_lists_mouse_buttons(self) -> None:
        html = self._section(usage_guide_html(("win", "alt"), platform="win32"))
        for name in ("mouse4", "mouse5", "middle"):
            assert name in html

    def test_lists_the_whole_curated_vocabulary(self) -> None:
        # Drift guard: every accepted [hotkey].modifiers name (config's curated
        # allow-list) must appear in the section, so the two can't fall out of
        # sync as new trigger inputs are added.
        from dictatem.config import VALID_MODIFIER_NAMES

        section = self._section(usage_guide_html(("win", "alt"), platform="win32"))
        for name in VALID_MODIFIER_NAMES:
            assert name in section, f"{name} missing from the hotkey section"

    def test_notes_click_only_mice_cannot_hold_to_talk(self) -> None:
        # ADR-0020 consequence: don't imply every mouse can push-to-talk.
        section = self._section(usage_guide_html(("win", "alt"), platform="win32"))
        assert "hold-to-talk" in section


class TestDocumentShape:
    def test_is_wrapped_html(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert html.startswith("<html>")
        assert html.endswith("</html>")

    def test_sections_are_ordered_dictating_triggers_first_use(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        # The hotkey keycaps + modes open the page (no "Dictating" heading now).
        assert html.index("Hold to talk") < html.index("The pill")
        assert html.index("The pill") < html.index("Trigger words")
        assert html.index("Trigger words") < html.index("First use")

    def test_changing_hotkey_section_comes_last(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert html.index("First use") < html.index("Changing your hotkey")


class TestVisualDesign:
    def test_hotkey_opens_the_page_as_keycaps(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32")
        assert html.index(">Win</td>") < html.index(">Alt</td>") < html.index("Hold to talk")

    def test_pill_legend_names_every_phase(self) -> None:
        from dictatem.tray.usage_guide import PILL_HUES

        html = usage_guide_html(("win", "alt"), platform="win32")
        for hue in PILL_HUES.values():
            assert hue in html

    def test_pill_legend_has_held_row_with_palette_hue_and_caption(self) -> None:
        # The "Saved — say paste" row (#239) uses the overlay palette's Held hue.
        from dictatem.overlay.state import PILL_HEX, PillColor

        html = usage_guide_html(("win", "alt"), platform="win32")
        held_hue = PILL_HEX[PillColor.HELD]
        assert held_hue in html
        row_start = html.index(held_hue)
        row = html[row_start : html.index("</tr>", row_start)]
        assert "Saved — say paste" in row

    def test_pill_legend_has_say_again_row_with_palette_hue(self) -> None:
        # The Borderline "say again" flash (#248) gets its own row and hue.
        from dictatem.overlay.state import PILL_HEX, PillColor

        html = usage_guide_html(("win", "alt"), platform="win32")
        row_start = html.index(PILL_HEX[PillColor.SAY_AGAIN])
        row = html[row_start : html.index("</tr>", row_start)]
        assert "Say again" in row
        assert "nothing was pasted" in row

    def test_explains_say_again_and_the_longer_phrase_workaround(self) -> None:
        html = usage_guide_html(("win", "alt"), platform="win32", trigger_words=("summarize",))
        assert "say again" in html.lower()
        assert "longer phrase" in html

    def test_pill_legend_error_row_means_a_real_failure(self) -> None:
        from dictatem.overlay.state import PILL_HEX, PillColor

        html = usage_guide_html(("win", "alt"), platform="win32")
        row_start = html.index(PILL_HEX[PillColor.ERROR])
        row = html[row_start : html.index("</tr>", row_start)]
        # No longer the catch-all "Didn't land" (held dictations have their own
        # row now); it names a genuine failure where nothing was saved.
        assert "Didn't land" not in row
        assert "Didn't catch that — nothing to paste" in row

    def test_dark_theme_switches_the_page_colour(self) -> None:
        from dictatem.tray.usage_guide import DARK, LIGHT

        assert LIGHT.page in usage_guide_html(("win", "alt"), platform="win32")
        dark = usage_guide_html(("win", "alt"), platform="win32", dark=True)
        assert DARK.page in dark
        assert LIGHT.page not in dark
