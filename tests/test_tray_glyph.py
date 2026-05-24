"""Unit tests for the pure tray-glyph geometry (no Qt, no Pillow)."""

from __future__ import annotations

import pytest

from dictatem.tray.glyph import waveform_bars

# Tray sizes the app actually renders (all even).
_TRAY_SIZES = (16, 20, 24, 32, 48, 64)


class TestBarCount:
    def test_small_sizes_use_fewer_bars(self) -> None:
        assert len(waveform_bars(16)) == 3

    def test_larger_sizes_use_full_silhouette(self) -> None:
        assert len(waveform_bars(32)) == 5


class TestSymmetry:
    @pytest.mark.parametrize("size", _TRAY_SIZES)
    def test_vertical_every_bar_centred_on_midline(self, size: int) -> None:
        # The whole point: every bar's centre sits exactly on size/2, so the
        # waveform shares one clean baseline (no ½px vertical offsets).
        for bar in waveform_bars(size):
            assert bar.y + bar.h / 2 == size / 2

    @pytest.mark.parametrize("size", _TRAY_SIZES)
    def test_horizontal_equal_left_and_right_margins(self, size: int) -> None:
        bars = waveform_bars(size)
        left = bars[0].x
        right = size - (bars[-1].x + bars[-1].w)
        assert left == right


class TestCrispness:
    @pytest.mark.parametrize("size", _TRAY_SIZES)
    def test_all_dimensions_are_whole_pixels(self, size: int) -> None:
        for bar in waveform_bars(size):
            assert bar.x == int(bar.x)
            assert bar.y == int(bar.y)
            assert bar.w == int(bar.w)
            assert bar.h == int(bar.h)

    @pytest.mark.parametrize("size", _TRAY_SIZES)
    def test_bars_within_bounds(self, size: int) -> None:
        for bar in waveform_bars(size):
            assert bar.x >= 0
            assert bar.y >= 0
            assert bar.x + bar.w <= size
            assert bar.y + bar.h <= size

    @pytest.mark.parametrize("size", _TRAY_SIZES)
    def test_bars_equal_width_and_non_overlapping(self, size: int) -> None:
        bars = waveform_bars(size)
        assert len({b.w for b in bars}) == 1
        for left, right in zip(bars, bars[1:], strict=False):
            assert left.x + left.w <= right.x


class TestSilhouette:
    @pytest.mark.parametrize("size", _TRAY_SIZES)
    def test_centre_bar_is_tallest(self, size: int) -> None:
        heights = [b.h for b in waveform_bars(size)]
        assert heights[len(heights) // 2] == max(heights)

    def test_geometry_scales_with_size(self) -> None:
        assert waveform_bars(64)[0].w > waveform_bars(24)[0].w

    @pytest.mark.parametrize("size", _TRAY_SIZES)
    def test_heights_mirror_around_centre(self, size: int) -> None:
        # The bar left of centre must match the bar right of centre, etc.
        heights = [b.h for b in waveform_bars(size)]
        assert heights == heights[::-1]
