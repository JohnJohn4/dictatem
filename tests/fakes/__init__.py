"""In-memory fake implementations of all Protocol contracts.

Each fake is deterministic and records call history for assertions.
"""

from tests.fakes.fake_audio import FakeAudioCapture
from tests.fakes.fake_clipboard import FakeClipboardIO
from tests.fakes.fake_foreground import FakeForegroundTracker
from tests.fakes.fake_keyboard_hook import FakeKeyboardHook
from tests.fakes.fake_keystroke import FakeKeystrokeSender
from tests.fakes.fake_overlay import FakeOverlayRenderer
from tests.fakes.fake_transcriber import FakeTranscriberBackend
from tests.fakes.fake_tray import FakeTrayRenderer

__all__ = [
    "FakeAudioCapture",
    "FakeClipboardIO",
    "FakeForegroundTracker",
    "FakeKeyboardHook",
    "FakeKeystrokeSender",
    "FakeOverlayRenderer",
    "FakeTranscriberBackend",
    "FakeTrayRenderer",
]
