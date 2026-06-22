"""Tests for the pure focus-drift comparison (ADR-0026 / #97)."""

from __future__ import annotations

import importlib
import sys

from dictatem.paste.focus_drift import focus_drifted


class TestFocusDrifted:
    def test_same_target_does_not_drift(self) -> None:
        assert focus_drifted(42, 42) is False

    def test_changed_target_drifts(self) -> None:
        # Window/app changed between record-start and paste → hold, don't paste.
        assert focus_drifted(42, 99) is True

    def test_no_anchor_never_drifts(self) -> None:
        # No anchor (no ForegroundTracker, or capture skipped) → paste as before,
        # never hold — focus drift can't be detected without an anchor.
        assert focus_drifted(None, 99) is False

    def test_zero_anchor_is_a_real_anchor_not_missing(self) -> None:
        # A 0 target_id is a real (if unusual) handle, not "missing" — only None
        # means missing. 0 vs 0 → no drift; 0 vs 5 → drift.
        assert focus_drifted(0, 0) is False
        assert focus_drifted(0, 5) is True


class TestImportSafety:
    def test_no_os_imports(self) -> None:
        before = set(sys.modules.keys())
        importlib.import_module("dictatem.paste.focus_drift")
        after = set(sys.modules.keys())
        new = after - before
        forbidden = ("win32api", "win32gui", "pywintypes", "ctypes", "PySide6")
        leaked = [m for m in new if any(m == f or m.startswith(f + ".") for f in forbidden)]
        assert leaked == [], f"focus_drift pulled in OS modules: {leaked}"
