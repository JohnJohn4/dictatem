"""Tests for the load-time Trigger Word collision check (#251, spec #226 Layer 4).

The check is pure: given the Prompt Files' Aliases (file name -> Aliases) and
the user's ``paste`` aliases, it reports Aliases of *different* actions that
sound alike, and Aliases too short for fuzzy tolerance (exact-only).
"""

from __future__ import annotations

from dictatem.transform.collisions import (
    PASTE_ACTION_LABEL,
    AliasCollision,
    ExactOnlyAlias,
    check_trigger_lexicon,
)

DEFAULT_PROMPT_FILES = {
    "polish.md": ["polish", "cleanup"],
    "summarize.md": ["summarize", "summarise"],
}


def _pairs(report: object) -> set[frozenset[str]]:
    return {frozenset({c.alias, c.other_alias}) for c in report.collisions}  # type: ignore[attr-defined]


class TestCrossActionCollisions:
    def test_near_homophone_of_a_different_prompt_file_is_reported(self) -> None:
        report = check_trigger_lexicon({**DEFAULT_PROMPT_FILES, "grand.md": ["palace"]})
        assert report.collisions == [
            AliasCollision(
                alias="polish", action="polish.md", other_alias="palace", other_action="grand.md"
            )
        ]

    def test_same_action_variants_are_not_reported(self) -> None:
        report = check_trigger_lexicon({"summarize.md": ["summarize", "summarise"]})
        assert report.collisions == []

    def test_identical_phonetic_keys_across_actions_are_reported(self) -> None:
        report = check_trigger_lexicon(
            {"a.md": ["summarize"], "b.md": ["summarise"]}
        )
        assert _pairs(report) == {frozenset({"summarize", "summarise"})}

    def test_distinct_words_are_not_reported(self) -> None:
        report = check_trigger_lexicon({**DEFAULT_PROMPT_FILES, "expand.md": ["expand"]})
        assert report.collisions == []

    def test_builtin_paste_is_included(self) -> None:
        report = check_trigger_lexicon({"rush.md": ["haste"]})
        assert report.collisions == [
            AliasCollision(
                alias="paste",
                action=PASTE_ACTION_LABEL,
                other_alias="haste",
                other_action="rush.md",
            )
        ]

    def test_paste_aliases_are_included(self) -> None:
        report = check_trigger_lexicon(
            {**DEFAULT_PROMPT_FILES, "glossy.md": ["glossary"]}, paste_aliases=["glossy"]
        )
        assert report.collisions == [
            AliasCollision(
                alias="glossy",
                action=PASTE_ACTION_LABEL,
                other_alias="glossary",
                other_action="glossy.md",
            )
        ]

    def test_paste_alias_and_paste_are_one_action(self) -> None:
        report = check_trigger_lexicon({}, paste_aliases=["haste", "pasta"])
        assert report.collisions == []

    def test_shadowed_prompt_alias_is_not_reported_again(self) -> None:
        # A Prompt File alias equal to `paste` (or a paste alias) is already
        # warned as shadowed; it never competes, so it is not a collision.
        report = check_trigger_lexicon({"mine.md": ["paste", "insert"]}, paste_aliases=["insert"])
        assert report.collisions == []

    def test_alias_claimed_by_an_earlier_file_is_not_reported_again(self) -> None:
        # The loader keeps the first file's alias; the duplicate never loads.
        report = check_trigger_lexicon({"a.md": ["expand"], "b.md": ["expand"]})
        assert report.collisions == []

    def test_surface_forms_are_normalised(self) -> None:
        report = check_trigger_lexicon({"a.md": ["Polish."], "b.md": ["PALACE"]})
        assert _pairs(report) == {frozenset({"polish", "palace"})}


class TestExactOnlyAliases:
    def test_alias_below_fuzzy_minimum_is_reported(self) -> None:
        report = check_trigger_lexicon({"fix.md": ["fix", "repair"]})
        assert report.exact_only == [ExactOnlyAlias(alias="fix", action="fix.md")]

    def test_short_paste_alias_is_reported(self) -> None:
        report = check_trigger_lexicon({}, paste_aliases=["glue"])
        assert report.exact_only == [ExactOnlyAlias(alias="glue", action=PASTE_ACTION_LABEL)]

    def test_builtin_paste_itself_is_long_enough(self) -> None:
        assert check_trigger_lexicon({}).exact_only == []


class TestShippedDefaults:
    def test_default_prompts_produce_no_warnings(self) -> None:
        report = check_trigger_lexicon(DEFAULT_PROMPT_FILES)
        assert report.collisions == []
        assert report.exact_only == []

    def test_bundled_default_prompt_files_produce_no_warnings(self) -> None:
        from dictatem.transform.prompts import default_prompts_dir, load_prompts

        loaded = load_prompts(default_prompts_dir())
        report = check_trigger_lexicon(loaded.aliases_by_file())
        assert report.collisions == []
        assert report.exact_only == []
