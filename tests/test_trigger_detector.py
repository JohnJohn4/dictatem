"""Tests for TriggerDetector match logic."""

from __future__ import annotations

from dictatem.transform.detector import (
    PASTE_ACTION,
    TriggerDetector,
    match_builtin_action,
    shadowed_builtin_aliases,
)

SUMMARIZE = "summarize prompt body"
EXPAND = "expand prompt body"

ALIASES = {
    "summarize": SUMMARIZE,
    "summarise": SUMMARIZE,
    "expand": EXPAND,
}


class TestEmptyMap:
    def test_empty_map_matches_nothing(self) -> None:
        det = TriggerDetector({})
        assert det.match("summarize") is None


class TestSingleTokenHits:
    def test_exact_match(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("summarize") == SUMMARIZE

    def test_case_insensitive(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("SUMMARIZE") == SUMMARIZE
        assert det.match("Summarize") == SUMMARIZE

    def test_trailing_punctuation_stripped(self) -> None:
        """Whisper loves to add a period."""
        det = TriggerDetector(ALIASES)
        assert det.match("Summarize.") == SUMMARIZE
        assert det.match("summarize!") == SUMMARIZE
        assert det.match("summarize?") == SUMMARIZE

    def test_leading_and_trailing_whitespace_stripped(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("  summarize  ") == SUMMARIZE
        assert det.match("\tsummarize\n") == SUMMARIZE

    def test_alias_variants_hit_same_transform(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("summarise") == SUMMARIZE
        assert det.match("summarize") == SUMMARIZE
        assert det.match("Summarise.") == SUMMARIZE


class TestSingleTokenMisses:
    def test_unknown_word(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("hello") is None

    def test_empty_string(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("") is None

    def test_only_whitespace(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("   ") is None

    def test_only_punctuation(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match(".....") is None


class TestMultiTokenRejection:
    def test_two_words_no_match(self) -> None:
        """Multi-token utterances are dictation, not triggers."""
        det = TriggerDetector(ALIASES)
        assert det.match("summarize this") is None

    def test_three_words_no_match(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("please summarize that") is None

    def test_punctuation_between_words_still_multi_token(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("summarize, please") is None

    def test_internal_newline_treated_as_multi_token(self) -> None:
        det = TriggerDetector(ALIASES)
        assert det.match("summarize\nthis") is None


class TestRegistrationNormalisation:
    """The detector re-normalises aliases at construction.

    Callers can pass surface forms (e.g. ``"Summarize."``) and they will
    be normalised the same way match input is.
    """

    def test_alias_with_punctuation_registered_after_normalise(self) -> None:
        det = TriggerDetector({"Summarize.": SUMMARIZE})
        assert det.match("summarize") == SUMMARIZE

    def test_alias_with_mixed_case_registered_lowercase(self) -> None:
        det = TriggerDetector({"SUMMARIZE": SUMMARIZE})
        assert det.match("summarize") == SUMMARIZE

    def test_empty_alias_string_ignored(self) -> None:
        det = TriggerDetector({"": SUMMARIZE, "summarize": SUMMARIZE})
        # Empty key dropped; real alias still works.
        assert det.match("summarize") == SUMMARIZE
        assert det.match("") is None


class TestMatchBuiltinAction:
    """The built-in `paste` action uses the same match rule as Trigger Words,
    but is matched independently of the Transform alias map (#139)."""

    def test_paste_action_constant(self) -> None:
        assert PASTE_ACTION == "paste"

    def test_exact_paste_matches(self) -> None:
        assert match_builtin_action("paste") == PASTE_ACTION

    def test_case_and_punctuation_forms_fire(self) -> None:
        # Whisper's period, a question mark, all-caps — all normalise to "paste".
        for utterance in ("Paste.", "paste?", "PASTE", "  paste  ", "\tPaste!\n"):
            assert match_builtin_action(utterance) == PASTE_ACTION, utterance

    def test_multi_word_paste_this_is_not_the_action(self) -> None:
        # A lone "paste" is never something a user dictates; "paste this" is.
        assert match_builtin_action("paste this") is None
        assert match_builtin_action("please paste") is None
        assert match_builtin_action("paste, please") is None

    def test_unknown_and_empty_miss(self) -> None:
        assert match_builtin_action("summarize") is None
        assert match_builtin_action("") is None
        assert match_builtin_action("   ") is None
        assert match_builtin_action("....") is None


class TestShadowedBuiltinAliases:
    def test_no_collision_returns_empty(self) -> None:
        assert shadowed_builtin_aliases(["summarize", "expand"]) == []

    def test_exact_paste_alias_is_shadowed(self) -> None:
        assert shadowed_builtin_aliases(["paste", "summarize"]) == ["paste"]

    def test_surface_form_alias_is_shadowed(self) -> None:
        # The collision is detected after normalisation, so punctuation/case
        # variants of a built-in name are caught too.
        assert shadowed_builtin_aliases(["Paste.", "expand"]) == ["Paste."]

    def test_result_is_deduped_and_sorted(self) -> None:
        out = shadowed_builtin_aliases(["paste", "paste", "PASTE"])
        assert out == sorted(set(out))
