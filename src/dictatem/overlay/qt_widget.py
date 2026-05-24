"""PySide6 overlay widget — Windows manual QA only.

This module intentionally imports PySide6 and must never be imported on Linux
or in the test suite.  It is the thin rendering adapter that subscribes to
:class:`~dictatem.overlay.state.OverlayState` and paints the pill.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dictatem.overlay.state import (
    Color,
    DotStyle,
    OverlayPhase,
    PILL_HEIGHT,
    PILL_WIDTH,
    Point,
)

if TYPE_CHECKING:
    from dictatem.overlay.state import OverlayState

from dictatem.overlay.state import MonitorRect

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget


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
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
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

        dot_color = self._state.current_dot_color()
        dot_qcolor = QColor("red") if dot_color == Color.RED else QColor(255, 191, 0)

        if self._state.current_dot_style() == DotStyle.OUTLINE:
            painter.setPen(QPen(dot_qcolor, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_qcolor)
        painter.drawEllipse(8, 10, 20, 20)

        if self._state.phase == OverlayPhase.RECORDING:
            frame = self._state.current_waveform_frame(lambda: self._last_level)
            bar_w = 4
            bar_count = len(frame.bars)
            bar_area_x = 36
            bar_area_w = PILL_WIDTH - bar_area_x - 8
            spacing = (bar_area_w - bar_count * bar_w) / max(1, bar_count - 1)
            center_y = PILL_HEIGHT // 2
            max_h = PILL_HEIGHT - 6  # 2px padding top and bottom (3px each side from center)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 195))
            for i, bar_val in enumerate(frame.bars):
                bar_h = max(3, int(bar_val * max_h))
                bx = int(bar_area_x + i * (bar_w + spacing))
                by = center_y - bar_h // 2
                painter.drawRoundedRect(bx, by, bar_w, bar_h, bar_w // 2, bar_w // 2)

        painter.end()
