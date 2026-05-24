"""PySide6 system-tray adapter — Windows manual QA only."""

from __future__ import annotations

import os
import winreg
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from dictatem.assets import asset_path
from dictatem.tray.state import MenuItem, TrayState, glyph_tint_rgba

if TYPE_CHECKING:
    from collections.abc import Callable

_MENU_LABELS: dict[MenuItem, str] = {
    MenuItem.START: "Start Recording",
    MenuItem.STOP: "Stop Recording",
    MenuItem.PRELOAD: "Preload Model",
    MenuItem.UNLOAD: "Unload Model",
    MenuItem.SHOW_LOG: "Show Log",
    MenuItem.RESTART: "Restart",
    MenuItem.QUIT: "Quit",
}

# Master glyph rendered at this side length; QSystemTrayIcon downscales to the
# real tray size. Large enough to stay crisp at 16-32 px.
_GLYPH_SIZE = 64

# Pixels at least this luminous are treated as the baked-in white background and
# kept fully transparent in the alpha mask; darker pixels (the near-black bars)
# become opaque. Mirrors the white-keying threshold used by gen_icons.py so the
# anti-aliased fringe around the bars does not leave a pale halo.
_WHITE_THRESHOLD = 240


def _is_dark_taskbar() -> bool:
    """True when the Windows taskbar is dark, so the glyph should be light.

    The tray sits on the taskbar, whose theme is the registry value
    ``SystemUsesLightTheme`` (0 = dark taskbar, 1 = light). This is independent
    of the *app* theme — Windows commonly runs light apps with a dark taskbar —
    so we must read the taskbar value, not Qt's ``colorScheme``. On a non-Windows
    host or if the key is unreadable, fall back to Qt's app colour scheme.
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            uses_light, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        return int(uses_light) == 0
    except OSError:
        scheme = QApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark


def _themed_glyph_pixmap(is_dark_background: bool, size: int = _GLYPH_SIZE) -> QPixmap:
    """Render the brand glyph as a theme-adaptive monochrome pixmap.

    The master art is full-colour near-black bars on a white background. We
    derive an alpha mask from luminance (dark bars → opaque, near-white
    background → transparent) and fill every opaque pixel with the single
    theme-appropriate tint colour, so the glyph reads on any taskbar.
    """
    master = QImage(str(asset_path("icon.png")))
    master = master.convertToFormat(QImage.Format.Format_ARGB32)
    master = master.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    r, g, b, _a = glyph_tint_rgba(is_dark_background)
    tint = QColor(r, g, b)

    out = QImage(master.size(), QImage.Format.Format_ARGB32)
    out.fill(Qt.GlobalColor.transparent)

    for y in range(master.height()):
        for x in range(master.width()):
            px = master.pixelColor(x, y)
            if px.alpha() == 0:
                continue
            # Rec. 601 luminance; the baked-in background is near-white.
            lum = 0.299 * px.red() + 0.587 * px.green() + 0.114 * px.blue()
            if lum >= _WHITE_THRESHOLD:
                continue
            # Opacity tracks how dark the source pixel is, so anti-aliased edges
            # fade smoothly: a fully black bar pixel is fully opaque, the
            # near-white fringe trails off toward transparent.
            alpha = int(round((_WHITE_THRESHOLD - lum) / _WHITE_THRESHOLD * 255))
            out.setPixelColor(x, y, QColor(tint.red(), tint.green(), tint.blue(), alpha))

    return QPixmap.fromImage(out)


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
        pixmap = _themed_glyph_pixmap(_is_dark_taskbar())
        self._tray.setIcon(QIcon(pixmap))

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
            action.triggered.connect(callback_map[item])
            self._actions[item] = action
            self._menu.addAction(action)

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
        log_path = os.path.join(
            os.environ.get("APPDATA", ""), "Dictatem", "logs", "daemon.log"
        )
        if os.path.exists(log_path):
            os.startfile(log_path)  # type: ignore[attr-defined]  # Windows only
