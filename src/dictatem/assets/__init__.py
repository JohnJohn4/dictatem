"""Bundled brand assets — the master waveform art and generated icon set.

The master art (``icon.png``) is full-colour with a baked-in white background.
The application/window icon (``app.ico`` and the PNG/ICNS sets) is regenerated
from it by ``scripts/gen_icons.py`` with the white background keyed out to
transparency. See ADR-0006: the full-colour art is the *application* icon; the
theme-adaptive tray rendering is a separate concern.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def asset_path(name: str) -> Path:
    """Filesystem path to a bundled asset (e.g. ``"app.ico"``, ``"icon.png"``)."""
    resource = files(__name__) / name
    # The package always ships as real files on disk (hatch copies them into
    # the wheel), so the traversable is a concrete path.
    return Path(str(resource))
