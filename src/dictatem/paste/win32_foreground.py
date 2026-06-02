"""Win32 foreground window tracker — uses ctypes."""

from __future__ import annotations

import ctypes


class Win32ForegroundTracker:
    def capture(self) -> int:
        return ctypes.windll.user32.GetForegroundWindow()

    def restore(self, target_id: int) -> None:
        # On Windows the target_id is a window handle (HWND).
        ctypes.windll.user32.SetForegroundWindow(target_id)
