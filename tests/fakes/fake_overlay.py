"""Fake overlay renderer for testing overlay state logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictatem.types import RecordingMode


class FakeOverlayRenderer:
    def __init__(self) -> None:
        self.visible: bool = False
        self.mode: RecordingMode | None = None
        self.level: float = 0.0
        self.state: str = "hidden"
        self.calls: list[tuple[str, ...]] = []

    def show(self, mode: RecordingMode) -> None:
        self.visible = True
        self.mode = mode
        self.state = "recording"
        self.calls.append(("show", mode.value))

    def update_level(self, level: float) -> None:
        self.level = level
        self.calls.append(("update_level", str(level)))

    def show_transcribing(self) -> None:
        self.state = "transcribing"
        self.calls.append(("show_transcribing",))

    def show_error(self) -> None:
        self.state = "error"
        self.calls.append(("show_error",))

    def hide(self) -> None:
        self.visible = False
        self.state = "hidden"
        self.calls.append(("hide",))
