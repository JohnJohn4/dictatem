"""Tests for TriggerDetector match logic."""

from __future__ import annotations

from dictatem.transform.detector import TriggerDetector


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
