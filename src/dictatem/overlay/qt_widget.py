"""PySide6 overlay widget — Windows manual QA only.

This module intentionally imports PySide6 and must never be imported on Linux
or in the test suite.  It is the thin rendering adapter that subscribes to
:class:`~dictatem.overlay.state.OverlayState` and paints the pill.
"""

from __future__ import annotations

import math
import sys
from typing import TYPE_CHECKING

from dictatem.overlay.state import (
    PILL_HEIGHT,
    PILL_WIDTH,
    OverlayPhase,
    PillColor,
    Point,
)

if TYPE_CHECKING:
    from dictatem.overlay.state import OverlayState

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from dictatem.overlay.state import MonitorRect

# Semantic PillColor → actual hue (the implementer call ADR-0026 leaves open).
# Distinct hues for transcribing vs computing so the two processing phases read
# differently. Built once at import (QColor needs no QApplication) rather than
# per paintEvent — the pill repaints at 30 FPS while visible.
_PHASE_HUES = {
    PillColor.ACCENT: QColor(255, 255, 255, 195),  # recording — white (motion is the cue)
    PillColor.PROCESSING: QColor(255, 191, 0),  # transcribing — amber
    PillColor.COMPUTING: QColor(170, 130, 255),  # computing — violet
    PillColor.ERROR: QColor(235, 80, 80),  # error / "saved" flash — red
}


class QtOverlayWidget(QWidget):
    """Frameless, always-on-top, click-through recording pill."""

    _FPS = 30

    def __init__(self, overlay_state: OverlayState) -> None:
        super().__init__(None)
        self._state = overlay_state
        self._last_level: float = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            # Never take keyboard focus / activation when shown (#163). Without
            # this, *showing* the pill at record-start could momentarily steal
            # activation from the user's window — a plausible cause of the
            # "caret deactivates while talking" drift (ADR-0026 consequence).
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Show without activating, so raising the pill never deactivates the
        # user's foreground window or caret (#163). Pairs with the no-focus flag
        # above and with the detect-and-hold paste guard (#97): the overlay can
        # stay purely informational only because it never grabs activation.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        if sys.platform == "darwin":
            # A Qt.Tool window is hidden whenever its app is not frontmost, and
            # our daemon is a menu-bar accessory that never is — so on macOS the
            # pill never appeared in QA (#56). This attribute keeps tool windows
            # visible across app deactivation; it is a no-op on other platforms.
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setFixedSize(PILL_WIDTH, PILL_HEIGHT)

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // self._FPS)
        self._timer.timeout.connect(self._on_tick)

    def update_level(self, level: float) -> None:
        # Scale raw RMS (typically 0.01–0.1 for speech) into a visible display range.
        # sqrt gives a perceptually natural response; *5 lifts quiet speech to ~50%.
        self._last_level = min(1.0, math.sqrt(level) * 5.0) if level > 0.0 else 0.0

    def show_pill(self) -> None:
        cursor = QCursor.pos()
        # availableGeometry() is the screen rect MINUS the taskbar/docks, so the
        # bottom-right resting position computed by compute_position clears the
        # taskbar instead of overlapping it. Adapts to any taskbar height/edge
        # (and to auto-hide, where the work area is the full screen).
        monitors = [
            MonitorRect(
                g.x(), g.y(), g.width(), g.height(),
            )
            for s in QApplication.screens()
            for g in (s.availableGeometry(),)
        ]
        pos = self._state.compute_position(
            cursor_position=Point(cursor.x(), cursor.y()),
            monitors=monitors,
        )
        self.move(pos.x, pos.y)
        self.show()
        self._timer.start()

    def hide_pill(self) -> None:
        self._timer.stop()
        self.hide()

    def _on_tick(self) -> None:
        self._state.tick()
        if self._state.phase == OverlayPhase.HIDDEN:
            self.hide_pill()
            return
        self.setWindowOpacity(self._state.current_opacity())
        self.update()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QColor(30, 30, 30, 220))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 8, 8)

        # While a model loads, the pill is a single animated caption — no dot or
        # waveform (there is no recording yet to visualise).
        if self._state.phase == OverlayPhase.LOADING:
            painter.setPen(QColor(235, 235, 235, 235))
            font = painter.font()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(14, 0, -10, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._state.current_loading_text(),
            )
            painter.end()
            return

        # Phase by COLOUR (#96 / ADR-0026): the waveform itself is drawn in the
        # phase's colour — accent while recording, a distinct processing hue while
        # transcribing, a distinct hue while a Transform computes, the error hue on
        # the error / focus-drift "saved" flash. The Status Dot is gone. Only
        # RECORDING tracks the live mic level; the other phases show a low static
        # waveform that reads as "still working" in the phase colour.
        col = _PHASE_HUES[self._state.current_color()]
        live = self._state.phase in (OverlayPhase.RECORDING, OverlayPhase.FADING_IN)
        level = self._last_level if live else 0.3
        frame = self._state.current_waveform_frame(lambda: level)
        bar_w = 4
        bar_count = len(frame.bars)
        bar_area_x = 14
        bar_area_w = PILL_WIDTH - bar_area_x - 12
        spacing = (bar_area_w - bar_count * bar_w) / max(1, bar_count - 1)
        center_y = PILL_HEIGHT // 2
        max_h = PILL_HEIGHT - 12
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(col)
        for i, bar_val in enumerate(frame.bars):
            bar_h = max(3, int(bar_val * max_h))
            bx = int(bar_area_x + i * (bar_w + spacing))
            by = center_y - bar_h // 2
            painter.drawRoundedRect(bx, by, bar_w, bar_h, bar_w // 2, bar_w // 2)

        painter.end()
