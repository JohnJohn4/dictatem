"""Wiring test: Replacements apply to regular dictation, never to Trigger Words.

Drives the full PTT → transcription → (optional trigger) → paste pipeline
through fakes and asserts that Replacement rules rewrite *regular dictation*
before it reaches the clipboard, while a Trigger Word utterance is intercepted
before paste and therefore left untouched (ADR-0024 / #125).
"""

from __future__ import annotations

import pytest

from dictatem.daemon import DaemonCore
from dictatem.state import Event, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.transcribe.replacements import Replacement
from dictatem.transform.detector import TriggerDetector
from dictatem.transform.lifecycle import TransformLifecycle
from tests.fakes import (
    FakeAudioCapture,
    FakeClipboardIO,
    FakeForegroundTracker,
    FakeKeystrokeSender,
    FakeOverlayRenderer,
    FakeTranscriberBackend,
    FakeTransformBackend,
    FakeTrayRenderer,
)

SUMMARIZE_PROMPT = "SYSTEM: summarize this text."
ALIASES = {"summarize": SUMMARIZE_PROMPT, "summarise": SUMMARIZE_PROMPT}


@pytest.fixture
def backend() -> FakeTranscriberBackend:
    return FakeTranscriberBackend(result="hello world")


@pytest.fixture
def clipboard() -> FakeClipboardIO:
    return FakeClipboardIO()


@pytest.fixture
def keystroke() -> FakeKeystrokeSender:
    return FakeKeystrokeSender()


@pytest.fixture
def transform_backend() -> FakeTransformBackend:
    return FakeTransformBackend()


def _make_core(
    *,
    backend: FakeTranscriberBackend,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    transform_backend: FakeTransformBackend,
    replacements: list[Replacement],
) -> DaemonCore:
    return DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=FakeOverlayRenderer(),
        tray=FakeTrayRenderer(),
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=FakeForegroundTracker(target_id=42),
        transform_lifecycle=TransformLifecycle(backend=transform_backend),
        trigger_detector=TriggerDetector(ALIASES),
        transform_enabled=True,
        last_paste_ttl_s=300.0,
        replacements=replacements,
    )


def _cycle(core: DaemonCore, *, start_ms: int, end_ms: int) -> None:
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=start_ms)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=start_ms + 200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=end_ms)
    core.drain_transcription_for_test(now_ms=end_ms)


def _set_texts(clipboard: FakeClipboardIO) -> list[str]:
    return [c[1] for c in clipboard.calls if c[0] == "set_text"]


class TestReplacementsOnRegularDictation:
    def test_substitution_applied_before_paste(
        self,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        transform_backend: FakeTransformBackend,
    ) -> None:
        core = _make_core(
            backend=backend, clipboard=clipboard, keystroke=keystroke,
            transform_backend=transform_backend,
            replacements=[Replacement(source="teh", target="the")],
        )
        backend._result = "teh cat sat"
        _cycle(core, start_ms=0, end_ms=1_000)
        # The replaced text reaches the clipboard (normalised: trailing space).
        assert _set_texts(clipboard) == ["the cat sat "]

    def test_empty_target_deletes_filler_before_paste(
        self,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        transform_backend: FakeTransformBackend,
    ) -> None:
        core = _make_core(
            backend=backend, clipboard=clipboard, keystroke=keystroke,
            transform_backend=transform_backend,
            replacements=[Replacement(source="um", target="")],
        )
        backend._result = "so um yeah"
        _cycle(core, start_ms=0, end_ms=1_000)
        assert _set_texts(clipboard) == ["so yeah "]

    def test_no_rules_leaves_dictation_unchanged(
        self,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        transform_backend: FakeTransformBackend,
    ) -> None:
        core = _make_core(
            backend=backend, clipboard=clipboard, keystroke=keystroke,
            transform_backend=transform_backend, replacements=[],
        )
        backend._result = "teh cat sat"
        _cycle(core, start_ms=0, end_ms=1_000)
        assert _set_texts(clipboard) == ["teh cat sat "]


class TestReplacementsDoNotTouchTriggerWords:
    def test_trigger_word_is_not_rewritten_by_a_matching_rule(
        self,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        transform_backend: FakeTransformBackend,
    ) -> None:
        # A pathological rule that would rewrite the trigger word itself. The
        # Trigger Word path is intercepted before paste, so the rule must NOT
        # apply: 'summarize' must still fire the Transform.
        core = _make_core(
            backend=backend, clipboard=clipboard, keystroke=keystroke,
            transform_backend=transform_backend,
            replacements=[Replacement(source="summarize", target="banana")],
        )
        # Prime a Last Paste with regular dictation.
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)

        # Utter the trigger word.
        backend._result = "summarize"
        transform_backend.queue_result("CONDENSED")
        _cycle(core, start_ms=2_000, end_ms=3_000)

        # The Transform fired on the prior Last Paste — the trigger word was
        # NOT rewritten to "banana" (which would not match any alias).
        assert transform_backend.calls == [("the verbose text ", SUMMARIZE_PROMPT)]
        assert keystroke.typed_texts == ["CONDENSED "]

    def test_transform_output_is_not_rewritten(
        self,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        transform_backend: FakeTransformBackend,
    ) -> None:
        # A rule matching a word in the Transform OUTPUT must not apply — only
        # regular dictation is rewritten, not the LLM result.
        core = _make_core(
            backend=backend, clipboard=clipboard, keystroke=keystroke,
            transform_backend=transform_backend,
            replacements=[Replacement(source="condensed", target="EXPANDED")],
        )
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = "summarize"
        transform_backend.queue_result("condensed")
        _cycle(core, start_ms=2_000, end_ms=3_000)

        # Transform output typed verbatim, not rewritten.
        assert keystroke.typed_texts == ["condensed "]
