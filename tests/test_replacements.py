"""Tests for the pure Replacement parser + apply (ADR-0024, #125).

A Replacement is a deterministic, post-transcription substitution applied to
regular dictation before paste: ``source => target`` per line, ``#`` comments,
blank lines ignored, malformed lines skipped with a warning. Matching is
case-insensitive on WHOLE words; an EMPTY target deletes the match and
collapses the surrounding whitespace. No LLM — see ``CONTEXT.md#replacement``.
"""

from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING

from dictatem.transcribe.replacements import (
    Replacement,
    apply_replacements,
    bootstrap_replacements,
    parse_replacements,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestParseReplacements:
    def test_single_rule(self) -> None:
        rules = parse_replacements("teh => the")
        assert rules == [Replacement(source="teh", target="the")]

    def test_multiple_rules(self) -> None:
        content = dedent("""\
            teh => the
            recieve => receive
        """)
        rules = parse_replacements(content)
        assert rules == [
            Replacement(source="teh", target="the"),
            Replacement(source="recieve", target="receive"),
        ]

    def test_comments_are_ignored(self) -> None:
        content = dedent("""\
            # this is a comment
            teh => the
            # um =>
        """)
        rules = parse_replacements(content)
        assert rules == [Replacement(source="teh", target="the")]

    def test_blank_lines_ignored(self) -> None:
        content = "\n\nteh => the\n\n\n"
        rules = parse_replacements(content)
        assert rules == [Replacement(source="teh", target="the")]

    def test_empty_target_is_a_delete_rule(self) -> None:
        rules = parse_replacements("um =>")
        assert rules == [Replacement(source="um", target="")]

    def test_empty_target_with_trailing_whitespace_is_delete(self) -> None:
        rules = parse_replacements("um =>   ")
        assert rules == [Replacement(source="um", target="")]

    def test_surrounding_whitespace_trimmed_from_source_and_target(self) -> None:
        rules = parse_replacements("   teh    =>    the   ")
        assert rules == [Replacement(source="teh", target="the")]

    def test_target_may_contain_spaces(self) -> None:
        rules = parse_replacements("btw => by the way")
        assert rules == [Replacement(source="btw", target="by the way")]

    def test_multi_word_source_is_supported(self) -> None:
        rules = parse_replacements("new york => NYC")
        assert rules == [Replacement(source="new york", target="NYC")]

    def test_malformed_line_without_arrow_is_skipped_with_warning(
        self, caplog: logging.LogCaptureFixture
    ) -> None:
        content = dedent("""\
            teh => the
            this line has no arrow
        """)
        with caplog.at_level(
            logging.WARNING, logger="dictatem.transcribe.replacements"
        ):
            rules = parse_replacements(content)
        assert rules == [Replacement(source="teh", target="the")]
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_empty_source_is_skipped_with_warning(
        self, caplog: logging.LogCaptureFixture
    ) -> None:
        with caplog.at_level(
            logging.WARNING, logger="dictatem.transcribe.replacements"
        ):
            rules = parse_replacements("   => something")
        assert rules == []
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_empty_content_returns_no_rules(self) -> None:
        assert parse_replacements("") == []

    def test_only_comments_returns_no_rules(self) -> None:
        assert parse_replacements("# um =>\n# uh =>\n") == []


class TestApplyReplacements:
    def test_no_rules_returns_text_unchanged(self) -> None:
        assert apply_replacements("hello world", []) == "hello world"

    def test_simple_whole_word_substitution(self) -> None:
        rules = [Replacement(source="teh", target="the")]
        assert apply_replacements("teh cat", rules) == "the cat"

    def test_match_is_case_insensitive(self) -> None:
        rules = [Replacement(source="teh", target="the")]
        assert apply_replacements("TEH cat", rules) == "the cat"
        assert apply_replacements("Teh cat", rules) == "the cat"

    def test_does_not_match_partial_word(self) -> None:
        # "cat" must not match inside "category".
        rules = [Replacement(source="cat", target="dog")]
        assert apply_replacements("category", rules) == "category"

    def test_matches_at_string_boundaries(self) -> None:
        rules = [Replacement(source="cat", target="dog")]
        assert apply_replacements("cat", rules) == "dog"

    def test_multiple_occurrences_all_replaced(self) -> None:
        rules = [Replacement(source="teh", target="the")]
        assert apply_replacements("teh cat and teh dog", rules) == "the cat and the dog"

    def test_multiple_rules_applied(self) -> None:
        rules = [
            Replacement(source="teh", target="the"),
            Replacement(source="recieve", target="receive"),
        ]
        assert apply_replacements("teh recieve", rules) == "the receive"

    def test_empty_target_deletes_word_and_collapses_whitespace(self) -> None:
        rules = [Replacement(source="um", target="")]
        assert apply_replacements("so um yeah", rules) == "so yeah"

    def test_empty_target_delete_at_start_strips_leading_space(self) -> None:
        rules = [Replacement(source="um", target="")]
        assert apply_replacements("um hello there", rules) == "hello there"

    def test_empty_target_delete_at_end_strips_trailing_space(self) -> None:
        rules = [Replacement(source="um", target="")]
        assert apply_replacements("hello there um", rules) == "hello there"

    def test_empty_target_deletes_multiple_fillers(self) -> None:
        rules = [Replacement(source="um", target="")]
        assert apply_replacements("um so um yeah um", rules) == "so yeah"

    def test_delete_is_also_case_insensitive(self) -> None:
        rules = [Replacement(source="um", target="")]
        assert apply_replacements("so Um yeah", rules) == "so yeah"

    def test_delete_does_not_touch_substring(self) -> None:
        # "um" should not be deleted from inside "umbrella".
        rules = [Replacement(source="um", target="")]
        assert apply_replacements("umbrella", rules) == "umbrella"

    def test_target_with_spaces_substituted(self) -> None:
        rules = [Replacement(source="btw", target="by the way")]
        assert apply_replacements("btw hello", rules) == "by the way hello"

    def test_source_regex_metacharacters_are_literal(self) -> None:
        # A source like "c++" must be matched literally, not as a regex.
        rules = [Replacement(source="c++", target="cpp")]
        assert apply_replacements("I love c++", rules) == "I love cpp"

    def test_punctuation_adjacent_word_is_replaced(self) -> None:
        rules = [Replacement(source="teh", target="the")]
        assert apply_replacements("teh, cat", rules) == "the, cat"

    def test_underscore_counts_as_word_character(self) -> None:
        # Standard whole-word semantics: an underscore is part of the word, so
        # "um" must NOT match inside an identifier-like "um_var".
        rules = [Replacement(source="um", target="X")]
        assert apply_replacements("um_var", rules) == "um_var"
        assert apply_replacements("say_um_now", rules) == "say_um_now"

    def test_non_word_edged_source_with_underscore_neighbour(self) -> None:
        # "c++" is bounded correctly even though it ends in non-word chars, and
        # an adjacent underscore still blocks the match (it would extend it).
        rules = [Replacement(source="c++", target="cpp")]
        assert apply_replacements("c++ rocks", rules) == "cpp rocks"
        assert apply_replacements("c++config", rules) == "c++config"
        assert apply_replacements("c++_lib", rules) == "c++_lib"


class TestBootstrapReplacements:
    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        target = tmp_path / "replacements.md"
        assert not target.exists()
        bootstrap_replacements(target)
        assert target.exists()

    def test_bootstrapped_file_has_only_commented_examples(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "replacements.md"
        bootstrap_replacements(target)
        content = target.read_text(encoding="utf-8")
        # No active rules: every non-blank line is a comment, so parsing
        # yields zero rules — nothing is altered by default (ADR-0024).
        assert parse_replacements(content) == []
        # And there is at least one commented filler example to uncomment.
        assert "# um =>" in content

    def test_does_not_overwrite_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "replacements.md"
        target.write_text("teh => the\n", encoding="utf-8")
        bootstrap_replacements(target)
        assert target.read_text(encoding="utf-8") == "teh => the\n"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "replacements.md"
        bootstrap_replacements(target)
        assert target.exists()
