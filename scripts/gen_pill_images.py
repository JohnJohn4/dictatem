"""Render the real Overlay Pill in each phase, for the README.

Dev-only tool (requires the ``runtime`` extra for PySide6 and the ``dev`` group
for Pillow). It drives the real :class:`~dictatem.overlay.state.OverlayState`
with a fake clock and paints the real
:class:`~dictatem.overlay.qt_widget.QtOverlayWidget` offscreen
(``QT_QPA_PLATFORM=offscreen``), so the images are exactly what the app paints
and can be regenerated whenever the pill changes. Nothing is drawn by hand: the
only inputs are the phase transitions, a scripted microphone level, and the
clock.

Writes into ``docs/images/``:

    - pill-<phase>.png   one transparent PNG per phase (2x, for crisp README use)
    - pill-dictation.gif one dictation: listening, then transcribing, then gone

Usage (after ``uv sync --extra runtime --group dev``):
    uv run python scripts/gen_pill_images.py

See ADR-0016 (model-loading caption) and ADR-0026 (phase by colour).
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

# Must be set before PySide6 is imported: no window ever appears on screen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    # The offscreen plugin ships no fonts on Windows (captions come out as
    # boxes); point it at the system fonts instead.
    os.environ.setdefault(
        "QT_QPA_FONTDIR", str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
    )

# The environment above must be in place before Qt loads, hence the late imports.
from PIL import Image  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QImage, QRegion  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from dictatem.overlay.qt_widget import QtOverlayWidget  # noqa: E402
from dictatem.overlay.state import PILL_HEIGHT, PILL_WIDTH, OverlayState  # noqa: E402
from dictatem.types import RecordingMode  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable

# The offscreen plugin's default UI font is a generic "Sans Serif"; use the
# font the native Windows plugin gives the pill, so captions match the app.
WINDOWS_UI_FONT = "Segoe UI"

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "images"

# Render at 2x so the pill stays sharp on high-DPI screens; the README shows it
# at its real 200x40 size.
SCALE = 2

# The animated GIF has no partial transparency, so its frames sit on a plain
# backdrop (a neutral desktop grey), with a little room around the pill.
GIF_BACKDROP = (233, 236, 241, 255)
GIF_PAD = 12
GIF_FPS = 20

# A raw mic RMS in the range speech produces (see QtOverlayWidget.update_level).
SPEAKING_RMS = 0.03


class FakeClock:
    """The injected clock: time only moves when the script says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass(frozen=True)
class Phase:
    name: str
    enter: Callable[[OverlayState, QtOverlayWidget, FakeClock], None]


def _recording(state: OverlayState, widget: QtOverlayWidget, clock: FakeClock) -> None:
    state.show_recording(RecordingMode.TOGGLE)
    clock.now += 0.2  # past the fade-in
    state.tick()
    widget.update_level(SPEAKING_RMS)


def _transcribing(state: OverlayState, _w: QtOverlayWidget, clock: FakeClock) -> None:
    state.show_transcribing()
    clock.now += 0.3


def _computing(state: OverlayState, _w: QtOverlayWidget, clock: FakeClock) -> None:
    state.show_computing()
    clock.now += 0.3


def _loading(label: str) -> Callable[[OverlayState, QtOverlayWidget, FakeClock], None]:
    def enter(state: OverlayState, _w: QtOverlayWidget, clock: FakeClock) -> None:
        state.show_loading(label)
        clock.now += 0.9  # three dots
    return enter


def _busy(state: OverlayState, _w: QtOverlayWidget, clock: FakeClock) -> None:
    state.show_transcribing()
    clock.now += 0.3
    state.show_busy_nudge()


def _held(state: OverlayState, _w: QtOverlayWidget, _c: FakeClock) -> None:
    state.show_held()


def _say_again(state: OverlayState, _w: QtOverlayWidget, _c: FakeClock) -> None:
    state.flash_say_again()


def _error(state: OverlayState, _w: QtOverlayWidget, _c: FakeClock) -> None:
    state.flash_error()


PHASES: tuple[Phase, ...] = (
    Phase("listening", _recording),
    Phase("transcribing", _transcribing),
    Phase("trigger-word", _computing),
    Phase("loading-model", _loading("Loading Dict. Model")),
    Phase("downloading-model", _loading("Downloading model")),
    Phase("still-working", _busy),
    Phase("held", _held),
    Phase("say-again", _say_again),
    Phase("error", _error),
)


def grab(widget: QWidget) -> Image.Image:
    """Paint *widget* into a transparent RGBA image at :data:`SCALE`."""
    image = QImage(
        PILL_WIDTH * SCALE, PILL_HEIGHT * SCALE, QImage.Format.Format_RGBA8888
    )
    image.setDevicePixelRatio(SCALE)
    image.fill(0)
    # No DrawWindowBackground flag: keep the area outside the capsule clear.
    widget.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    raw = bytes(image.constBits())
    return Image.frombuffer(
        "RGBA", (image.width(), image.height()), raw, "raw", "RGBA",
        image.bytesPerLine(), 1,
    ).copy()


def render_phase(phase: Phase) -> Image.Image:
    clock = FakeClock()
    state = OverlayState(clock)
    widget = QtOverlayWidget(state)
    phase.enter(state, widget, clock)
    return grab(widget)


def _speech_level(t: float) -> float:
    """A scripted mic level: two bursts of 'speech' with a breath between."""
    if t < 0.15 or 1.05 < t < 1.25 or t > 2.0:
        return 0.002
    syllables = 0.5 + 0.5 * math.sin(t * 19.0) * math.sin(t * 7.3 + 1.0)
    return SPEAKING_RMS * (0.25 + 0.95 * abs(syllables))


def _on_backdrop(frame: Image.Image, opacity: float) -> Image.Image:
    if opacity < 1.0:
        lut = [round(a * opacity) for a in range(256)]
        alpha = frame.getchannel("A").point(lut)
        frame = frame.copy()
        frame.putalpha(alpha)
    pad = GIF_PAD * SCALE
    canvas = Image.new(
        "RGBA", (frame.width + 2 * pad, frame.height + 2 * pad), GIF_BACKDROP
    )
    canvas.alpha_composite(frame, (pad, pad))
    return canvas.convert("RGB")


def render_dictation_gif(path: Path) -> None:
    """One dictation, frame by frame: listening, transcribing, fade-out."""
    clock = FakeClock()
    state = OverlayState(clock)
    widget = QtOverlayWidget(state)
    step = 1.0 / GIF_FPS
    frames: list[Image.Image] = []

    def capture() -> None:
        state.tick()
        frames.append(_on_backdrop(grab(widget), state.current_opacity()))

    # Idle backdrop first, so the loop reads as "nothing, then the pill".
    blank = _on_backdrop(Image.new("RGBA", (PILL_WIDTH * SCALE, PILL_HEIGHT * SCALE)), 1.0)
    frames.extend([blank] * (GIF_FPS // 2))

    state.show_recording(RecordingMode.PTT)
    start = clock.now
    while clock.now - start < 2.2:
        widget.update_level(_speech_level(clock.now - start))
        capture()
        clock.now += step

    state.show_transcribing()
    start = clock.now
    while clock.now - start < 1.4:
        capture()
        clock.now += step

    state.hide()
    while True:
        state.tick()
        if state.current_opacity() <= 0.0:
            break
        capture()
        clock.now += step

    frames.extend([blank] * GIF_FPS)
    # The pill's few flat colours quantise cleanly; one shared palette, built
    # from frames across every phase, keeps the file small and each phase's
    # colour steady between frames.
    sample = frames[::4]
    sheet = Image.new("RGB", (frames[0].width, frames[0].height * len(sample)))
    for i, frame in enumerate(sample):
        sheet.paste(frame, (0, i * frame.height))
    palette = sheet.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    quantised = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    quantised[0].save(
        path,
        save_all=True,
        append_images=quantised[1:],
        duration=round(1000 / GIF_FPS),
        loop=0,
        optimize=True,
    )


def main() -> int:
    # Widgets need a QApplication; hold the reference until we're done.
    app = QApplication.instance() or QApplication(sys.argv)
    if sys.platform == "win32":
        font = QApplication.font()
        font.setFamily(WINDOWS_UI_FONT)
        QApplication.setFont(font)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for phase in PHASES:
        path = OUT_DIR / f"pill-{phase.name}.png"
        render_phase(phase).save(path, format="PNG", optimize=True)
        written.append(path)
    gif = OUT_DIR / "pill-dictation.gif"
    render_dictation_gif(gif)
    written.append(gif)
    for path in written:
        print(f"wrote {path.relative_to(OUT_DIR.parents[1])}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
