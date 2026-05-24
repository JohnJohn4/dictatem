"""Pure, clock-injected monitor of transcription real-time factor.

Tracks a rolling window of real-time factors (wall_time / audio_duration)
over recent transcriptions. When the window is consistently poor it fires a
single, one-shot "transcriptions are slow" tip and then latches — never
firing again for the rest of the session.

This follows ADR-0007's philosophy of *rare, earned advice* rather than
repeated warnings: the tip is offered at most once, only after the slowness
is demonstrably consistent, never as a nag.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class LatencyMonitor:
    """Rolling real-time-factor watcher that fires one slowness tip per session."""

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        rtf_threshold: float = 1.5,
        window: int = 3,
    ) -> None:
        self._clock = clock
        self._rtf_threshold = rtf_threshold
        self._window = window
        self._rtfs: deque[float] = deque(maxlen=window)
        self._start: float = 0.0
        self._fired = False

    def begin(self) -> None:
        """Record clock() as the start of a transcription."""
        self._start = self._clock()

    def end(self, audio_duration_s: float) -> bool:
        """Close a transcription and update the rolling window.

        Returns True EXACTLY ONCE — the first time the window is full and
        every real-time factor in it is at or above ``rtf_threshold`` — then
        latches so it never returns True again this session.
        """
        if audio_duration_s <= 0:
            # No usable signal — ignore the sample to avoid div-by-zero.
            return False

        wall = self._clock() - self._start
        rtf = wall / audio_duration_s
        self._rtfs.append(rtf)

        if self._fired:
            return False
        if len(self._rtfs) < self._window:
            return False
        if all(r >= self._rtf_threshold for r in self._rtfs):
            self._fired = True
            return True
        return False
