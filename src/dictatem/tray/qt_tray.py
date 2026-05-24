"""PySide6 system-tray adapter — Windows manual QA only."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from dictatem.assets import asset_path
from dictatem.tray.state import IconVariant, MenuItem, TrayState

if TYPE_CHECKING:
    from collections.abc import Callable

_ICON_COLORS: dict[IconVariant, str] = {
    IconVariant.Idle: "#808080",
    IconVariant.Recording: "#00cc00",
    IconVariant.Error: "#cc0000",
}

_MENU_LABELS: dict[MenuItem, str] = {
    MenuItem.START: "Start Recording",
    MenuItem.STOP: "Stop Recording",
    MenuItem.PRELOAD: "Preload Model",
    MenuItem.UNLOAD: "Unload Model",
    MenuItem.SHOW_LOG: "Show Log",
    MenuItem.RESTART: "Restart",
    MenuItem.QUIT: "Quit",
}


def _colored_pixmap(hex_color: str, size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(hex_color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, size - 8, size - 8)
    painter.end()
    return pixmap


class QtTrayIcon:
    """System-tray icon driven by TrayState."""

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._parent = QWidget()

        # Full-colour waveform brand as the application/window icon (taskbar,
        # alt-tab, window chrome). The multi-resolution .ico lets Windows pick
        # the crispest embedded size. Per ADR-0006 this is the *application*
        # icon only; the state-driven tray icon below is unrelated and the
        # theme-adaptive tray rendering is a separate slice (#38).
        self._app_icon = QIcon(str(asset_path("app.ico")))
        self._app.setWindowIcon(self._app_icon)
        self._parent.setWindowIcon(self._app_icon)

        self._icons: dict[IconVariant, QIcon] = {
            variant: QIcon(_colored_pixmap(color))
            for variant, color in _ICON_COLORS.items()
        }

        self._tray = QSystemTrayIcon(self._icons[IconVariant.Idle], self._parent)
        self._menu = QMenu()
        self._actions: dict[MenuItem, QAction] = {}

        self.on_start: Callable[[], None] | None = None
        self.on_stop: Callable[[], None] | None = None
        self.on_preload: Callable[[], None] | None = None
        self.on_unload: Callable[[], None] | None = None
        self.on_show_log: Callable[[], None] | None = None
        self.on_restart: Callable[[], None] | None = None
        self.on_quit: Callable[[], None] | None = None

        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.show()

    def _build_menu(self) -> None:
        callback_map: dict[MenuItem, Callable[[], None]] = {
            MenuItem.START: lambda: self.on_start() if self.on_start else None,
            MenuItem.STOP: lambda: self.on_stop() if self.on_stop else None,
            MenuItem.PRELOAD: lambda: self.on_preload() if self.on_preload else None,
            MenuItem.UNLOAD: lambda: self.on_unload() if self.on_unload else None,
            MenuItem.SHOW_LOG: lambda: self._open_log(),
            MenuItem.RESTART: lambda: self.on_restart() if self.on_restart else None,
            MenuItem.QUIT: lambda: self.on_quit() if self.on_quit else None,
        }

        for item in MenuItem:
            action = QAction(_MENU_LABELS[item], self._parent)
            action.triggered.connect(callback_map[item])
            self._actions[item] = action
            self._menu.addAction(action)

    def update_state(self, state: TrayState) -> None:
        variant = state.current_icon_variant()
        self._tray.setIcon(self._icons[variant])
        for item in MenuItem:
            self._actions[item].setEnabled(state.menu_item_enabled(item))

    def show_notification(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message)

    def _open_log(self) -> None:
        if self.on_show_log is not None:
            self.on_show_log()
            return
        log_path = os.path.join(
            os.environ.get("APPDATA", ""), "Dictatem", "logs", "daemon.log"
        )
        if os.path.exists(log_path):
            os.startfile(log_path)  # type: ignore[attr-defined]  # Windows only
