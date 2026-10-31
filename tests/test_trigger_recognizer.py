"""Tests for the Trigger Word recognizer — the one pure trigger decision (#246).

Carries over the meaning of the old TriggerDetector / match_builtin_action
tests (exact, case, punctuation, whitespace, multi-token rejection, shadowed
built-in aliases) onto the single ``decide(Utterance, armed)`` seam.
"""

from __future__ import annotations

from dictatem.transform.recognizer import (
    PASTE_ACTION,
    BuiltinAction,
    Dictation,
    Fire,
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


class TestShadowedBuiltinAliases:
    def test_no_collision_returns_empty(self) -> None:
        assert shadowed_builtin_aliases(["summarize", "expand"]) == []

    def test_exact_paste_alias_is_shadowed(self) -> None:
        assert shadowed_builtin_aliases(["paste", "summarize"]) == ["paste"]

    def test_surface_form_alias_is_shadowed(self) -> None:
        assert shadowed_builtin_aliases(["Paste.", "expand"]) == ["Paste."]

    def test_result_is_deduped_and_sorted(self) -> None:
        out = shadowed_builtin_aliases(["paste", "paste", "PASTE"])
        assert out == sorted(set(out))
