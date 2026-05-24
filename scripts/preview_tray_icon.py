"""Render the theme-adaptive tray glyph for human legibility review (HITL).

Dev-only tool (requires the ``dev`` dependency group for Pillow — Pillow is
never a runtime dependency). The shipping tray rendering lives in
``src/dictatem/tray/qt_tray.py`` and runs on Qt; this script reproduces the same
luminance-keying + monochrome-tint pipeline in Pillow purely so a human can
eyeball the result at real tray sizes without launching the daemon.

It composites the glyph at 16, 24, and 32 px onto BOTH a dark taskbar swatch
(~#202020, where the glyph tints light) and a light one (~#f3f3f3, where it
tints dark), and writes a single side-by-side preview PNG.

Usage (after ``uv sync --group dev``):
    uv run python scripts/preview_tray_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dictatem.tray.state import glyph_tint_rgba  # noqa: E402

# Mirror the Qt adapter's white-keying threshold so the preview matches runtime.
WHITE_THRESHOLD = 240

TRAY_SIZES = (16, 24, 32)
DARK_SWATCH = (0x20, 0x20, 0x20)
LIGHT_SWATCH = (0xF3, 0xF3, 0xF3)

PAD = 12  # padding around each glyph cell
CELL = max(TRAY_SIZES) + 2 * PAD


def themed_glyph(source: Image.Image, *, is_dark_background: bool, size: int) -> Image.Image:
    """Reproduce the runtime monochrome tint pipeline for a single glyph.

    Derives an alpha mask from luminance (near-black bars opaque, near-white
    background transparent, anti-aliased edges fading between) and fills every
    pixel with the theme-appropriate tint.
    """
    glyph = source.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
    arr = np.asarray(glyph, dtype=np.float64)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    alpha = np.clip((WHITE_THRESHOLD - lum) / WHITE_THRESHOLD, 0.0, 1.0)
    alpha = (alpha * 255).round().astype(np.uint8)

    r, g, b, _a = glyph_tint_rgba(is_dark_background)
    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[:, :, 0] = r
    out[:, :, 1] = g
    out[:, :, 2] = b
    out[:, :, 3] = alpha
    return Image.fromarray(out, mode="RGBA")


def _row(source: Image.Image, swatch: tuple[int, int, int], *, is_dark: bool) -> Image.Image:
    row = Image.new("RGBA", (CELL * len(TRAY_SIZES), CELL), (*swatch, 255))
    for col, size in enumerate(TRAY_SIZES):
        glyph = themed_glyph(source, is_dark_background=is_dark, size=size)
        x = col * CELL + (CELL - size) // 2
        y = (CELL - size) // 2
        row.alpha_composite(glyph, (x, y))
    return row


def build_preview(source: Path, out_path: Path) -> Path:
    with Image.open(source) as raw:
        master = raw.copy()

    dark_row = _row(master, DARK_SWATCH, is_dark=True)
    light_row = _row(master, LIGHT_SWATCH, is_dark=False)

    preview = Image.new("RGBA", (dark_row.width, dark_row.height * 2), (0, 0, 0, 0))
    preview.alpha_composite(dark_row, (0, 0))
    preview.alpha_composite(light_row, (0, dark_row.height))
    preview.save(out_path, format="PNG")
    return out_path


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    source = repo / "src" / "dictatem" / "assets" / "icon.png"
    out_path = repo / "tray-icon-preview.png"
    written = build_preview(source, out_path)
    print(f"Wrote tray glyph preview to {written}")
    print("Top row: dark taskbar (#202020); bottom row: light taskbar (#f3f3f3).")
    print(f"Sizes left-to-right: {', '.join(f'{s}px' for s in TRAY_SIZES)}.")


if __name__ == "__main__":
    main()
