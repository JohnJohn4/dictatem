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
    LOADING = "loading"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    COMPUTING = "computing"
    ERROR_FLASH = "error_flash"
    FADING_OUT = "fading_out"


class PillColor(enum.Enum):
    """The pill's phase-by-colour signal (#96 / ADR-0026).

    Replaces the retired Status Dot: recording phase is carried by the pill's
    colour rather than a separate dot. The names are semantic; the Qt widget
    maps each to an actual hue (an implementer call — see ``overlay.qt_widget``).
    """

    ACCENT = "accent"  # recording: the live waveform's colour
    PROCESSING = "processing"  # transcribing
    COMPUTING = "computing"  # a Transform/Trigger Fire generating (distinct hue)
    ERROR = "error"  # the error / focus-drift "saved" flash


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

# How long each dot in the "Model Loading" animation holds before the next
# appears; the count cycles 1 -> 2 -> 3 -> 1 so the pill reads as live.
LOADING_DOT_INTERVAL_S: float = 0.4


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
        # The current phase colour (#96). Set on each show_*/flash transition and
        # held through the following fade-out, so the pill fades the colour it was
        # last showing rather than snapping to a default.
        self._color: PillColor = PillColor.ACCENT
        self._transition_start: float = 0.0
        self._loading_label: str = "Model Loading"
        self._loading_start: float = 0.0

    @property
    def phase(self) -> OverlayPhase:
        return self._phase

    def show_recording(self, mode: RecordingMode) -> None:
        # ``mode`` (Tap vs Hold) no longer drives a visible cue: the Status Dot
        # is retired and its Tap/Hold style is dropped — the user knows the
        # gesture they just made (#96 / ADR-0026). The parameter is kept so the
        # OverlayRenderer contract still distinguishes the two record entrypoints.
        self._color = PillColor.ACCENT
        self._phase = OverlayPhase.FADING_IN
        self._transition_start = self._clock()

    def show_transcribing(self) -> None:
        self._color = PillColor.PROCESSING
        self._phase = OverlayPhase.TRANSCRIBING

    def show_computing(self) -> None:
        """The pill while a Transform/Trigger Fire generates (#96 / ADR-0026).

        A warm LLM generating is a tinted processing indicator by COLOUR, held
        until the daemon hides it — distinct from a model *load* (still the text
        caption via :meth:`show_loading`) and from transcribing (a distinct hue).
        """
        self._color = PillColor.COMPUTING
        self._phase = OverlayPhase.COMPUTING

    def show_loading(self, label: str = "Model Loading") -> None:
        self._loading_label = label
        self._phase = OverlayPhase.LOADING
        self._loading_start = self._clock()

    def current_loading_text(self) -> str:
        """The pill caption while a model loads, with dots cycling 1->2->3->1 so
        it reads as live progress rather than a frozen string."""
        elapsed = max(0.0, self._clock() - self._loading_start)
        dots = int(elapsed / LOADING_DOT_INTERVAL_S) % 3 + 1
        return f"{self._loading_label}{'.' * dots}"

    def flash_error(self) -> None:
        self._color = PillColor.ERROR
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
        if self._phase in (
            OverlayPhase.LOADING,
            OverlayPhase.RECORDING,
            OverlayPhase.TRANSCRIBING,
            OverlayPhase.COMPUTING,
            OverlayPhase.ERROR_FLASH,
        ):
            return 1.0
        if self._phase == OverlayPhase.FADING_OUT:
            elapsed = self._clock() - self._transition_start
            t = min(elapsed / self._fade_out_s, 1.0)
            return (1.0 - t) ** 2  # ease-out
        return 0.0

    def current_color(self) -> PillColor:
        """The pill's phase colour — the Status Dot's replacement (#96).

        Carries recording phase: accent while recording, a distinct processing
        hue while transcribing, a distinct hue while a Transform computes, and
        the error/focus-drift flash colour. Held through the fade-out so the pill
        fades the colour it was last showing. While LOADING the pill shows a text
        caption instead (see :meth:`current_loading_text`), so this is unused then.
        """
        return self._color

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
