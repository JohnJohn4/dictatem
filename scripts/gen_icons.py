"""Regenerate the cross-platform application icon set from the master art.

Dev-only tool (requires the ``dev`` dependency group for Pillow). The master
art ``src/dictatem/assets/icon.png`` is full-colour with a baked-in white
background; this script keys that white out to transparency and writes the
committed icon set back into ``src/dictatem/assets/``:

    - app.ico   multi-resolution (16, 24, 32, 48, 64, 128, 256)
    - app.icns  16-1024 including @2x retina sizes
    - icon-<N>.png for N in (16, 32, 48, 128, 256, 512, 1024)

Usage (after ``uv sync --group dev``):
    uv run python scripts/gen_icons.py

See ADR-0006: the full-colour art is reserved for the *application* icon. The
theme-adaptive tray rendering is a separate slice (issue #38) and is not
produced here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

# Pixels at least this luminous (per channel, roughly) are treated as the white
# background and keyed to transparent. Anti-aliased edges fade toward the white
# background, so we key by a near-white threshold rather than exact white to
# avoid a pale halo box around the brand.
WHITE_THRESHOLD = 240

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_SIZES = (16, 32, 64, 128, 256, 512, 1024)  # includes @2x of 8..512
PNG_SIZES = (16, 32, 48, 128, 256, 512, 1024)


def key_white_to_transparent(img: Image.Image, threshold: int = WHITE_THRESHOLD) -> Image.Image:
    """Return a copy of ``img`` with its near-white background made transparent.

    A pixel is considered background when *every* RGB channel is at or above
    ``threshold`` (i.e. near-white). Such pixels get alpha 0; all others keep
    their original alpha. Keying by a near-white threshold (rather than exact
    255,255,255) removes the anti-aliased halo that an exact match would leave
    as a faint box around the artwork.
    """
    rgba = img.convert("RGBA")
    arr = np.array(rgba)
    background = np.all(arr[:, :, :3] >= threshold, axis=2)
    arr[background, 3] = 0
    return Image.fromarray(arr, mode="RGBA")


def _resized(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.Resampling.LANCZOS)


def generate_icons(source: Path, out_dir: Path) -> list[Path]:
    """Generate the full icon set from ``source`` into ``out_dir``.

    Returns the list of written file paths. The source is keyed once at full
    resolution, then downscaled per output so edges resample cleanly.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as raw:
        keyed = key_white_to_transparent(raw)

    written: list[Path] = []

    # PNG set.
    for size in PNG_SIZES:
        path = out_dir / f"icon-{size}.png"
        _resized(keyed, size).save(path, format="PNG")
        written.append(path)

    # Multi-resolution Windows .ico. Pillow embeds each requested size.
    ico_path = out_dir / "app.ico"
    _resized(keyed, max(ICO_SIZES)).save(
        ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES]
    )
    written.append(ico_path)

    # macOS .icns. Pillow derives the standard members from the largest image.
    icns_path = out_dir / "app.icns"
    _resized(keyed, max(ICNS_SIZES)).save(
        icns_path, format="ICNS", sizes=[(s, s) for s in ICNS_SIZES]
    )
    written.append(icns_path)

    return written


def main() -> None:
    assets = Path(__file__).resolve().parent.parent / "src" / "dictatem" / "assets"
    source = assets / "icon.png"
    written = generate_icons(source, assets)
    print(f"Wrote {len(written)} icon files to {assets}:")
    for path in written:
        print(f"  {path.name}")


if __name__ == "__main__":
    main()
