"""Built-in `paste` Trigger Word — re-paste the Most-recent dictation (#139).

Drives the full PTT → transcription → built-in-action routing → paste pipeline
through fakes, asserting that saying "paste" re-pastes the Most-recent dictation
buffer (#119) via the normal clipboard + Ctrl+V path, runs regardless of
`[transform].enabled` and with no prior Last Paste, shadows a same-named user
alias, and flashes the existing error on an empty buffer (never typing the
literal word). The routing decision is pure; the paste itself is manual-QA.
"""

from __future__ import annotations

import pytest

from dictatem.daemon import DaemonCore
from dictatem.state import Event, State, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
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
PASTE_PROMPT = "SYSTEM: this should be shadowed."
ALIASES = {"summarize": SUMMARIZE_PROMPT}


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
def overlay() -> FakeOverlayRenderer:
    return FakeOverlayRenderer()


@pytest.fixture
def transform_backend() -> FakeTransformBackend:
    return FakeTransformBackend()


def _make_core(
    *,
    backend: FakeTranscriberBackend,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    overlay: FakeOverlayRenderer,
    transform_backend: FakeTransformBackend,
    transform_enabled: bool = True,
    aliases: dict[str, str] | None = None,
) -> DaemonCore:
    return DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=overlay,
        tray=FakeTrayRenderer(),
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=FakeForegroundTracker(target_id=42),
        transform_lifecycle=TransformLifecycle(backend=transform_backend),
        trigger_detector=TriggerDetector(aliases if aliases is not None else ALIASES),
        transform_enabled=transform_enabled,
        last_paste_ttl_s=300.0,
    )


@pytest.fixture
def core(
    backend: FakeTranscriberBackend,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    overlay: FakeOverlayRenderer,
    transform_backend: FakeTransformBackend,
) -> DaemonCore:
    return _make_core(
        backend=backend, clipboard=clipboard, keystroke=keystroke, overlay=overlay,
        transform_backend=transform_backend,
    )


def _cycle(core: DaemonCore, *, start_ms: int, end_ms: int) -> None:
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=start_ms)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=start_ms + 200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=end_ms)
    core.drain_transcription_for_test(now_ms=end_ms)


def _set_texts(clipboard: FakeClipboardIO) -> list[str]:
    return [c[1] for c in clipboard.calls if c[0] == "set_text"]


class TestPasteReRePastes:
    def test_paste_re_pastes_the_most_recent_dictation(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
    ) -> None:
        backend._result = "hello world"
        _cycle(core, start_ms=0, end_ms=1_000)
        assert keystroke.paste_count == 1

        # Say "paste" — re-pastes the buffer via clipboard + Ctrl+V.
        backend._result = "paste"
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert _set_texts(clipboard) == ["hello world ", "hello world "]
        assert keystroke.paste_count == 2
        # Never a typed-replacement (no backspaces, nothing typed).
        assert keystroke.total_backspaces == 0
        assert keystroke.typed_texts == []

    @pytest.mark.parametrize("form", ["paste", "Paste.", "paste?", "PASTE"])
    def test_case_and_punctuation_forms_all_fire(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        form: str,
    ) -> None:
        backend._result = "recover me"
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = form
        _cycle(core, start_ms=2_000, end_ms=3_000)
        assert _set_texts(clipboard) == ["recover me ", "recover me "]

    def test_multi_word_paste_this_is_regular_dictation(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
    ) -> None:
        backend._result = "earlier"
        _cycle(core, start_ms=0, end_ms=1_000)
        # "paste this" is dictation, not the action — pasted verbatim.
        backend._result = "paste this"
        _cycle(core, start_ms=2_000, end_ms=3_000)
        assert _set_texts(clipboard) == ["earlier ", "paste this "]


class TestDecoupledFromTransform:
    def test_works_with_transform_disabled(
        self,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        transform_backend: FakeTransformBackend,
    ) -> None:
        # Built-in action detection must not be gated on the Transform feature.
        core = _make_core(
            backend=backend, clipboard=clipboard, keystroke=keystroke,
            overlay=overlay, transform_backend=transform_backend,
            transform_enabled=False,
        )
        backend._result = "no transform here"
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = "paste"
        _cycle(core, start_ms=2_000, end_ms=3_000)
        assert _set_texts(clipboard) == ["no transform here ", "no transform here "]

    def test_works_with_no_prior_last_paste_and_arms_it(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
    ) -> None:
        # The built-in reads the buffer, NOT Last Paste — so it fires even with
        # no Last Paste, and its re-paste then becomes the new Last Paste.
        core._most_recent_dictation = "recover this "
        core._last_paste = None

        backend._result = "paste"
        _cycle(core, start_ms=0, end_ms=1_000)

        assert _set_texts(clipboard) == ["recover this "]
        assert core._last_paste is not None
        assert core._last_paste.text == "recover this "

    def test_re_paste_arms_a_following_trigger_word(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
    ) -> None:
        # Buffer set, but NO Last Paste yet — only the `paste` re-paste arms it.
        core._most_recent_dictation = "recover this "
        core._last_paste = None

        backend._result = "paste"
        _cycle(core, start_ms=0, end_ms=1_000)
        assert core._last_paste is not None  # re-paste armed it

        # Now "summarize" fires a Transform on the re-pasted text.
        backend._result = "summarize"
        transform_backend.queue_result("CONDENSED")
        _cycle(core, start_ms=2_000, end_ms=3_000)
        assert transform_backend.calls == [("recover this ", SUMMARIZE_PROMPT)]
        assert keystroke.typed_texts == ["CONDENSED "]


class TestEmptyBuffer:
    def test_empty_buffer_flashes_error_and_types_nothing(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
    ) -> None:
        # Never any dictation → empty buffer. "paste" must no-op with the error
        # flash and NEVER type the literal word "paste".
        backend._result = "paste"
        _cycle(core, start_ms=0, end_ms=1_000)

        assert _set_texts(clipboard) == []
        assert keystroke.paste_count == 0
        assert keystroke.typed_texts == []
        assert any(c[0] == "show_error" for c in overlay.calls)
        assert core._most_recent_dictation is None
        assert core._sm.state is State.IDLE


class TestShadowsUserAlias:
    def test_builtin_paste_wins_over_a_user_paste_alias(
        self,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
        transform_backend: FakeTransformBackend,
    ) -> None:
        # A user Prompt File aliased `paste` is shadowed by the built-in: saying
        # "paste" re-pastes (built-in), it does NOT run the user's Transform.
        core = _make_core(
            backend=backend, clipboard=clipboard, keystroke=keystroke,
            overlay=overlay, transform_backend=transform_backend,
            aliases={"paste": PASTE_PROMPT, "summarize": SUMMARIZE_PROMPT},
        )
        backend._result = "some dictation"
        _cycle(core, start_ms=0, end_ms=1_000)

        backend._result = "paste"
        transform_backend.queue_result("SHOULD NOT RUN")
        _cycle(core, start_ms=2_000, end_ms=3_000)

        # Built-in re-paste happened; the (shadowed) Transform did not run.
        assert _set_texts(clipboard) == ["some dictation ", "some dictation "]
        assert transform_backend.calls == []
        assert keystroke.typed_texts == []
