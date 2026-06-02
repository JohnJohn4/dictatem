"""Tests for the Prompt File parser, folder loader, and bootstrap (#21)."""

from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING

from dictatem.transform.prompts import (
    bootstrap_prompts,
    default_prompts_dir,
    load_prompts_dir,
    parse_prompt_file,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestParsePromptFile:
    def test_valid_file_returns_aliases_and_body(self) -> None:
        content = dedent("""\
            ---
            aliases: [summarize, summarise]
            ---
            Body line one.
            Body line two.
        """)
        result = parse_prompt_file(content)
        assert result is not None
        assert result.aliases == ["summarize", "summarise"]
        assert result.body == "Body line one.\nBody line two."

    def test_single_alias_list(self) -> None:
        content = "---\naliases: [shorten]\n---\nbody"
        result = parse_prompt_file(content)
        assert result is not None
        assert result.aliases == ["shorten"]

    def test_aliases_with_quotes_are_unwrapped(self) -> None:
        content = '---\naliases: ["a", \'b\', c]\n---\nbody'
        result = parse_prompt_file(content)
        assert result is not None
        assert result.aliases == ["a", "b", "c"]

    def test_missing_opening_fence_returns_none(
        self, caplog: logging.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="dictatem.transform.prompts"):
            assert parse_prompt_file("aliases: [x]\nbody") is None
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_missing_closing_fence_returns_none(
        self, caplog: logging.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="dictatem.transform.prompts"):
            result = parse_prompt_file("---\naliases: [x]\nbody")
        assert result is None
        assert any("closing" in r.message for r in caplog.records)

    def test_missing_aliases_key_returns_none(
        self, caplog: logging.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="dictatem.transform.prompts"):
            result = parse_prompt_file("---\nname: foo\n---\nbody")
        assert result is None
        assert any("aliases" in r.message for r in caplog.records)

    def test_non_list_aliases_returns_none(
        self, caplog: logging.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="dictatem.transform.prompts"):
            result = parse_prompt_file("---\naliases: summarize\n---\nbody")
        assert result is None
        assert any("aliases" in r.message for r in caplog.records)

    def test_empty_aliases_list_returns_none(
        self, caplog: logging.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="dictatem.transform.prompts"):
            result = parse_prompt_file("---\naliases: []\n---\nbody")
        assert result is None
        assert any("empty" in r.message for r in caplog.records)

    def test_body_preserves_trailing_newline_stripped(self) -> None:
        content = "---\naliases: [x]\n---\n\nThe body.\n\n"
        result = parse_prompt_file(content)
        assert result is not None
        assert result.body == "The body."

    def test_aliases_kept_verbatim_for_loader_to_normalise(self) -> None:
        # Surface form preserved here — TriggerDetector / loader normalise later.
        content = "---\naliases: [Summarize, summarize.]\n---\nbody"
        result = parse_prompt_file(content)
        assert result is not None
        assert result.aliases == ["Summarize", "summarize."]


class TestLoadPromptsDir:
    def test_empty_directory_returns_empty_dict(self, tmp_path: Path) -> None:
        assert load_prompts_dir(tmp_path) == {}

    def test_missing_directory_returns_empty_dict(self, tmp_path: Path) -> None:
        assert load_prompts_dir(tmp_path / "does-not-exist") == {}

    def test_single_valid_file_registers_all_aliases(self, tmp_path: Path) -> None:
        (tmp_path / "summarize.md").write_text(
            "---\naliases: [summarize, summarise]\n---\nBODY",
            encoding="utf-8",
        )
        result = load_prompts_dir(tmp_path)
        assert result == {"summarize": "BODY", "summarise": "BODY"}

    def test_normalises_aliases_at_registration(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text(
            "---\naliases: [Summarize, 'summarize.']\n---\nBODY",
            encoding="utf-8",
        )
        result = load_prompts_dir(tmp_path)
        assert result == {"summarize": "BODY"}

    def test_mix_of_valid_and_malformed(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        (tmp_path / "good.md").write_text(
            "---\naliases: [good]\n---\nBODY", encoding="utf-8",
        )
        (tmp_path / "bad.md").write_text("no frontmatter here", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="dictatem.transform.prompts"):
            result = load_prompts_dir(tmp_path)
        assert result == {"good": "BODY"}

    def test_collision_keeps_first_and_warns(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        # Sorted glob order: a.md before b.md → a wins.
        (tmp_path / "a.md").write_text(
            "---\naliases: [shared]\n---\nFROM_A", encoding="utf-8",
        )
        (tmp_path / "b.md").write_text(
            "---\naliases: [shared]\n---\nFROM_B", encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING, logger="dictatem.transform.prompts"):
            result = load_prompts_dir(tmp_path)
        assert result == {"shared": "FROM_A"}
        assert any("already registered" in r.message for r in caplog.records)

    def test_non_md_files_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "README.txt").write_text(
            "---\naliases: [nope]\n---\nignored", encoding="utf-8",
        )
        (tmp_path / "real.md").write_text(
            "---\naliases: [real]\n---\nBODY", encoding="utf-8",
        )
        result = load_prompts_dir(tmp_path)
        assert result == {"real": "BODY"}


class TestBootstrapPrompts:
    def test_creates_target_dir_if_missing(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "summarize.md").write_text(
            "---\naliases: [summarize]\n---\nBODY", encoding="utf-8",
        )
        target = tmp_path / "target"
        assert not target.exists()
        bootstrap_prompts(target, source)
        assert (target / "summarize.md").exists()

    def test_copies_every_default_when_target_empty(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "a.md").write_text("body-a", encoding="utf-8")
        (source / "b.md").write_text("body-b", encoding="utf-8")
        target = tmp_path / "target"
        bootstrap_prompts(target, source)
        assert (target / "a.md").read_text(encoding="utf-8") == "body-a"
        assert (target / "b.md").read_text(encoding="utf-8") == "body-b"

    def test_does_not_overwrite_existing_user_file(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "summarize.md").write_text("default body", encoding="utf-8")
        target = tmp_path / "target"
        target.mkdir()
        (target / "summarize.md").write_text("user edit", encoding="utf-8")
        bootstrap_prompts(target, source)
        assert (target / "summarize.md").read_text(encoding="utf-8") == "user edit"

    def test_copies_missing_defaults_alongside_existing(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "a.md").write_text("default-a", encoding="utf-8")
        (source / "b.md").write_text("default-b", encoding="utf-8")
        target = tmp_path / "target"
        target.mkdir()
        (target / "a.md").write_text("user-a", encoding="utf-8")
        bootstrap_prompts(target, source)
        assert (target / "a.md").read_text(encoding="utf-8") == "user-a"
        assert (target / "b.md").read_text(encoding="utf-8") == "default-b"

    def test_missing_source_is_noop(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        bootstrap_prompts(target, tmp_path / "missing")
        # Target dir was still created (mkdir parents=True, exist_ok=True).
        assert target.is_dir()
        assert list(target.iterdir()) == []


class TestShippedDefaults:
    """Sanity: the bundled summarize.md parses and registers correctly."""

    def test_bundled_summarize_is_loadable(self, tmp_path: Path) -> None:
        bootstrap_prompts(tmp_path, default_prompts_dir())
        aliases = load_prompts_dir(tmp_path)
        assert "summarize" in aliases
        assert "summarise" in aliases
        assert aliases["summarize"] == aliases["summarise"]
        assert "condenser" in aliases["summarize"].lower()
