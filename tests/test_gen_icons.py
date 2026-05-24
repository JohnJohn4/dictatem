"""Tests for the dev-only icon generation pipeline (scripts/gen_icons.py).

Qt rendering is manual QA, but the white-keying and file-generation logic is
pure and worth testing. We import the script module directly off ``scripts/``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_gen_icons():
    spec = importlib.util.spec_from_file_location(
        "gen_icons", _SCRIPTS_DIR / "gen_icons.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_icons"] = module
    spec.loader.exec_module(module)
    return module


gen_icons = _load_gen_icons()


# --- pure white-keying logic -------------------------------------------------


def test_pure_white_pixel_becomes_transparent() -> None:
    img = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
    keyed = gen_icons.key_white_to_transparent(img)
    assert keyed.getpixel((0, 0))[3] == 0


def test_near_black_bar_pixel_stays_opaque() -> None:
    img = Image.new("RGBA", (1, 1), (44, 43, 48, 255))
    keyed = gen_icons.key_white_to_transparent(img)
    assert keyed.getpixel((0, 0))[3] == 255


def test_near_white_edge_halo_is_keyed_out() -> None:
    # Anti-aliased edge pixel just shy of pure white must also go transparent,
    # otherwise the icon shows a pale halo box.
    img = Image.new("RGBA", (1, 1), (250, 251, 249, 255))
    keyed = gen_icons.key_white_to_transparent(img)
    assert keyed.getpixel((0, 0))[3] == 0


def test_keyed_image_keeps_dimensions() -> None:
    img = Image.new("RGBA", (8, 8), (255, 255, 255, 255))
    keyed = gen_icons.key_white_to_transparent(img)
    assert keyed.size == (8, 8)
    assert keyed.mode == "RGBA"


# --- full generation ---------------------------------------------------------


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory):
    out_dir = tmp_path_factory.mktemp("icons")
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "dictatem"
        / "assets"
        / "icon.png"
    )
    written = gen_icons.generate_icons(source, out_dir)
    return out_dir, written


def test_generates_expected_files(generated) -> None:
    out_dir, _written = generated
    expected = {
        "app.ico",
        "app.icns",
        "icon-16.png",
        "icon-32.png",
        "icon-48.png",
        "icon-128.png",
        "icon-256.png",
        "icon-512.png",
        "icon-1024.png",
    }
    present = {p.name for p in out_dir.iterdir()}
    assert expected <= present


def test_ico_contains_expected_resolutions(generated) -> None:
    out_dir, _ = generated
    with Image.open(out_dir / "app.ico") as ico:
        sizes = {size[0] for size in ico.ico.sizes()}  # type: ignore[attr-defined]
    assert {16, 24, 32, 48, 64, 128, 256} <= sizes


def test_png_outputs_have_correct_sizes(generated) -> None:
    out_dir, _ = generated
    for size in (16, 32, 48, 128, 256, 512, 1024):
        with Image.open(out_dir / f"icon-{size}.png") as png:
            assert png.size == (size, size)
            assert png.mode == "RGBA"


def test_app_icon_has_transparency(generated) -> None:
    out_dir, _ = generated
    with Image.open(out_dir / "icon-256.png") as png:
        alphas = png.getchannel("A").getextrema()
    # Some pixel must be (near-)transparent: the keyed-out white background.
    assert alphas[0] < 255


def test_app_icon_keeps_opaque_brand_pixels(generated) -> None:
    out_dir, _ = generated
    with Image.open(out_dir / "icon-256.png") as png:
        alphas = png.getchannel("A").getextrema()
    # The dark waveform bars must remain fully opaque.
    assert alphas[1] == 255


def test_icns_is_valid_icns(generated) -> None:
    out_dir, _ = generated
    with Image.open(out_dir / "app.icns") as icns:
        assert icns.format == "ICNS"
