"""Tests for the pure overlay state machine (no Qt, no PySide6)."""

from __future__ import annotations

import importlib
import sys

import pytest

from dictatem.overlay.state import (
    MonitorRect,
    OverlayPhase,
    OverlayState,
    PillColor,
    Point,
    WaveformFrame,
)
from dictatem.types import RecordingMode


class FakeClock:
    """Deterministic clock for testing time-dependent transitions."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance_ms(self, ms: float) -> None:
        self._now += ms / 1000.0


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def state(clock: FakeClock) -> OverlayState:
    return OverlayState(clock=clock)


class TestInitialState:
    def test_starts_hidden(self, state: OverlayState) -> None:
        assert state.phase == OverlayPhase.HIDDEN

    def test_initial_opacity_is_zero(self, state: OverlayState) -> None:
        assert state.current_opacity() == 0.0


class TestFadeIn:
    def test_show_recording_transitions_to_fading_in(
        self, state: OverlayState
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        assert state.phase == OverlayPhase.FADING_IN

    def test_opacity_at_halfway_through_fade_in(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(50)
        assert state.current_opacity() == pytest.approx(0.5, abs=0.05)

    def test_opacity_one_after_full_fade_in(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        assert state.current_opacity() == 1.0

    def test_phase_is_recording_after_full_fade_in(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        assert state.phase == OverlayPhase.RECORDING


class TestPillColor:
    """Recording phase is encoded by pill COLOUR, not a dot (#96 / ADR-0026).

    The Status Dot is retired; ``current_color()`` is the phase→colour mapping
    the Qt widget renders (the exact hues are an implementer call).
    """

    def test_accent_during_recording(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        assert state.current_color() == PillColor.ACCENT

    def test_accent_during_fade_in(self, state: OverlayState) -> None:
        state.show_recording(RecordingMode.PTT)
        assert state.current_color() == PillColor.ACCENT

    def test_processing_during_transcribing(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.show_transcribing()
        assert state.current_color() == PillColor.PROCESSING

    def test_computing_is_distinct_from_transcribing(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        # A Transform computing reads as a DISTINCT colour from transcribing
        # (#96): both are "processing" phases but the user gets different hues.
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.show_computing()
        assert state.current_color() == PillColor.COMPUTING
        assert PillColor.COMPUTING != PillColor.PROCESSING

    def test_error_colour_during_error_flash(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.flash_error()
        assert state.current_color() == PillColor.ERROR


class TestNoDotApi:
    """The retired Status Dot's API is gone (#96 / ADR-0026)."""

    def test_dot_color_method_removed(self, state: OverlayState) -> None:
        assert not hasattr(state, "current_dot_color")

    def test_dot_style_method_removed(self, state: OverlayState) -> None:
        assert not hasattr(state, "current_dot_style")


class TestComputing:
    """show_computing() drives the Transform/Trigger-Fire 'computing' phase.

    A warm LLM generating is a tinted processing indicator by COLOUR (ADR-0026)
    — not the old 'LLM Model Computing' text caption (which was a LOADING state).
    """

    def test_show_computing_enters_computing_phase(self, state: OverlayState) -> None:
        state.show_computing()
        assert state.phase == OverlayPhase.COMPUTING

    def test_opacity_one_during_computing(self, state: OverlayState) -> None:
        state.show_computing()
        assert state.current_opacity() == 1.0

    def test_computing_is_held_across_ticks(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        # Like LOADING/TRANSCRIBING, COMPUTING never auto-transitions: the daemon
        # hides it once the Transform result lands.
        state.show_computing()
        clock.advance_ms(5000)
        state.tick()
        assert state.phase == OverlayPhase.COMPUTING

    def test_hide_leaves_computing(self, state: OverlayState) -> None:
        state.show_computing()
        state.hide()
        assert state.phase == OverlayPhase.FADING_OUT


class TestWaveformFrame:
    def test_half_level_produces_half_height_bars(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        frame = state.current_waveform_frame(lambda: 0.5)
        assert isinstance(frame, WaveformFrame)
        assert len(frame.bars) > 0
        avg_height = sum(frame.bars) / len(frame.bars)
        assert 0.2 < avg_height < 0.8

    def test_energy_proportional_to_level(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        frame_low = state.current_waveform_frame(lambda: 0.25)
        frame_high = state.current_waveform_frame(lambda: 0.75)
        energy_low = sum(frame_low.bars)
        energy_high = sum(frame_high.bars)
        assert energy_high / energy_low == pytest.approx(3.0, rel=0.1)

    def test_zero_level_produces_zero_bars(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        frame = state.current_waveform_frame(lambda: 0.0)
        assert all(b == 0.0 for b in frame.bars)

    def test_full_level_produces_max_bars(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        frame = state.current_waveform_frame(lambda: 1.0)
        assert all(b > 0.0 for b in frame.bars)
        assert max(frame.bars) == pytest.approx(1.0, abs=0.01)


class TestComputePosition:
    def test_cursor_on_second_monitor(self) -> None:
        monitors = [
            MonitorRect(0, 0, 1920, 1080),
            MonitorRect(1920, 0, 1920, 1080),
        ]
        pos = OverlayState.compute_position(
            cursor_position=Point(2500, 800), monitors=monitors
        )
        # Should be in the second monitor's bottom-right region
        assert 1920 < pos.x < 1920 + 1920
        assert 0 < pos.y < 1080
        # Specifically in the right half and bottom half of the second monitor
        assert pos.x > 1920 + 960
        assert pos.y > 540

    def test_cursor_on_first_monitor(self) -> None:
        monitors = [
            MonitorRect(0, 0, 1920, 1080),
            MonitorRect(1920, 0, 1920, 1080),
        ]
        pos = OverlayState.compute_position(
            cursor_position=Point(500, 500), monitors=monitors
        )
        assert 0 < pos.x < 1920
        assert 0 < pos.y < 1080
        assert pos.x > 960
        assert pos.y > 540

    def test_fallback_to_first_monitor(self) -> None:
        monitors = [MonitorRect(0, 0, 1920, 1080)]
        pos = OverlayState.compute_position(
            cursor_position=Point(5000, 5000), monitors=monitors
        )
        assert 0 < pos.x < 1920
        assert 0 < pos.y < 1080


class TestFadeOut:
    def test_hide_transitions_to_fading_out(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.hide()
        assert state.phase == OverlayPhase.FADING_OUT

    def test_opacity_decreases_during_fade_out(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.hide()
        clock.advance_ms(200)
        opacity = state.current_opacity()
        assert 0.0 < opacity < 1.0

    def test_hidden_after_full_fade_out(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.hide()
        clock.advance_ms(400)
        state.tick()
        assert state.phase == OverlayPhase.HIDDEN
        assert state.current_opacity() == 0.0


class TestTranscribing:
    def test_show_transcribing_transitions_from_recording(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.show_transcribing()
        assert state.phase == OverlayPhase.TRANSCRIBING

    def test_opacity_stays_one_during_transcribing(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.show_transcribing()
        assert state.current_opacity() == 1.0


class TestLoading:
    """show_loading() drives the animated "Model Loading" pill (#74)."""

    def test_show_loading_enters_loading_phase(self, state: OverlayState) -> None:
        state.show_loading()
        assert state.phase == OverlayPhase.LOADING

    def test_opacity_one_during_loading(self, state: OverlayState) -> None:
        state.show_loading()
        assert state.current_opacity() == 1.0

    def test_loading_is_held_across_ticks(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        # Unlike the fade/flash phases, LOADING never auto-transitions: the
        # daemon flips it to transcribing or hides it once the load resolves.
        state.show_loading()
        clock.advance_ms(5000)
        state.tick()
        assert state.phase == OverlayPhase.LOADING

    def test_dots_cycle_one_two_three(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_loading()
        assert state.current_loading_text() == "Model Loading."
        clock.advance_ms(400)
        assert state.current_loading_text() == "Model Loading.."
        clock.advance_ms(400)
        assert state.current_loading_text() == "Model Loading..."
        clock.advance_ms(400)
        assert state.current_loading_text() == "Model Loading."  # wraps to one

    def test_custom_label_is_used(self, state: OverlayState) -> None:
        state.show_loading("Loading LLM Model")
        assert state.current_loading_text() == "Loading LLM Model."

    def test_show_transcribing_leaves_loading(self, state: OverlayState) -> None:
        state.show_loading()
        state.show_transcribing()
        assert state.phase == OverlayPhase.TRANSCRIBING

    def test_hide_leaves_loading(self, state: OverlayState) -> None:
        state.show_loading()
        state.hide()
        assert state.phase == OverlayPhase.FADING_OUT


class TestFlashError:
    """flash_error() → ERROR_FLASH for ~300ms → FADING_OUT → HIDDEN."""

    def test_flash_error_transitions_to_error_flash(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.flash_error()
        assert state.phase == OverlayPhase.ERROR_FLASH

    def test_opacity_one_during_error_flash(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.flash_error()
        assert state.current_opacity() == 1.0

    def test_still_error_flash_before_300ms(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.flash_error()
        clock.advance_ms(299)
        state.tick()
        assert state.phase == OverlayPhase.ERROR_FLASH

    def test_fading_out_after_300ms(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.flash_error()
        clock.advance_ms(300)
        state.tick()
        assert state.phase == OverlayPhase.FADING_OUT

    def test_hidden_after_full_flash_and_fade(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.show_recording(RecordingMode.PTT)
        clock.advance_ms(100)
        state.tick()
        state.flash_error()
        clock.advance_ms(300)
        state.tick()
        assert state.phase == OverlayPhase.FADING_OUT
        clock.advance_ms(400)
        state.tick()
        assert state.phase == OverlayPhase.HIDDEN
        assert state.current_opacity() == 0.0

    def test_flash_error_from_hidden_still_works(
        self, state: OverlayState, clock: FakeClock
    ) -> None:
        state.flash_error()
        assert state.phase == OverlayPhase.ERROR_FLASH
        clock.advance_ms(300)
        state.tick()
        assert state.phase == OverlayPhase.FADING_OUT


class TestImportSafety:
    def test_overlay_state_has_no_pyside6_imports(self) -> None:
        before = set(sys.modules.keys())
        importlib.import_module("dictatem.overlay.state")
        after = set(sys.modules.keys())
        new_modules = after - before
        for forbidden in ("PySide6", "shiboken6"):
            violations = [
                m
                for m in new_modules
                if m == forbidden or m.startswith(forbidden + ".")
            ]
            assert violations == [], (
                f"overlay.state pulled in forbidden module(s): {violations}"
            )
