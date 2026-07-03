"""Tests verifying that all Protocol contracts are defined with correct signatures."""

from __future__ import annotations

import inspect

from dictatem import interfaces

EXPECTED_PROTOCOLS = [
    "ClipboardIO",
    "KeystrokeSender",
    "ForegroundTracker",
    "KeyboardHook",
    "AudioCapture",
    "TranscriberBackend",
    "TransformBackend",
    "AutostartRegistrar",
    "DaemonStopper",
    "OverlayRenderer",
    "TrayRenderer",
]


class TestProtocolsExist:
    def test_all_protocols_defined(self) -> None:
        for name in EXPECTED_PROTOCOLS:
            cls = getattr(interfaces, name)
            assert inspect.isclass(cls), f"{name} is not a class"


class TestProtocolSignatures:
    def test_clipboard_io_methods(self) -> None:
        assert callable(getattr(interfaces.ClipboardIO, "save", None))
        assert callable(getattr(interfaces.ClipboardIO, "set_text", None))
        assert callable(getattr(interfaces.ClipboardIO, "restore", None))
        assert callable(getattr(interfaces.ClipboardIO, "copy", None))

    def test_keystroke_sender_methods(self) -> None:
        assert callable(getattr(interfaces.KeystrokeSender, "send_paste", None))
        assert callable(
            getattr(interfaces.KeystrokeSender, "send_backspaces", None)
        )
        assert callable(getattr(interfaces.KeystrokeSender, "send_text", None))

    def test_foreground_tracker_methods(self) -> None:
        assert callable(getattr(interfaces.ForegroundTracker, "capture", None))
        assert callable(getattr(interfaces.ForegroundTracker, "restore", None))

    def test_keyboard_hook_methods(self) -> None:
        assert callable(getattr(interfaces.KeyboardHook, "install", None))
        assert callable(getattr(interfaces.KeyboardHook, "uninstall", None))
        # The key-event handler is constructor-injected (see the Protocol
        # docstring), so install/uninstall take no arguments.
        install_params = inspect.signature(interfaces.KeyboardHook.install).parameters
        assert list(install_params) == ["self"]

    def test_audio_capture_methods(self) -> None:
        assert callable(getattr(interfaces.AudioCapture, "start", None))
        assert callable(getattr(interfaces.AudioCapture, "stop", None))
        # close() is the final shutdown teardown, distinct from per-dictation
        # stop(); re-added with the macOS AVAudioEngine backend (#161).
        assert callable(getattr(interfaces.AudioCapture, "close", None))

    def test_transcriber_backend_methods(self) -> None:
        assert callable(getattr(interfaces.TranscriberBackend, "load_model", None))
        assert callable(getattr(interfaces.TranscriberBackend, "unload_model", None))
        assert callable(getattr(interfaces.TranscriberBackend, "transcribe", None))
        assert callable(getattr(interfaces.TranscriberBackend, "empty_cache", None))
        assert callable(getattr(interfaces.TranscriberBackend, "set_progress_callback", None))

    def test_transform_backend_methods(self) -> None:
        assert callable(getattr(interfaces.TransformBackend, "transform", None))

    def test_autostart_registrar_methods(self) -> None:
        assert callable(getattr(interfaces.AutostartRegistrar, "enable", None))
        assert callable(getattr(interfaces.AutostartRegistrar, "disable", None))
        assert callable(getattr(interfaces.AutostartRegistrar, "is_enabled", None))

    def test_daemon_stopper_methods(self) -> None:
        assert callable(getattr(interfaces.DaemonStopper, "stop_running_daemons", None))

    def test_overlay_renderer_methods(self) -> None:
        assert callable(getattr(interfaces.OverlayRenderer, "show", None))
        assert callable(getattr(interfaces.OverlayRenderer, "update_level", None))
        assert callable(getattr(interfaces.OverlayRenderer, "show_transcribing", None))
        assert callable(getattr(interfaces.OverlayRenderer, "show_computing", None))
        assert callable(getattr(interfaces.OverlayRenderer, "show_error", None))
        assert callable(getattr(interfaces.OverlayRenderer, "hide", None))

    def test_tray_renderer_methods(self) -> None:
        assert callable(getattr(interfaces.TrayRenderer, "set_idle", None))
        assert callable(getattr(interfaces.TrayRenderer, "set_recording", None))
        assert callable(getattr(interfaces.TrayRenderer, "set_error", None))
        assert callable(getattr(interfaces.TrayRenderer, "set_has_last_dictation", None))
        assert callable(getattr(interfaces.TrayRenderer, "show_notification", None))


class TestProtocolsAreRuntimeCheckable:
    def test_all_runtime_checkable(self) -> None:
        for name in EXPECTED_PROTOCOLS:
            cls = getattr(interfaces, name)
            assert hasattr(cls, "__protocol_attrs__") or hasattr(
                cls, "_is_runtime_protocol"
            ), f"{name} is not runtime_checkable"
