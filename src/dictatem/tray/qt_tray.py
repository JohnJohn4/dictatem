"""PySide6 system-tray adapter — manual QA only (Windows taskbar / macOS menu bar)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from dictatem.assets import asset_path
from dictatem.logpaths import daemon_log_path
from dictatem.tray.glyph import waveform_bars
from dictatem.tray.state import MenuItem, TrayState, glyph_tint_rgba

if TYPE_CHECKING:
    from collections.abc import Callable

_MENU_LABELS: dict[MenuItem, str] = {
    MenuItem.START: "Start Recording",
    MenuItem.STOP: "Stop Recording",
    MenuItem.PRELOAD: "Preload Model",
    MenuItem.UNLOAD: "Unload Model",
    MenuItem.AUTOSTART: "Start at Login",
    MenuItem.SHOW_LOG: "Show Log",
    MenuItem.RESTART: "Restart",
    MenuItem.QUIT: "Quit",
}

# Draw a native pixmap at each of these side lengths and add them all to the
# tray QIcon, so the OS picks a purpose-built size. Procedural bars stay crisp
# at every size.
_TRAY_ICON_SIZES = (16, 20, 24, 32, 48, 64)


def _is_dark_taskbar() -> bool:
    """True when the Windows taskbar is dark, so the glyph should be light.

    The tray sits on the taskbar, whose theme is the registry value
    ``SystemUsesLightTheme`` (0 = dark taskbar, 1 = light). This is independent
    of the *app* theme — Windows commonly runs light apps with a dark taskbar —
    so we must read the taskbar value, not Qt's ``colorScheme``. On a non-Windows
    host (``winreg`` is Windows-only, hence the lazy import) or if the key is
    unreadable, fall back to Qt's app colour scheme.
    """
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                uses_light, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return int(uses_light) == 0
        except OSError:
            pass
    scheme = QApplication.styleHints().colorScheme()
    return scheme == Qt.ColorScheme.Dark


def _themed_glyph_pixmap(is_dark_background: bool, size: int) -> QPixmap:
    """Draw the procedural waveform glyph at *size* px in the theme tint.

    A simplified set of pill-shaped bars (geometry from ``waveform_bars``)
    filled with the single theme-appropriate colour, so the glyph reads on any
    taskbar. Drawn natively at *size* with antialiasing — no image, keying, or
    dilation — so it stays crisp and bold even at 16 px.
    """
    r, g, b, a = glyph_tint_rgba(is_dark_background)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(r, g, b, a))
    for bar in waveform_bars(size):
        radius = bar.w / 2.0
        painter.drawRoundedRect(QRectF(bar.x, bar.y, bar.w, bar.h), radius, radius)
    painter.end()

    return pixmap


def _themed_tray_icon(is_dark_background: bool) -> QIcon:
    """Build a multi-resolution tray icon, one native pixmap per tray size."""
    icon = QIcon()
    for size in _TRAY_ICON_SIZES:
        icon.addPixmap(_themed_glyph_pixmap(is_dark_background, size))
    return icon


class QtTrayIcon:
    """System-tray icon driven by TrayState.

    Per ADR-0006 the tray icon is static brand identity: it shows the same
    theme-adaptive monochrome waveform glyph regardless of recording state.
    Only the menu enable/disable state still tracks TrayState. Recording state
    lives on the Overlay Pill's Status Dot, not here.
    """

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._parent = QWidget()

        # Full-colour waveform brand as the application/window icon (taskbar,
        # alt-tab, window chrome). The multi-resolution .ico lets Windows pick
        # the crispest embedded size. Per ADR-0006 this is the *application*
        # icon only; the tray icon below is the theme-adaptive monochrome glyph.
        self._app_icon = QIcon(str(asset_path("app.ico")))
        self._app.setWindowIcon(self._app_icon)
        self._parent.setWindowIcon(self._app_icon)

        self._tray = QSystemTrayIcon(self._parent)
        self._refresh_icon()

        self._menu = QMenu()
        self._actions: dict[MenuItem, QAction] = {}

        self.on_start: Callable[[], None] | None = None
        self.on_stop: Callable[[], None] | None = None
        self.on_preload: Callable[[], None] | None = None
        self.on_unload: Callable[[], None] | None = None
        # "Start at Login" toggle — receives the new checked state (ADR-0012).
        self.on_autostart_toggled: Callable[[bool], None] | None = None
        self.on_show_log: Callable[[], None] | None = None
        self.on_restart: Callable[[], None] | None = None
        self.on_quit: Callable[[], None] | None = None

        # Re-tint live when the OS theme changes. colorSchemeChanged fires on a
        # light/dark switch; we re-read the taskbar registry value (the app
        # scheme it carries may differ from the taskbar) and repaint.
        self._app.styleHints().colorSchemeChanged.connect(self._on_color_scheme_changed)

        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.show()

    def _refresh_icon(self) -> None:
        self._tray.setIcon(_themed_tray_icon(_is_dark_taskbar()))

    def _on_color_scheme_changed(self, _scheme: object) -> None:
        self._refresh_icon()

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
            if item is MenuItem.AUTOSTART:
                # Checkable "Start at Login" toggle. triggered passes the new
                # checked state straight through to the daemon, which flips the
                # config flag and reconciles the OS entry (ADR-0012).
                action.setCheckable(True)
                action.triggered.connect(self._on_autostart_triggered)
            else:
                action.triggered.connect(callback_map[item])
            self._actions[item] = action
            self._menu.addAction(action)

    def _on_autostart_triggered(self, checked: bool) -> None:
        if self.on_autostart_toggled is not None:
            self.on_autostart_toggled(checked)

    def set_autostart_checked(self, checked: bool) -> None:
        """Reflect the current ``config.startup.autostart`` flag in the menu."""
        self._actions[MenuItem.AUTOSTART].setChecked(checked)

    def update_state(self, state: TrayState) -> None:
        # The tray glyph is static brand identity (ADR-0006); only menu-item
        # enable/disable tracks TrayState. The icon does not change with state.
        for item in MenuItem:
            self._actions[item].setEnabled(state.menu_item_enabled(item))

    def show_notification(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message)

    def _open_log(self) -> None:
        if self.on_show_log is not None:
            self.on_show_log()
            return
        log_path = daemon_log_path(sys.platform, os.environ, Path.home())
        if log_path is None or not log_path.exists():
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(log_path)])
        else:
            os.startfile(str(log_path))  # type: ignore[attr-defined]  # Windows only
