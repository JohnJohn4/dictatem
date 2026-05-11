"""Win32 foreground window tracker — requires pywin32."""

from __future__ import annotations

import ctypes


class Win32ForegroundTracker:
    def capture(self) -> int:
        return ctypes.windll.user32.GetForegroundWindow()

    def restore(self, hwnd: int) -> None:
        ctypes.windll.user32.AllowSetForegroundWindow(ctypes.windll.kernel32.GetCurrentProcessId())
        ctypes.windll.user32.SetForegroundWindow(hwnd)
