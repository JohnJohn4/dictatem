"""Pure overlay state machine — stdlib only, no Qt/PySide6."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

from dictatem.types import RecordingMode


class OverlayPhase(enum.Enum):
    HIDDEN = "hidden"
    FADING_IN = "fading_in"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    ERROR_FLASH = "error_flash"
    FADING_OUT = "fading_out"


class Color(enum.Enum):
    RED = "red"
    AMBER = "amber"


class DotStyle(enum.Enum):
    OUTLINE = "outline"
    FILLED = "filled"


class Point(NamedTuple):
    x: int
    y: int


class MonitorRect(NamedTuple):
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class WaveformFrame:
    bars: tuple[float, ...]


_BAR_WEIGHTS: tuple[float, ...] = (0.5, 0.7, 0.9, 1.0, 0.85, 0.95, 1.0, 0.8, 0.65, 0.5)

PILL_WIDTH: int = 200
PILL_HEIGHT: int = 40
PILL_MARGIN: int = 16


class OverlayState:
    """Pure state machine for the recording overlay pill.

    All time-dependent behaviour is driven by an injected clock callable
    that returns the current time in seconds.
    """

    def __init__(
        self,
        clock: Callable[[], float],
        fade_in_ms: int = 100,
        fade_out_ms: int = 400,
        bar_count: int = 10,
    ) -> None:
        self._clock = clock
        self._fade_in_s = fade_in_ms / 1000.0
        self._fade_out_s = fade_out_ms / 1000.0
        self._bar_weights = _BAR_WEIGHTS[:bar_count]
        self._flash_duration_s = 0.300
        self._phase = OverlayPhase.HIDDEN
        self._mode: RecordingMode | None = None
        self._transition_start: float = 0.0

    @property
    def phase(self) -> OverlayPhase:
        return self._phase

    def show_recording(self, mode: RecordingMode) -> None:
        self._mode = mode
        self._phase = OverlayPhase.FADING_IN
        self._transition_start = self._clock()

    def show_transcribing(self) -> None:
        self._phase = OverlayPhase.TRANSCRIBING

    def flash_error(self) -> None:
        self._phase = OverlayPhase.ERROR_FLASH
        self._transition_start = self._clock()

    def hide(self) -> None:
        self._phase = OverlayPhase.FADING_OUT
        self._transition_start = self._clock()

    def tick(self) -> None:
        now = self._clock()
        if self._phase == OverlayPhase.FADING_IN:
            if now - self._transition_start >= self._fade_in_s:
                self._phase = OverlayPhase.RECORDING
        elif self._phase == OverlayPhase.ERROR_FLASH:
            if now - self._transition_start >= self._flash_duration_s:
                self._phase = OverlayPhase.FADING_OUT
                self._transition_start = now
        elif (
            self._phase == OverlayPhase.FADING_OUT
            and now - self._transition_start >= self._fade_out_s
        ):
            self._phase = OverlayPhase.HIDDEN

    def current_opacity(self) -> float:
        if self._phase == OverlayPhase.HIDDEN:
            return 0.0
        if self._phase == OverlayPhase.FADING_IN:
            elapsed = self._clock() - self._transition_start
            return min(elapsed / self._fade_in_s, 1.0)
        if self._phase in (OverlayPhase.RECORDING, OverlayPhase.TRANSCRIBING, OverlayPhase.ERROR_FLASH):
            return 1.0
        if self._phase == OverlayPhase.FADING_OUT:
            elapsed = self._clock() - self._transition_start
            t = min(elapsed / self._fade_out_s, 1.0)
            return (1.0 - t) ** 2  # ease-out
        return 0.0

    def current_dot_color(self) -> Color:
        if self._phase == OverlayPhase.TRANSCRIBING:
            return Color.AMBER
        return Color.RED

    def current_dot_style(self) -> DotStyle:
        if self._mode == RecordingMode.PTT:
            return DotStyle.OUTLINE
        return DotStyle.FILLED

    def current_waveform_frame(self, level_supplier: Callable[[], float]) -> WaveformFrame:
        level = max(0.0, min(1.0, level_supplier()))
        bars = tuple(w * level for w in self._bar_weights)
        return WaveformFrame(bars=bars)

    @staticmethod
    def compute_position(
        cursor_position: Point,
        monitors: list[MonitorRect],
    ) -> Point:
        target = monitors[0]
        for mon in monitors:
            if (
                mon.x <= cursor_position.x < mon.x + mon.width
                and mon.y <= cursor_position.y < mon.y + mon.height
            ):
                target = mon
                break
        return Point(
            target.x + target.width - PILL_WIDTH - PILL_MARGIN,
            target.y + target.height - PILL_HEIGHT - PILL_MARGIN,
        )
