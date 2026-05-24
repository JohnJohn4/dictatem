"""Render the procedural tray glyph for human legibility review (HITL).

Dev-only tool. The shipping tray rendering lives in
``src/dictatem/tray/qt_tray.py`` and draws with Qt; this reproduces the same bar
geometry (``dictatem.tray.glyph.waveform_bars``) + theme tint in Pillow so a
human can eyeball the result at real tray sizes without launching the daemon.

It draws the glyph at 16, 24, and 32 px onto both a dark taskbar swatch
(~#202020, where the glyph tints light) and a light one (~#f3f3f3), into a
single side-by-side preview PNG.

Usage (after ``uv sync --group dev``):
    uv run python scripts/preview_tray_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dictatem.tray.glyph import waveform_bars  # noqa: E402
from dictatem.tray.state import glyph_tint_rgba  # noqa: E402

TRAY_SIZES = (16, 24, 32)
DARK_SWATCH = (0x20, 0x20, 0x20)
LIGHT_SWATCH = (0xF3, 0xF3, 0xF3)

PAD = 12  # padding around each glyph cell
CELL = max(TRAY_SIZES) + 2 * PAD


def themed_glyph(*, is_dark_background: bool, size: int) -> Image.Image:
    """Draw the procedural waveform glyph, mirroring the Qt runtime geometry."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r, g, b, a = glyph_tint_rgba(is_dark_background)
    for bar in waveform_bars(size):
        box = [bar.x, bar.y, bar.x + bar.w, bar.y + bar.h]
        draw.rounded_rectangle(box, radius=bar.w / 2.0, fill=(r, g, b, a))
    return img


def _row(swatch: tuple[int, int, int], *, is_dark: bool) -> Image.Image:
    row = Image.new("RGBA", (CELL * len(TRAY_SIZES), CELL), (*swatch, 255))
    for col, size in enumerate(TRAY_SIZES):
        glyph = themed_glyph(is_dark_background=is_dark, size=size)
        x = col * CELL + (CELL - size) // 2
        y = (CELL - size) // 2
        row.alpha_composite(glyph, (x, y))
    return row


def build_preview(out_path: Path) -> Path:
    dark_row = _row(DARK_SWATCH, is_dark=True)
    light_row = _row(LIGHT_SWATCH, is_dark=False)
    preview = Image.new("RGBA", (dark_row.width, dark_row.height * 2), (0, 0, 0, 0))
    preview.alpha_composite(dark_row, (0, 0))
    preview.alpha_composite(light_row, (0, dark_row.height))
    preview.save(out_path, format="PNG")
    return out_path


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    out_path = repo / "tray-icon-preview.png"
    written = build_preview(out_path)
    print(f"Wrote tray glyph preview to {written}")
    print("Top row: dark taskbar (#202020); bottom row: light taskbar (#f3f3f3).")
    print(f"Sizes left-to-right: {', '.join(f'{s}px' for s in TRAY_SIZES)}.")


if __name__ == "__main__":
    main()
