"""Integration tests for the Trigger Fire flow in DaemonCore.

These tests drive the full dictation → trigger detection → Ollama → backspace
+ paste replacement pipeline through fakes, asserting the observable side
effects on clipboard, keystrokes, foreground tracker, and ``_last_paste``.

See acceptance criteria in #20 and the domain glossary in ``CONTEXT.md``.
"""

from __future__ import annotations

import pytest

from dictatem.daemon import DaemonCore
from dictatem.exceptions import TransformFailedError
from dictatem.state import Event, State, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from dictatem.transform.detector import TriggerDetector
from dictatem.transform.failure import OllamaFailure
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
def sm() -> StateMachine:
    return StateMachine(tap_threshold_ms=200)


@pytest.fixture
def backend() -> FakeTranscriberBackend:
    return FakeTranscriberBackend(result="hello world")


@pytest.fixture
def audio() -> FakeAudioCapture:
    return FakeAudioCapture(duration_s=1.0)


@pytest.fixture
def overlay() -> FakeOverlayRenderer:
    return FakeOverlayRenderer()


@pytest.fixture
def tray() -> FakeTrayRenderer:
    return FakeTrayRenderer()


@pytest.fixture
def clipboard() -> FakeClipboardIO:
    return FakeClipboardIO()


@pytest.fixture
def keystroke() -> FakeKeystrokeSender:
    return FakeKeystrokeSender()


@pytest.fixture
def foreground() -> FakeForegroundTracker:
    return FakeForegroundTracker(target_id=42)


@pytest.fixture
def transform_backend() -> FakeTransformBackend:
    return FakeTransformBackend()


@pytest.fixture
def transform_lifecycle(
    transform_backend: FakeTransformBackend,
) -> TransformLifecycle:
    return TransformLifecycle(backend=transform_backend)


@pytest.fixture
def trigger_detector() -> TriggerDetector:
    return TriggerDetector(ALIASES)


@pytest.fixture
def lifecycle(backend: FakeTranscriberBackend) -> TranscribeLifecycle:
    return TranscribeLifecycle(backend=backend, clock=lambda: 0.0)


@pytest.fixture
def core(
    sm: StateMachine,
    audio: FakeAudioCapture,
    lifecycle: TranscribeLifecycle,
    overlay: FakeOverlayRenderer,
    tray: FakeTrayRenderer,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    foreground: FakeForegroundTracker,
    transform_lifecycle: TransformLifecycle,
    trigger_detector: TriggerDetector,
) -> DaemonCore:
    return DaemonCore(
        state_machine=sm,
        audio_capture=audio,
        lifecycle=lifecycle,
        overlay=overlay,
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=foreground,
        transform_lifecycle=transform_lifecycle,
        trigger_detector=trigger_detector,
        transform_enabled=True,
        last_paste_ttl_s=300.0,
    )


def _cycle(core: DaemonCore, *, start_ms: int, end_ms: int) -> None:
    """Drive one PTT cycle and drain both transcription and transform queues."""
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=start_ms)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=start_ms + 200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=end_ms)
    core.drain_transcription_for_test(now_ms=end_ms)


def _set_texts(clipboard: FakeClipboardIO) -> list[str]:
    return [c[1] for c in clipboard.calls if c[0] == "set_text"]


class TestPreloadWarmsLLM:
    """Tray Preload also warms the Transform LLM in one click — gated on the
    model being available, never blocking Whisper preload (#74)."""

    def test_preload_warms_llm_when_available(
        self,
        core: DaemonCore,
        transform_backend: FakeTransformBackend,
        overlay: FakeOverlayRenderer,
    ) -> None:
        transform_backend.set_available(True)
        core.on_tray_preload()
        if core._llm_warm_thread is not None:
            core._llm_warm_thread.join(timeout=5.0)
        assert transform_backend.availability_checks == 1
        assert transform_backend.warm_calls == 1
        loading = [c for c in overlay.calls if c[0] == "show_loading"]
        assert any(c[1] == "Preloading Models" for c in loading)

    def test_preload_skips_llm_when_model_unavailable(
        self,
        core: DaemonCore,
        transform_backend: FakeTransformBackend,
    ) -> None:
        transform_backend.set_available(False)
        core.on_tray_preload()
        if core._llm_warm_thread is not None:
            core._llm_warm_thread.join(timeout=5.0)
        assert transform_backend.availability_checks == 1
        assert transform_backend.warm_calls == 0  # gated: model not pulled


class TestTriggerLoadingLabel:
    """A cold Trigger Fire says 'Loading LLM Model'; once the model is warm a
    follow-up trigger says 'LLM Model Computing' (#74)."""

    def test_cold_trigger_fire_labels_loading_llm_model(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        overlay: FakeOverlayRenderer,
    ) -> None:
        backend._result = "some verbose text to condense"
        _cycle(core, start_ms=0, end_ms=1_000)  # dictation -> Last Paste
        backend._result = "summarize"  # trigger word
        _cycle(core, start_ms=2_000, end_ms=3_000)
        labels = [c[1] for c in overlay.calls if c[0] == "show_loading"]
        assert "Loading LLM Model" in labels

    def test_warm_trigger_fire_labels_computing(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        overlay: FakeOverlayRenderer,
    ) -> None:
        # First trigger warms the LLM (cold -> "Loading LLM Model").
        backend._result = "first verbose text to condense"
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = "summarize"
        _cycle(core, start_ms=2_000, end_ms=3_000)
        # Second trigger within keep_alive: warm -> "LLM Model Computing".
        backend._result = "second verbose text to condense"
        _cycle(core, start_ms=4_000, end_ms=5_000)
        backend._result = "summarize"
        _cycle(core, start_ms=6_000, end_ms=7_000)
        labels = [c[1] for c in overlay.calls if c[0] == "show_loading"]
        assert "LLM Model Computing" in labels
        assert "Loading LLM Model" in labels  # the first (cold) one


# ── Happy path ───────────────────────────────────────────────────────


class TestTriggerFireHappyPath:
    def test_dictation_then_summarize_replaces_in_place(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
        clipboard: FakeClipboardIO,
    ) -> None:
        # First dictation: "the long verbose thing"
        backend._result = "the long verbose thing"
        _cycle(core, start_ms=0, end_ms=1_000)

        assert keystroke.paste_count == 1
        assert keystroke.total_backspaces == 0
        assert _set_texts(clipboard) == ["the long verbose thing "]
        assert keystroke.typed_texts == []
        assert transform_backend.calls == []  # no trigger yet

        # Second cycle: utter "summarize"
        backend._result = "summarize"
        transform_backend.queue_result("CONDENSED")
        _cycle(core, start_ms=2_000, end_ms=3_000)

        # Replacement: backspaces = char_count of previous LastPaste.
        # "the long verbose thing" → normalize → "the long verbose thing " (23 chars).
        assert keystroke.total_backspaces == 23
        # Trigger fire types directly via send_text — no extra Ctrl+V paste,
        # no extra clipboard write (see #23).
        assert keystroke.paste_count == 1
        assert keystroke.typed_texts == ["CONDENSED "]
        assert _set_texts(clipboard) == ["the long verbose thing "]
        # Transform got the previous LastPaste text + the matched prompt.
        assert transform_backend.calls == [
            ("the long verbose thing ", SUMMARIZE_PROMPT)
        ]

    def test_chained_summarize_summarises_the_summary(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
        clipboard: FakeClipboardIO,
    ) -> None:
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)

        # First "summarize" → "short"
        backend._result = "summarize"
        transform_backend.queue_result("short")
        _cycle(core, start_ms=2_000, end_ms=3_000)

        first_backspaces = keystroke.total_backspaces
        # "the verbose text" → 17 chars after normalise
        assert first_backspaces == 17

        # Second "summarize" should run on "short " (6 chars after normalise)
        # and produce "tinier".
        backend._result = "summarize"
        transform_backend.queue_result("tinier")
        _cycle(core, start_ms=4_000, end_ms=5_000)

        second_backspaces = keystroke.total_backspaces - first_backspaces
        assert second_backspaces == 6
        assert keystroke.typed_texts == ["short ", "tinier "]
        # Second transform fed the post-first-trigger LastPaste text.
        assert transform_backend.calls == [
            ("the verbose text ", SUMMARIZE_PROMPT),
            ("short ", SUMMARIZE_PROMPT),
        ]
        # Only the first dictation went through the clipboard+Ctrl+V path.
        assert keystroke.paste_count == 1
        assert _set_texts(clipboard) == ["the verbose text "]

    def test_alias_variant_summarise_fires(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        backend._result = "hello"
        _cycle(core, start_ms=0, end_ms=1_000)

        backend._result = "Summarise."
        transform_backend.queue_result("brief")
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert transform_backend.calls[-1][1] == SUMMARIZE_PROMPT


# ── Negative paths: trigger does NOT fire ────────────────────────────


class TestTriggerDoesNotFire:
    def test_no_prior_last_paste(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
        clipboard: FakeClipboardIO,
    ) -> None:
        """First-ever utterance of 'summarize' is just regular dictation."""
        backend._result = "summarize"
        _cycle(core, start_ms=0, end_ms=1_000)

        assert keystroke.total_backspaces == 0
        assert keystroke.paste_count == 1
        assert _set_texts(clipboard) == ["summarize "]
        assert transform_backend.calls == []  # no Ollama call

    def test_multi_token_utterance_is_dictation(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
        clipboard: FakeClipboardIO,
    ) -> None:
        # Prime LastPaste.
        backend._result = "hello"
        _cycle(core, start_ms=0, end_ms=1_000)

        # Multi-token "summarize this" — must NOT trigger.
        backend._result = "summarize this"
        _cycle(core, start_ms=2_000, end_ms=3_000)

        assert keystroke.total_backspaces == 0
        assert transform_backend.calls == []
        # And LastPaste is updated to the new dictation.
        last = core._last_paste
        assert last is not None
        assert last.text == "summarize this "

    def test_kill_switch_disables_detection(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        transform_lifecycle: TransformLifecycle,
        trigger_detector: TriggerDetector,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        """With ``transform_enabled=False``, 'summarize' is pasted verbatim."""
        disabled_core = DaemonCore(
            state_machine=sm,
            audio_capture=audio,
            lifecycle=lifecycle,
            overlay=overlay,
            tray=tray,
            clipboard=clipboard,
            keystroke=keystroke,
            foreground=foreground,
            transform_lifecycle=transform_lifecycle,
            trigger_detector=trigger_detector,
            transform_enabled=False,
        )
        backend._result = "hello"
        _cycle(disabled_core, start_ms=0, end_ms=1_000)
        backend._result = "summarize"
        _cycle(disabled_core, start_ms=2_000, end_ms=3_000)

        assert keystroke.total_backspaces == 0
        assert transform_backend.calls == []
        assert _set_texts(clipboard)[-1] == "summarize "


# ── Safety rails ─────────────────────────────────────────────────────


class TestRailsAbort:
    def test_target_id_change_aborts_trigger(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        overlay: FakeOverlayRenderer,
    ) -> None:
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)

        # User alt-tabs; focus is now a different window.
        foreground._target_id = 999

        backend._result = "summarize"
        transform_backend.queue_result("should not be used")
        _cycle(core, start_ms=2_000, end_ms=3_000)

        # No transform call; no backspaces; no second paste.
        assert transform_backend.calls == []
        assert keystroke.total_backspaces == 0
        assert keystroke.paste_count == 1
        # Error path on the overlay (FLASH_ERROR via EMPTY_RESULT).
        assert any(c[0] == "show_error" for c in overlay.calls)

    def test_ttl_expired_aborts_trigger(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
    ) -> None:
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)

        # 5 minutes + 1 ms later (TTL is 300 s = 300_000 ms).
        backend._result = "summarize"
        transform_backend.queue_result("never used")
        _cycle(core, start_ms=300_500, end_ms=301_500)

        assert transform_backend.calls == []
        assert keystroke.total_backspaces == 0
        assert keystroke.paste_count == 1
        assert any(c[0] == "show_error" for c in overlay.calls)


# ── Transform failure ────────────────────────────────────────────────


class TestTransformFailure:
    def test_ollama_failure_flashes_error_and_leaves_document_untouched(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
        overlay: FakeOverlayRenderer,
    ) -> None:
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)

        backend._result = "summarize"
        transform_backend.queue_error(TransformFailedError("ollama unreachable"))
        _cycle(core, start_ms=2_000, end_ms=3_000)

        # Transform WAS called (and failed).
        assert transform_backend.calls == [
            ("the verbose text ", SUMMARIZE_PROMPT)
        ]
        # But no backspaces, no second paste.
        assert keystroke.total_backspaces == 0
        assert keystroke.paste_count == 1
        # Overlay flashed an error.
        assert any(c[0] == "show_error" for c in overlay.calls)


# ── Actionable failure messaging (#37) ───────────────────────────────


def _make_core(
    *,
    sm: StateMachine,
    audio: FakeAudioCapture,
    lifecycle: TranscribeLifecycle,
    overlay: FakeOverlayRenderer,
    tray: FakeTrayRenderer,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    foreground: FakeForegroundTracker,
    transform_lifecycle: TransformLifecycle,
    trigger_detector: TriggerDetector,
    model_name: str = "gemma4:e4b",
    base_url: str = "http://localhost:11434",
) -> DaemonCore:
    return DaemonCore(
        state_machine=sm,
        audio_capture=audio,
        lifecycle=lifecycle,
        overlay=overlay,
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=foreground,
        transform_lifecycle=transform_lifecycle,
        trigger_detector=trigger_detector,
        transform_enabled=True,
        last_paste_ttl_s=300.0,
        transform_model_name=model_name,
        transform_base_url=base_url,
    )


class TestActionableFailureMessaging:
    def _run_failure(
        self,
        *,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        failure: OllamaFailure | None,
    ) -> None:
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = "summarize"
        transform_backend.queue_error(
            TransformFailedError("boom", failure=failure)
        )
        _cycle(core, start_ms=2_000, end_ms=3_000)

    def test_unreachable_message_points_to_readme(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        transform_lifecycle: TransformLifecycle,
        trigger_detector: TriggerDetector,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        core = _make_core(
            sm=sm, audio=audio, lifecycle=lifecycle, overlay=overlay, tray=tray,
            clipboard=clipboard, keystroke=keystroke, foreground=foreground,
            transform_lifecycle=transform_lifecycle,
            trigger_detector=trigger_detector,
        )
        self._run_failure(
            core=core, backend=backend, transform_backend=transform_backend,
            failure=OllamaFailure.connection_refused(),
        )

        assert tray.notifications, "expected a tray notification"
        _title, message = tray.notifications[-1]
        assert "README" in message
        # Document untouched + overlay flashed.
        assert keystroke.total_backspaces == 0
        assert any(c[0] == "show_error" for c in overlay.calls)

    def test_not_running_message_mentions_running(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        transform_lifecycle: TransformLifecycle,
        trigger_detector: TriggerDetector,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        core = _make_core(
            sm=sm, audio=audio, lifecycle=lifecycle, overlay=overlay, tray=tray,
            clipboard=clipboard, keystroke=keystroke, foreground=foreground,
            transform_lifecycle=transform_lifecycle,
            trigger_detector=trigger_detector,
        )
        self._run_failure(
            core=core, backend=backend, transform_backend=transform_backend,
            failure=OllamaFailure.connection_refused(),
        )

        _title, message = tray.notifications[-1]
        lowered = message.lower()
        assert "running" in lowered and "ollama" in lowered

    def test_model_missing_message_names_model_and_pull(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        transform_lifecycle: TransformLifecycle,
        trigger_detector: TriggerDetector,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        core = _make_core(
            sm=sm, audio=audio, lifecycle=lifecycle, overlay=overlay, tray=tray,
            clipboard=clipboard, keystroke=keystroke, foreground=foreground,
            transform_lifecycle=transform_lifecycle,
            trigger_detector=trigger_detector,
            model_name="llama3.2:1b",
        )
        self._run_failure(
            core=core, backend=backend, transform_backend=transform_backend,
            failure=OllamaFailure.http_status(404),
        )

        _title, message = tray.notifications[-1]
        assert "llama3.2:1b" in message
        assert "ollama pull llama3.2:1b" in message

    def test_http_500_surfaces_server_error_pointing_to_readme(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        transform_lifecycle: TransformLifecycle,
        trigger_detector: TriggerDetector,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        # A crashed llama-server (HTTP 500) must not read as a bare
        # "Transform failed" — it gets its own title and points at the README
        # multi-GPU troubleshooting entry (#103).
        core = _make_core(
            sm=sm, audio=audio, lifecycle=lifecycle, overlay=overlay, tray=tray,
            clipboard=clipboard, keystroke=keystroke, foreground=foreground,
            transform_lifecycle=transform_lifecycle,
            trigger_detector=trigger_detector,
        )
        self._run_failure(
            core=core, backend=backend, transform_backend=transform_backend,
            failure=OllamaFailure.http_status(500),
        )

        assert tray.notifications, "expected a tray notification"
        title, message = tray.notifications[-1]
        assert title == "Ollama Server Error"
        assert "500" in message
        assert "README" in message
        # Document untouched + overlay flashed.
        assert keystroke.total_backspaces == 0
        assert any(c[0] == "show_error" for c in overlay.calls)

    def test_failure_without_structured_signal_still_notifies(
        self,
        sm: StateMachine,
        audio: FakeAudioCapture,
        lifecycle: TranscribeLifecycle,
        overlay: FakeOverlayRenderer,
        tray: FakeTrayRenderer,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        foreground: FakeForegroundTracker,
        transform_lifecycle: TransformLifecycle,
        trigger_detector: TriggerDetector,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        """A bare TransformFailedError (failure=None) must not crash and
        should still surface a non-empty message."""
        core = _make_core(
            sm=sm, audio=audio, lifecycle=lifecycle, overlay=overlay, tray=tray,
            clipboard=clipboard, keystroke=keystroke, foreground=foreground,
            transform_lifecycle=transform_lifecycle,
            trigger_detector=trigger_detector,
        )
        self._run_failure(
            core=core, backend=backend, transform_backend=transform_backend,
            failure=None,
        )

        assert tray.notifications, "expected a tray notification"
        _title, message = tray.notifications[-1]
        assert message.strip() != ""
        assert any(c[0] == "show_error" for c in overlay.calls)


# ── Cancel during transform ──────────────────────────────────────────


class TestCancelDuringTransform:
    def test_esc_between_transcription_and_transform_discards_result(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
        keystroke: FakeKeystrokeSender,
        sm: StateMachine,
    ) -> None:
        # Prime LastPaste.
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)

        # Drive the "summarize" cycle but pause between trigger detection
        # and transform completion so ESC can interrupt cleanly.
        backend._result = "summarize"
        transform_backend.queue_result("not pasted")
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=2_000)
        core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=2_200)
        core.on_hotkey_event(Event.KEY_UP, now_ms=3_000)

        # Drain transcription (this also kicks off the transform thread).
        if core._transcription_thread is not None:
            core._transcription_thread.join(timeout=5.0)
        core.check_transcription_result(now_ms=3_000)

        # ESC during transform; SM is still in TRANSCRIBING.
        assert sm.state is State.TRANSCRIBING
        core.on_hotkey_event(Event.ESC, now_ms=3_100)

        assert core._last_paste is None
        assert sm.state is State.IDLE

        # Now let the transform worker actually finish; result must be discarded.
        if core._transform_thread is not None:
            core._transform_thread.join(timeout=5.0)
        core.check_transform_result(now_ms=3_200)

        # Only the first dictation pasted; no follow-up.
        assert keystroke.paste_count == 1
        assert keystroke.total_backspaces == 0
