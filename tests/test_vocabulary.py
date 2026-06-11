"""Tests for the pure Vocabulary parser + recognition-hint selection (#126).

Vocabulary terms (names, jargon, acronyms) bias transcription recognition.
The parser reads ``vocabulary.md`` (one term/line, ``#`` comments). The pure
``select_recognition_hint`` chooses faster-whisper's ``hotwords`` kwarg when the
installed backend supports it, else falls back to ``initial_prompt`` — the
capability is detected by inspecting the transcribe signature, so the selection
itself stays a pure, testable decision. See ``CONTEXT.md#vocabulary`` and
ADR-0024.
"""

from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

from dictatem.transcribe.vocabulary import (
    backend_supports_hotwords,
    bootstrap_vocabulary,
    parse_vocabulary,
    select_recognition_hint,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestParseVocabulary:
    def test_single_term(self) -> None:
        assert parse_vocabulary("Dictatem") == ["Dictatem"]

    def test_multiple_terms_one_per_line(self) -> None:
        content = dedent("""\
            Dictatem
            faster-whisper
            CTranslate2
        """)
        assert parse_vocabulary(content) == [
            "Dictatem",
            "faster-whisper",
            "CTranslate2",
        ]

    def test_comments_are_ignored(self) -> None:
        content = dedent("""\
            # add your terms below
            Dictatem
            # this is also a comment
        """)
        assert parse_vocabulary(content) == ["Dictatem"]

    def test_blank_lines_ignored(self) -> None:
        content = "\n\nDictatem\n\n\nCTranslate2\n"
        assert parse_vocabulary(content) == ["Dictatem", "CTranslate2"]

    def test_surrounding_whitespace_trimmed(self) -> None:
        assert parse_vocabulary("   Dictatem   ") == ["Dictatem"]

    def test_multi_word_term_preserved(self) -> None:
        assert parse_vocabulary("New York City") == ["New York City"]

    def test_term_preserves_internal_casing(self) -> None:
        # Vocabulary biases toward user spellings — casing must survive.
        assert parse_vocabulary("kubectl") == ["kubectl"]
        assert parse_vocabulary("OAuth") == ["OAuth"]

    def test_inline_hash_is_not_a_comment(self) -> None:
        # Only a line that STARTS with '#' (after stripping) is a comment.
        assert parse_vocabulary("C# language") == ["C# language"]

    def test_empty_content_returns_no_terms(self) -> None:
        assert parse_vocabulary("") == []

    def test_only_comments_returns_no_terms(self) -> None:
        assert parse_vocabulary("# just a note\n# another\n") == []


class TestSelectRecognitionHint:
    def test_no_terms_yields_no_kwargs(self) -> None:
        assert select_recognition_hint([], supports_hotwords=True) == {}
        assert select_recognition_hint([], supports_hotwords=False) == {}

    def test_hotwords_used_when_supported(self) -> None:
        hint = select_recognition_hint(
            ["Dictatem", "CTranslate2"], supports_hotwords=True
        )
        assert hint == {"hotwords": "Dictatem CTranslate2"}

    def test_initial_prompt_fallback_when_unsupported(self) -> None:
        hint = select_recognition_hint(
            ["Dictatem", "CTranslate2"], supports_hotwords=False
        )
        assert hint == {"initial_prompt": "Dictatem CTranslate2"}

    def test_single_term_hotwords(self) -> None:
        assert select_recognition_hint(["kubectl"], supports_hotwords=True) == {
            "hotwords": "kubectl"
        }


class _FakeBackendWithHotwords:
    def transcribe(self, audio, *, hotwords=None, initial_prompt=None):  # noqa: ANN001
        ...


class _FakeBackendNoHotwords:
    def transcribe(self, audio, *, initial_prompt=None):  # noqa: ANN001
        ...


class TestBackendSupportsHotwords:
    def test_detects_hotwords_parameter(self) -> None:
        assert backend_supports_hotwords(_FakeBackendWithHotwords().transcribe) is True

    def test_absent_hotwords_parameter(self) -> None:
        assert backend_supports_hotwords(_FakeBackendNoHotwords().transcribe) is False

    def test_uninspectable_callable_falls_back_to_false(self) -> None:
        # Some C-implemented callables have no inspectable signature; we must
        # degrade to the safe initial_prompt path rather than raise.
        assert backend_supports_hotwords(print) is False


class TestBootstrapVocabulary:
    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        target = tmp_path / "vocabulary.md"
        assert not target.exists()
        bootstrap_vocabulary(target)
        assert target.exists()

    def test_bootstrapped_file_has_commented_example_and_no_active_terms(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "vocabulary.md"
        bootstrap_vocabulary(target)
        content = target.read_text(encoding="utf-8")
        # Out of the box no terms are active (every line is a comment).
        assert parse_vocabulary(content) == []
        # There is a commented example and a note about over-long lists.
        assert "#" in content
        assert "degrade" in content.lower()

    def test_does_not_overwrite_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "vocabulary.md"
        target.write_text("Dictatem\n", encoding="utf-8")
        bootstrap_vocabulary(target)
        assert target.read_text(encoding="utf-8") == "Dictatem\n"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "vocabulary.md"
        bootstrap_vocabulary(target)
        assert target.exists()
