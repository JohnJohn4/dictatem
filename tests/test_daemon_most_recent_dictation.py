"""Most-recent dictation buffer + tray "Copy last dictation" (ADR-0023 / #119).

Drives the full PTT → transcription → paste pipeline through fakes and asserts
the daemon retains the last *regular* dictation (normalised + Replacements
applied) in a persistent buffer — kept across pastes, never overwritten by a
Trigger Fire — and that the tray copy item routes it to the clipboard as a
NORMAL copy. The buffer/state decision is pure; the win32 copy + Qt item are
manual-QA.
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
def tray() -> FakeTrayRenderer:
    return FakeTrayRenderer()


@pytest.fixture
def transform_backend() -> FakeTransformBackend:
    return FakeTransformBackend()


def _make_core(
    *,
    backend: FakeTranscriberBackend,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    tray: FakeTrayRenderer,
    transform_backend: FakeTransformBackend,
    replacements: list[Replacement] | None = None,
    transform_enabled: bool = True,
) -> DaemonCore:
    return DaemonCore(
        state_machine=StateMachine(tap_threshold_ms=200),
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=FakeOverlayRenderer(),
        tray=tray,
        clipboard=clipboard,
        keystroke=keystroke,
        foreground=FakeForegroundTracker(target_id=42),
        transform_lifecycle=TransformLifecycle(backend=transform_backend),
        trigger_detector=TriggerDetector(ALIASES),
        transform_enabled=transform_enabled,
        last_paste_ttl_s=300.0,
        replacements=replacements or [],
    )


@pytest.fixture
def core(
    backend: FakeTranscriberBackend,
    clipboard: FakeClipboardIO,
    keystroke: FakeKeystrokeSender,
    tray: FakeTrayRenderer,
    transform_backend: FakeTransformBackend,
) -> DaemonCore:
    return _make_core(
        backend=backend, clipboard=clipboard, keystroke=keystroke, tray=tray,
        transform_backend=transform_backend,
    )


def _cycle(core: DaemonCore, *, start_ms: int, end_ms: int) -> None:
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=start_ms)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=start_ms + 200)
    core.on_hotkey_event(Event.KEY_UP, now_ms=end_ms)
    core.drain_transcription_for_test(now_ms=end_ms)


def _copies(clipboard: FakeClipboardIO) -> list[str]:
    return [c[1] for c in clipboard.calls if c[0] == "copy"]


class TestBufferRetention:
    def test_regular_dictation_is_retained_normalised(
        self, core: DaemonCore, backend: FakeTranscriberBackend
    ) -> None:
        backend._result = "hello world"
        _cycle(core, start_ms=0, end_ms=1_000)
        # Same normalisation as the paste payload (trailing space).
        assert core._most_recent_dictation == "hello world "

    def test_buffer_survives_subsequent_pastes(
        self, core: DaemonCore, backend: FakeTranscriberBackend
    ) -> None:
        backend._result = "first dictation"
        _cycle(core, start_ms=0, end_ms=1_000)
        # _last_text (the transient pending payload) is nulled after the paste,
        # but the Most-recent dictation buffer survives.
        assert core._last_text is None
        assert core._most_recent_dictation == "first dictation "

    def test_buffer_tracks_the_newest_dictation(
        self, core: DaemonCore, backend: FakeTranscriberBackend
    ) -> None:
        backend._result = "older"
        _cycle(core, start_ms=0, end_ms=1_000)
        backend._result = "newer"
        _cycle(core, start_ms=2_000, end_ms=3_000)
        assert core._most_recent_dictation == "newer "

    def test_buffer_has_replacements_applied(
        self,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
        keystroke: FakeKeystrokeSender,
        tray: FakeTrayRenderer,
        transform_backend: FakeTransformBackend,
    ) -> None:
        core = _make_core(
            backend=backend, clipboard=clipboard, keystroke=keystroke, tray=tray,
            transform_backend=transform_backend,
            replacements=[Replacement(source="teh", target="the")],
        )
        backend._result = "teh cat"
        _cycle(core, start_ms=0, end_ms=1_000)
        # The retained text is the Replacements-applied, normalised form.
        assert core._most_recent_dictation == "the cat "

    def test_buffer_survives_cancel(
        self, core: DaemonCore, backend: FakeTranscriberBackend
    ) -> None:
        backend._result = "keep me"
        _cycle(core, start_ms=0, end_ms=1_000)
        # A later cancelled recording (ESC) must not wipe the recovery buffer.
        core.on_hotkey_event(Event.KEY_DOWN, now_ms=2_000)
        core.on_hotkey_event(Event.ESC, now_ms=2_100)
        assert core._most_recent_dictation == "keep me "


class TestTriggerFireDoesNotOverwriteBuffer:
    def test_summarize_leaves_buffer_as_the_dictation(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        transform_backend: FakeTransformBackend,
    ) -> None:
        # Regular dictation fills the buffer...
        backend._result = "the verbose text"
        _cycle(core, start_ms=0, end_ms=1_000)
        assert core._most_recent_dictation == "the verbose text "

        # ...then a Trigger Fire pastes Transform OUTPUT (typed replacement). The
        # Most-recent dictation must remain the dictation, not the summary, so
        # "paste" recovery still recovers what the user actually said (#139).
        backend._result = "summarize"
        transform_backend.queue_result("CONDENSED")
        _cycle(core, start_ms=2_000, end_ms=3_000)
        assert core._most_recent_dictation == "the verbose text "


class TestTrayHasLastDictationFlag:
    def test_flag_false_before_any_dictation(
        self, core: DaemonCore, tray: FakeTrayRenderer
    ) -> None:
        assert tray.has_last_dictation is False

    def test_flag_set_after_a_dictation(
        self, core: DaemonCore, backend: FakeTranscriberBackend, tray: FakeTrayRenderer
    ) -> None:
        backend._result = "anything"
        _cycle(core, start_ms=0, end_ms=1_000)
        assert tray.has_last_dictation is True

    def test_flag_not_set_by_an_empty_result(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        tray: FakeTrayRenderer,
    ) -> None:
        from dictatem.types import EmptyResult

        backend._result = EmptyResult()
        _cycle(core, start_ms=0, end_ms=1_000)
        assert tray.has_last_dictation is False
        assert core._most_recent_dictation is None


class TestCopyLastDictation:
    def test_copies_buffer_as_a_normal_copy(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
    ) -> None:
        backend._result = "recover me"
        _cycle(core, start_ms=0, end_ms=1_000)

        core.on_tray_copy_last_dictation()

        # Routed through the NORMAL copy path (appears in Win+V), not the
        # clutter-proof transient set_text used for the automatic paste.
        assert _copies(clipboard) == ["recover me "]

    def test_copy_survives_intervening_pastes(
        self,
        core: DaemonCore,
        backend: FakeTranscriberBackend,
        clipboard: FakeClipboardIO,
    ) -> None:
        backend._result = "remembered"
        _cycle(core, start_ms=0, end_ms=1_000)
        # A second, different dictation, then copy — copies the latest.
        backend._result = "latest"
        _cycle(core, start_ms=2_000, end_ms=3_000)
        core.on_tray_copy_last_dictation()
        assert _copies(clipboard) == ["latest "]

    def test_copy_is_noop_with_no_dictation(
        self, core: DaemonCore, clipboard: FakeClipboardIO
    ) -> None:
        core.on_tray_copy_last_dictation()
        assert _copies(clipboard) == []
