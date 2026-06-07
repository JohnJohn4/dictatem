"""Protocol-conformance tests for the macOS Phase-1 no-op adapters (#54).

These stand-ins must satisfy the same Protocols as the real adapters so the
DaemonCore wiring is unchanged; behaviourally they hold/deliver nothing. The
real macOS adapters land in #59 (paste) and #61 (autostart).
"""

from __future__ import annotations

from dictatem.autostart.noop_registrar import NoopAutostartRegistrar
from dictatem.interfaces import (
    AutostartRegistrar,
    ClipboardIO,
    ForegroundTracker,
    KeystrokeSender,
)
from dictatem.paste.noop import (
    NoopClipboardIO,
    NoopForegroundTracker,
    NoopKeystrokeSender,
)


class TestProtocolConformance:
    def test_clipboard(self) -> None:
        assert isinstance(NoopClipboardIO(), ClipboardIO)

    def test_keystroke(self) -> None:
        assert isinstance(NoopKeystrokeSender(), KeystrokeSender)

    def test_foreground(self) -> None:
        assert isinstance(NoopForegroundTracker(), ForegroundTracker)

    def test_autostart_registrar(self) -> None:
        assert isinstance(NoopAutostartRegistrar(), AutostartRegistrar)


class TestNoopBehaviour:
    def test_clipboard_save_sees_empty_clipboard(self) -> None:
        assert NoopClipboardIO().save() is None

    def test_foreground_capture_is_constant(self) -> None:
        tracker = NoopForegroundTracker()
        assert tracker.capture() == 0
        tracker.restore(0)  # must not raise

    def test_registrar_reports_disabled(self) -> None:
        registrar = NoopAutostartRegistrar()
        registrar.enable()
        # No entry is ever written, so the reconcile decision always sees
        # "absent" — enable() only logs until the LaunchAgent registrar (#61).
        assert registrar.is_enabled() is False
