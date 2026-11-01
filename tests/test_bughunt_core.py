"""Proving tests for the v0.7.0 bug hunt (docs/reviews/2026-11-02-v0.7.0-bug-hunt.md).

Each test asserts the INTENDED behaviour and is expected to fail on v0.7.0;
they are marked ``xfail(strict=True)`` with the finding they prove, so the fix
for a finding flips its test to XPASS and the strict marker forces its removal.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

from dictatem.config import Config, load_config_with_report, write_config
from dictatem.daemon import DaemonCore, _HotkeyBridge
from dictatem.hotkey.classifier import HotkeyClassifier, Key, KeyAction
from dictatem.state import Event, State, StateMachine
from dictatem.transcribe.lifecycle import TranscribeLifecycle
from tests.fakes import (
    FakeAudioCapture,
    FakeClipboardIO,
    FakeForegroundTracker,
    FakeKeystrokeSender,
    FakeOverlayRenderer,
    FakeTranscriberBackend,
    FakeTrayRenderer,
)

if TYPE_CHECKING:
    from pathlib import Path


# --- Finding M-1: a release between tap_threshold_ms and the next 50 ms tick ---


def _bridge() -> tuple[_HotkeyBridge, StateMachine, list[Event]]:
    sm = StateMachine(tap_threshold_ms=200)
    seen: list[Event] = []

    def _callback(event: Event, *, now_ms: int) -> None:
        seen.append(event)
        sm.handle(event, now_ms=now_ms)

    classifier = HotkeyClassifier(tap_threshold_ms=200, modifiers=("win", "alt"))
    classifier.set_active(True)
    return _HotkeyBridge(classifier=classifier, callback=_callback), sm, seen


@pytest.mark.xfail(
    strict=True,
    reason="bug-hunt M-1: a 200-250 ms press released before the next tick loses "
    "its release; the state machine is stranded in PRESSED with the mic open",
)
def test_release_after_threshold_but_before_tick_still_stops() -> None:
    bridge, sm, seen = _bridge()
    # Ticks every 50 ms, like the production QTimer. Press at t=1000 right
    # after a tick; release at t=1230 — 230 ms, past the 200 ms threshold, but
    # the tick that would have emitted HOLD_START (t=1250) hasn't run yet.
    bridge.tick(1000)
    bridge.enqueue_key_event(Key.LEFT_META, KeyAction.KEY_DOWN, 1000)
    bridge.enqueue_key_event(Key.LEFT_ALT, KeyAction.KEY_DOWN, 1001)
    for t in (1050, 1100, 1150, 1200):
        bridge.tick(t)
    bridge.enqueue_key_event(Key.LEFT_ALT, KeyAction.KEY_UP, 1229)
    bridge.enqueue_key_event(Key.LEFT_META, KeyAction.KEY_UP, 1230)
    for t in (1250, 1300, 5000, 60_000):
        bridge.tick(t)

    assert seen[0] is Event.KEY_DOWN  # recording started
    # Intended: the press is either a tap (TOGGLE_REC) or a hold that ended
    # (TRANSCRIBING). Actual: no KEY_UP ever reaches the state machine.
    assert sm.state is not State.PRESSED


# --- Finding M-2: config rewrite does not escape TOML strings ---


@pytest.mark.xfail(
    strict=True,
    reason="bug-hunt M-2: write_config emits strings unescaped, so a backslash "
    "or quote in a value makes the rewritten config.toml unparseable",
)
@pytest.mark.parametrize(
    "model_name",
    [
        r"C:\models\whisper-large-v3",  # a local model directory (faster-whisper accepts one)
        'my "tuned" model',
    ],
)
def test_rewritten_config_round_trips_string_values(tmp_path: Path, model_name: str) -> None:
    path = tmp_path / "config.toml"
    cfg = Config()
    cfg.model.name = model_name
    # What the tray Start-at-login toggle does: rewrite the loaded config.
    write_config(cfg, path)

    tomllib.loads(path.read_text(encoding="utf-8"))  # must still parse
    reloaded, report = load_config_with_report(path)
    assert report.is_empty
    assert reloaded.model.name == model_name


# --- Finding L-1: the Preload pill's dismissal hides a live recording pill ---


@pytest.mark.xfail(
    strict=True,
    reason="bug-hunt L-1: when a tray/startup Preload finishes mid-recording, "
    "check_loading_overlay hides the overlay under the live recording",
)
def test_preload_completion_does_not_hide_recording_pill() -> None:
    backend = FakeTranscriberBackend(result="hello")
    backend.block_load()
    overlay = FakeOverlayRenderer()
    sm = StateMachine(tap_threshold_ms=200)
    core = DaemonCore(
        state_machine=sm,
        audio_capture=FakeAudioCapture(duration_s=1.0),
        lifecycle=TranscribeLifecycle(backend=backend, clock=lambda: 0.0),
        overlay=overlay,
        tray=FakeTrayRenderer(),
        clipboard=FakeClipboardIO(),
        keystroke=FakeKeystrokeSender(),
        foreground=FakeForegroundTracker(target_id=1),
    )
    core.on_tray_preload()  # [startup].preload_model = true does the same
    # The user starts dictating while the model is still loading.
    core.on_hotkey_event(Event.KEY_DOWN, now_ms=0)
    core.on_hotkey_event(Event.TIMER_EXPIRED, now_ms=200)
    assert sm.state is State.PTT_REC
    assert overlay.state == "recording"

    backend.release_load()
    from tests.support import wait_until

    wait_until(lambda: not core._lifecycle.is_loading)
    core.check_loading_overlay(now_ms=300)

    # Still recording — the pill must still be up.
    assert sm.state is State.PTT_REC
    assert overlay.visible
