"""Pure geometry for the procedural tray waveform glyph (no Qt, no Pillow).

The tray icon is drawn in code (not derived from the brand image) so it stays
crisp and symmetric at every tray size. Everything snaps to whole pixels, with
**even** bar widths and **even** bar heights: in an even-sized icon that makes
every bar centre exactly on the icon's mid-line (vertical symmetry) and the bar
block sit with equal left/right margins (horizontal symmetry). Small sizes use
fewer bars so even-width bars still fit. The full-colour brand image is still
used for the application icon (`.ico`/`.icns`), per ADR-0006.
"""

from __future__ import annotations

from typing import NamedTuple


class Bar(NamedTuple):
    """A single waveform bar in pixels. Draw as a pill: corner radius = w / 2."""

    x: float
    y: float
    w: float
    h: float


# Relative bar heights (fraction of content height), tall-centre waveform
# silhouettes. Palindromic so the glyph mirrors around the centre bar (the bar
# left of centre matches the bar right of centre). Fewer bars at small sizes so
# even-width bars still fit.
_BAR_HEIGHTS_FULL: tuple[float, ...] = (0.55, 0.80, 1.00, 0.80, 0.55)
_BAR_HEIGHTS_SMALL: tuple[float, ...] = (0.66, 1.00, 0.66)
_FEW_BARS_MAX_SIZE = 20  # at or below this, use the small (fewer-bar) silhouette

_MARGIN_FRAC = 0.10  # padding around the content, as a fraction of icon size
_GAP_TO_BAR = 2.0  # gap width as a multiple of bar width — wide, clear gaps


def _nearest_even(value: float, minimum: int = 2) -> int:
    """Round *value* to the nearest even integer, at least *minimum*."""
    return max(minimum, round(value / 2) * 2)


def waveform_bars(size: int) -> list[Bar]:
    """Lay out the tray waveform for a square icon of *size* px.

    Bars are equal (even) width, evenly spaced, and (even) heights centred on
    the icon mid-line. For an even *size* this yields exact symmetry on both
    axes with crisp, pixel-aligned bars. Pure: the Qt adapter and the preview
    render identical geometry.
    """
    heights = _BAR_HEIGHTS_SMALL if size <= _FEW_BARS_MAX_SIZE else _BAR_HEIGHTS_FULL
    n = len(heights)
    margin = round(size * _MARGIN_FRAC)
    content = size - 2 * margin

    # Even bar width from the target gap:bar ratio, shrunk until n bars + 1px
    # minimum gaps fit. Even width keeps the bar block centred with equal margins.
    bar_w = _nearest_even(content / (n + (n - 1) * _GAP_TO_BAR))
    while bar_w > 2 and n * bar_w + (n - 1) > content:
        bar_w -= 2

    gap = max(1, round((content - n * bar_w) / (n - 1)))
    span = n * bar_w + (n - 1) * gap  # even (n-1 is even, bar_w is even)
    x0 = round((size - span) / 2.0)  # equal left/right margins for even size

    bars: list[Bar] = []
    for i, height_frac in enumerate(heights):
        x = x0 + i * (bar_w + gap)
        h = _nearest_even(height_frac * content)
        y = (size - h) // 2  # even size − even height ⇒ exact vertical centre
        bars.append(Bar(x=float(x), y=float(y), w=float(bar_w), h=float(h)))
    return bars
