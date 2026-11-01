"""Tests for the Trigger Word recognizer — the one pure trigger decision (#246).

Carries over the meaning of the old TriggerDetector / match_builtin_action
tests (exact, case, punctuation, whitespace, multi-token rejection, shadowed
built-in aliases) onto the single ``decide(Utterance, armed)`` seam.
"""

from __future__ import annotations

import pytest

from dictatem.transform.recognizer import (
    PASTE_ACTION,
    Borderline,
    BuiltinAction,
    Dictation,
    Fire,
    MatchVia,
    ScoreBand,
    TransformTarget,
    TriggerWordRecognizer,
    Utterance,
    shadowed_builtin_aliases,
)
from dictatem.types import SegmentConfidence

SUMMARIZE = "summarize prompt body"
EXPAND = "expand prompt body"

ALIASES = {
    "summarize": SUMMARIZE,
    "summarise": SUMMARIZE,
    "expand": EXPAND,
}

PASTE = Fire(BuiltinAction(PASTE_ACTION))


def _utt(text: str, duration_s: float = 1.0) -> Utterance:
    return Utterance(text=text, speech_duration_s=duration_s)


def _prompt(decision: object) -> str | None:
    """The Transform prompt body a decision fires, or None."""
    if isinstance(decision, Fire) and isinstance(decision.target, TransformTarget):
        return decision.target.prompt
    return None


def _armed(rec: TriggerWordRecognizer, text: str) -> object:
    return rec.decide(_utt(text), transforms_armed=True)


class TestEmptyMap:
    def test_empty_map_matches_nothing_but_builtins(self) -> None:
        rec = TriggerWordRecognizer({})
        assert _armed(rec, "summarize") == Dictation()
        assert _armed(rec, "paste") == PASTE


class TestTransformExactHits:
    def test_exact_match_fires_the_transform(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        decision = _armed(rec, "summarize")
        assert decision == Fire(TransformTarget(alias="summarize", prompt=SUMMARIZE))

    def test_case_insensitive(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        assert _prompt(_armed(rec, "SUMMARIZE")) == SUMMARIZE
        assert _prompt(_armed(rec, "Summarize")) == SUMMARIZE

    def test_trailing_punctuation_stripped(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        for text in ("Summarize.", "summarize!", "summarize?"):
            assert _prompt(_armed(rec, text)) == SUMMARIZE, text

    def test_leading_and_trailing_whitespace_stripped(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        assert _prompt(_armed(rec, "  summarize  ")) == SUMMARIZE
        assert _prompt(_armed(rec, "\tsummarize\n")) == SUMMARIZE

    def test_alias_variants_hit_same_transform(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        for text in ("summarise", "summarize", "Summarise."):
            assert _prompt(_armed(rec, text)) == SUMMARIZE, text


class TestDictation:
    def test_unknown_word(self) -> None:
        assert _armed(TriggerWordRecognizer(ALIASES), "hello") == Dictation()

    def test_empty_whitespace_and_punctuation_only(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        for text in ("", "   ", "....."):
            assert _armed(rec, text) == Dictation(), repr(text)

    def test_multi_token_is_dictation(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        for text in (
            "summarize this",
            "please summarize that",
            "summarize, please",
            "summarize\nthis",
        ):
            assert _armed(rec, text) == Dictation(), repr(text)


class TestArmedGate:
    def test_unarmed_transform_is_dictation(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        decision = rec.decide(_utt("summarize"), transforms_armed=False)
        assert decision == Dictation()

    def test_builtin_paste_fires_even_unarmed(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        assert rec.decide(_utt("paste"), transforms_armed=False) == PASTE


class TestBuiltinPaste:
    def test_paste_action_constant(self) -> None:
        assert PASTE_ACTION == "paste"

    def test_case_and_punctuation_forms_fire(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        for text in ("paste", "Paste.", "paste?", "PASTE", "  paste  ", "\tPaste!\n"):
            assert _armed(rec, text) == PASTE, repr(text)

    def test_multi_word_paste_is_dictation(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        for text in ("paste this", "please paste", "paste, please"):
            assert _armed(rec, text) == Dictation(), text

    def test_builtin_shadows_a_user_paste_alias(self) -> None:
        rec = TriggerWordRecognizer({"paste": "a user paste Transform"})
        assert _armed(rec, "paste") == PASTE


class TestRegistrationNormalisation:
    def test_alias_with_punctuation_registered_after_normalise(self) -> None:
        rec = TriggerWordRecognizer({"Summarize.": SUMMARIZE})
        assert _prompt(_armed(rec, "summarize")) == SUMMARIZE

    def test_alias_with_mixed_case_registered_lowercase(self) -> None:
        rec = TriggerWordRecognizer({"SUMMARIZE": SUMMARIZE})
        assert _prompt(_armed(rec, "summarize")) == SUMMARIZE

    def test_empty_alias_string_ignored(self) -> None:
        rec = TriggerWordRecognizer({"": SUMMARIZE, "summarize": SUMMARIZE})
        assert _prompt(_armed(rec, "summarize")) == SUMMARIZE
        assert _armed(rec, "") == Dictation()


class TestConfidenceDoesNotAffectExactMatching:
    def test_bad_confidence_still_fires_exact(self) -> None:
        rec = TriggerWordRecognizer(ALIASES)
        unsure = SegmentConfidence(avg_logprob=-3.0, no_speech_prob=0.99)
        utt = Utterance(text="summarize", speech_duration_s=0.6, confidence=unsure)
        assert _prompt(rec.decide(utt, transforms_armed=True)) == SUMMARIZE
        utt = Utterance(text="paste", speech_duration_s=0.6, confidence=unsure)
        assert rec.decide(utt, transforms_armed=False) == PASTE


# --- Fuzzy tier (#247) -----------------------------------------------------
#
# The golden table is the contract: decisions only, never scores, phonetic key
# strings or threshold constants, so the thresholds stay tunable.

POLISH = "polish prompt body"
# The shipped default Prompt Files' aliases (default_prompts/).
DEFAULT_ALIASES = {
    "summarize": SUMMARIZE,
    "summarise": SUMMARIZE,
    "polish": POLISH,
    "cleanup": POLISH,
}

CONFIDENT = SegmentConfidence(avg_logprob=-0.3, no_speech_prob=0.05)


def _fuzzy_decide(
    text: str,
    *,
    duration_s: float = 0.8,
    confidence: SegmentConfidence | None = CONFIDENT,
    armed: bool = True,
    aliases: dict[str, str] | None = None,
    fuzzy_matching: bool = True,
) -> object:
    rec = TriggerWordRecognizer(
        DEFAULT_ALIASES if aliases is None else aliases,
        fuzzy_matching=fuzzy_matching,
    )
    utt = Utterance(text=text, speech_duration_s=duration_s, confidence=confidence)
    return rec.decide(utt, transforms_armed=armed)


def _candidate_prompts(decision: Borderline) -> set[str]:
    """The Transform prompt bodies a Borderline decision's candidates run."""
    return {t.prompt for t in decision.candidates if isinstance(t, TransformTarget)}


def _fires_paste(decision: object) -> bool:
    return isinstance(decision, Fire) and decision.target == BuiltinAction(PASTE_ACTION)


class TestFuzzyGoldenTable:
    @pytest.mark.parametrize("heard", ["haste", "Pasta.", "Haste."])
    def test_near_paste_fires_paste(self, heard: str) -> None:
        decision = _fuzzy_decide(heard)
        assert _fires_paste(decision), heard
        assert decision.via is MatchVia.FUZZY

    @pytest.mark.parametrize(
        ("heard", "prompt"),
        [
            ("summerize", SUMMARIZE),
            ("Summerise.", SUMMARIZE),
            ("palish", POLISH),
            ("cleanop", POLISH),
            ("clean up", POLISH),
            ("Clean up.", POLISH),
        ],
    )
    def test_near_transform_alias_fires_that_transform(
        self, heard: str, prompt: str
    ) -> None:
        decision = _fuzzy_decide(heard)
        assert _prompt(decision) == prompt, heard
        assert decision.via is MatchVia.FUZZY

    @pytest.mark.parametrize(
        "heard",
        [
            "thank you",
            "okay",
            "hello",
            "Thank you.",
            "summarize this",
            "paste it",
            "paste this",
            "polish it",
            "Summarize this.",
            # > 3 tokens: never a Trigger Word, however close the joined form.
            "clean up the doc",
            "paste it in here",
        ],
    )
    def test_negatives_are_dictation(self, heard: str) -> None:
        assert _fuzzy_decide(heard) == Dictation(), heard

    def test_long_speech_is_dictation(self) -> None:
        assert _fuzzy_decide("haste", duration_s=4.0) == Dictation()
        assert _fuzzy_decide("summerize", duration_s=4.0) == Dictation()

    def test_weak_match_is_borderline(self) -> None:
        # "some of us" only sounds roughly like "summarise": a weak match.
        # Not sure enough to fire, too close to paste as dictation (#248).
        decision = _fuzzy_decide("some of us")
        assert isinstance(decision, Borderline)
        assert _candidate_prompts(decision) == {SUMMARIZE}
        assert decision.band is ScoreBand.WEAK

    def test_weak_match_to_an_unarmed_transform_is_dictation(self) -> None:
        # An unarmed Transform is never a candidate — not even a Borderline one.
        assert _fuzzy_decide("some of us", armed=False) == Dictation()


class TestFuzzyConfidenceGuardrail:
    def test_unknown_confidence_is_no_evidence_against(self) -> None:
        assert _fires_paste(_fuzzy_decide("haste", confidence=None))
        assert _prompt(_fuzzy_decide("summerize", confidence=None)) == SUMMARIZE

    def test_high_no_speech_prob_makes_a_strong_match_borderline(self) -> None:
        noisy = SegmentConfidence(avg_logprob=-0.3, no_speech_prob=0.9)
        haste = _fuzzy_decide("haste", confidence=noisy)
        assert isinstance(haste, Borderline)
        assert haste.candidates == (BuiltinAction(PASTE_ACTION),)
        assert haste.band is ScoreBand.STRONG
        summ = _fuzzy_decide("summerize", confidence=noisy)
        assert isinstance(summ, Borderline)
        assert _candidate_prompts(summ) == {SUMMARIZE}

    def test_low_avg_logprob_makes_a_strong_match_borderline(self) -> None:
        unsure = SegmentConfidence(avg_logprob=-1.8, no_speech_prob=0.05)
        haste = _fuzzy_decide("haste", confidence=unsure)
        assert isinstance(haste, Borderline)
        assert haste.candidates == (BuiltinAction(PASTE_ACTION),)
        palish = _fuzzy_decide("palish", confidence=unsure)
        assert isinstance(palish, Borderline)
        assert _candidate_prompts(palish) == {POLISH}

    def test_exact_match_ignores_bad_confidence(self) -> None:
        unsure = SegmentConfidence(avg_logprob=-3.0, no_speech_prob=0.99)
        decision = _fuzzy_decide("paste", confidence=unsure)
        assert _fires_paste(decision)
        assert decision.via is MatchVia.EXACT


class TestFuzzyGates:
    def test_unarmed_transform_is_never_a_fuzzy_candidate(self) -> None:
        assert _fuzzy_decide("summerize", armed=False) == Dictation()
        assert _fuzzy_decide("clean up", armed=False) == Dictation()

    def test_fuzzy_paste_fires_unarmed(self) -> None:
        assert _fires_paste(_fuzzy_decide("haste", armed=False))

    def test_short_alias_is_exact_only(self) -> None:
        aliases = {"tldr": "tldr prompt body"}
        assert _prompt(_fuzzy_decide("tldr", aliases=aliases)) == "tldr prompt body"
        assert _fuzzy_decide("tldk", aliases=aliases) == Dictation()

    def test_shadowed_user_paste_alias_never_wins_fuzzily(self) -> None:
        aliases = {"paste": "a user paste Transform"}
        assert _fires_paste(_fuzzy_decide("haste", aliases=aliases))

    def test_cross_action_tie_is_borderline_with_both_candidates(self) -> None:
        # Two different Transforms whose aliases are equally close to what
        # was heard: never guess between them — ask again (#248).
        aliases = {"rewrite": "rewrite body", "rewrote": "rewrote body"}
        decision = _fuzzy_decide("rewrute", aliases=aliases)
        assert isinstance(decision, Borderline)
        assert _candidate_prompts(decision) == {"rewrite body", "rewrote body"}

    def test_same_action_variants_are_not_a_tie(self) -> None:
        # summarize/summarise share one Transform: no ambiguity.
        assert _prompt(_fuzzy_decide("summarice")) == SUMMARIZE


class TestFuzzyEscapeHatch:
    def test_fuzzy_matching_off_is_exact_only(self) -> None:
        assert _fuzzy_decide("haste", fuzzy_matching=False) == Dictation()
        assert _fuzzy_decide("summerize", fuzzy_matching=False) == Dictation()
        assert _fuzzy_decide("clean up", fuzzy_matching=False) == Dictation()

    def test_fuzzy_matching_off_keeps_exact_matches(self) -> None:
        assert _fires_paste(_fuzzy_decide("paste", fuzzy_matching=False))
        assert _prompt(_fuzzy_decide("polish", fuzzy_matching=False)) == POLISH


# --- Confirm pass (#249) ---------------------------------------------------

UNSURE = SegmentConfidence(avg_logprob=-1.8, no_speech_prob=0.05)


def _borderline(
    rec: TriggerWordRecognizer,
    text: str,
    confidence: SegmentConfidence | None = CONFIDENT,
) -> Borderline:
    utt = Utterance(text=text, speech_duration_s=0.8, confidence=confidence)
    decision = rec.decide(utt, transforms_armed=True)
    assert isinstance(decision, Borderline), text
    return decision


def _confirm(
    rec: TriggerWordRecognizer,
    borderline: Borderline,
    heard: str,
    confidence: SegmentConfidence | None = CONFIDENT,
) -> object:
    utt = Utterance(text=heard, speech_duration_s=0.8, confidence=confidence)
    return rec.confirm(borderline, utt, transforms_armed=True)


class TestConfirm:
    """A Borderline gets one command-biased listen; it fires only a candidate."""

    def test_some_of_us_then_summarise_fires_summarize(self) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES)
        first = _borderline(rec, "some of us")
        assert _prompt(_confirm(rec, first, "Summarise.")) == SUMMARIZE

    def test_a_different_alias_of_the_candidate_action_fires(self) -> None:
        # Candidates are compared by action, not by the alias that scored.
        rec = TriggerWordRecognizer(DEFAULT_ALIASES)
        first = _borderline(rec, "some of us")
        assert _prompt(_confirm(rec, first, "summarize")) == SUMMARIZE
        assert _prompt(_confirm(rec, first, "summerise")) == SUMMARIZE

    def test_exact_match_for_a_different_action_stays_borderline(self) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES)
        first = _borderline(rec, "some of us")
        assert _confirm(rec, first, "paste") == first
        assert _confirm(rec, first, "polish") == first

    def test_strong_confident_match_for_a_different_action_stays_borderline(
        self,
    ) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES)
        first = _borderline(rec, "some of us")
        assert _confirm(rec, first, "haste") == first

    @pytest.mark.parametrize("heard", ["some of us", "hello there", "summarize this"])
    def test_no_better_hearing_stays_borderline(self, heard: str) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES)
        first = _borderline(rec, "some of us")
        assert _confirm(rec, first, heard) == first

    def test_unconfident_strong_confirm_stays_borderline(self) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES)
        first = _borderline(rec, "haste", confidence=UNSURE)
        assert _confirm(rec, first, "Haste.", confidence=UNSURE) == first

    def test_unconfident_strong_then_confident_confirm_fires(self) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES)
        first = _borderline(rec, "haste", confidence=UNSURE)
        assert _fires_paste(_confirm(rec, first, "Paste."))

    def test_cross_action_tie_resolves_to_the_confirmed_candidate(self) -> None:
        rec = TriggerWordRecognizer({"rewrite": "rewrite body", "rewrote": "rewrote body"})
        first = _borderline(rec, "rewrute")
        assert len(first.candidates) == 2
        assert _prompt(_confirm(rec, first, "Rewrote.")) == "rewrote body"

    def test_paste_alias_confirms_a_paste_candidate(self) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES, paste_aliases=["glue"])
        first = _borderline(rec, "haste", confidence=UNSURE)
        assert _fires_paste(_confirm(rec, first, "Glue."))


class TestTriggerWords:
    """The lexicon the confirm pass's command bias names (#249)."""

    def test_armed_lists_builtins_paste_aliases_and_transform_aliases(self) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES, paste_aliases=["glue"])
        assert rec.trigger_words(transforms_armed=True) == [
            "glue",
            "paste",
            "summarize",
            "summarise",
            "polish",
            "cleanup",
        ]

    def test_unarmed_lists_only_the_builtins(self) -> None:
        rec = TriggerWordRecognizer(DEFAULT_ALIASES, paste_aliases=["glue"])
        assert rec.trigger_words(transforms_armed=False) == ["glue", "paste"]

    def test_shadowed_prompt_file_alias_is_not_listed_twice(self) -> None:
        rec = TriggerWordRecognizer({"paste": "x", "polish": POLISH})
        assert rec.trigger_words(transforms_armed=True) == ["paste", "polish"]


class TestPasteAliases:
    """User-declared aliases for the built-in `paste` action (#250)."""

    def test_paste_alias_fires_paste_exactly_with_transforms_unarmed(self) -> None:
        rec = TriggerWordRecognizer(ALIASES, paste_aliases=["glue"], fuzzy_matching=False)
        for text in ("glue", "Glue.", "  GLUE!  "):
            decision = rec.decide(_utt(text), transforms_armed=False)
            assert _fires_paste(decision), repr(text)
            assert decision.via is MatchVia.EXACT

    def test_paste_alias_takes_part_in_fuzzy_matching(self) -> None:
        rec = TriggerWordRecognizer(ALIASES, paste_aliases=["insert"])
        utt = Utterance(text="Insurt.", speech_duration_s=0.7, confidence=CONFIDENT)
        decision = rec.decide(utt, transforms_armed=False)
        assert _fires_paste(decision)
        assert decision.via is MatchVia.FUZZY

    def test_paste_alias_fuzzy_respects_the_short_gate(self) -> None:
        rec = TriggerWordRecognizer(ALIASES, paste_aliases=["insert"])
        assert rec.decide(_utt("insurt", duration_s=4.0), transforms_armed=False) == Dictation()

    def test_paste_alias_followed_by_more_words_is_dictation(self) -> None:
        rec = TriggerWordRecognizer(ALIASES, paste_aliases=["insert"])
        for text in ("insert this", "insert it"):
            assert rec.decide(_utt(text), transforms_armed=True) == Dictation(), text

    def test_fuzzy_matching_off_makes_paste_aliases_exact_only(self) -> None:
        rec = TriggerWordRecognizer(ALIASES, paste_aliases=["insert"], fuzzy_matching=False)
        assert rec.decide(_utt("insurt"), transforms_armed=False) == Dictation()

    def test_paste_alias_shadows_a_same_named_prompt_file_alias(self) -> None:
        rec = TriggerWordRecognizer(
            {"insert": "an insert Transform", **ALIASES}, paste_aliases=["Insert"]
        )
        assert _armed(rec, "insert") == PASTE
        # ... fuzzily too: the shadowed Transform is not a candidate.
        utt = Utterance(text="insurt", speech_duration_s=0.7, confidence=CONFIDENT)
        assert _fires_paste(rec.decide(utt, transforms_armed=True))

    def test_blank_paste_aliases_are_ignored(self) -> None:
        rec = TriggerWordRecognizer(ALIASES, paste_aliases=["", "  ", "..."])
        assert _armed(rec, "") == Dictation()
        assert _armed(rec, "paste") == PASTE


class TestShadowedBuiltinAliases:
    def test_no_collision_returns_empty(self) -> None:
        assert shadowed_builtin_aliases(["summarize", "expand"]) == []

    def test_exact_paste_alias_is_shadowed(self) -> None:
        assert shadowed_builtin_aliases(["paste", "summarize"]) == ["paste"]

    def test_surface_form_alias_is_shadowed(self) -> None:
        assert shadowed_builtin_aliases(["Paste.", "expand"]) == ["Paste."]

    def test_alias_shadowed_by_a_paste_alias_is_reported(self) -> None:
        out = shadowed_builtin_aliases(
            ["insert", "summarize", "Paste."], paste_aliases=["Insert!"]
        )
        assert out == ["Paste.", "insert"]

    def test_result_is_deduped_and_sorted(self) -> None:
        out = shadowed_builtin_aliases(["paste", "paste", "PASTE"])
        assert out == sorted(set(out))
