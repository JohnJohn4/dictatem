"""PySide6 overlay widget — Windows manual QA only.

This module intentionally imports PySide6 and must never be imported on Linux
or in the test suite.  It is the thin rendering adapter that subscribes to
:class:`~dictatem.overlay.state.OverlayState` and paints the pill.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictatem.overlay.state import OverlayState

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class QtOverlayWidget(QWidget):
    """Frameless, always-on-top, click-through recording pill."""

    _FPS = 30

    def __init__(self, overlay_state: OverlayState) -> None:
        super().__init__(None)
        self._state = overlay_state

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(200, 40)

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // self._FPS)
        self._timer.timeout.connect(self._on_tick)

    def show_pill(self) -> None:
        from dictatem.overlay.state import Point

        pos = self._state.compute_position(
            cursor_position=Point(0, 0),
            monitors=[],
        )
        self.move(pos.x, pos.y)
        self.show()
        self._timer.start()

    def hide_pill(self) -> None:
        self._timer.stop()
        self.hide()

    def _on_tick(self) -> None:
        from dictatem.overlay.state import OverlayPhase

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

        dot_color_name = self._state.current_dot_color().value
        dot_qcolor = QColor("red") if dot_color_name == "red" else QColor(255, 191, 0)

        from dictatem.overlay.state import DotStyle

        if self._state.current_dot_style() == DotStyle.OUTLINE:
            painter.setPen(QPen(dot_qcolor, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_qcolor)
        painter.drawEllipse(8, 10, 20, 20)

        painter.end()
