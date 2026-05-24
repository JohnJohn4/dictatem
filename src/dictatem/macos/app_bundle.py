"""Generate / remove the macOS .app identity shell (#61 / ADR-0014) — manual QA.

``dictatem --install-macos-app`` calls :func:`install_macos_app`, which writes
``~/Applications/Dictatem.app`` — a minimal, unsigned, locally-generated bundle
that gives TCC a stable identity so Accessibility / Input Monitoring grants
survive ``uv tool`` upgrades (ADR-0014). The bundle is:

    Dictatem.app/
      Contents/
        Info.plist          (pure-rendered; see info_plist.py)
        MacOS/dictatem       (exec shim into the uv-installed daemon)
        Resources/app.icns   (the committed brand icon)

The Info.plist XML is rendered by the PURE, unit-tested ``render_info_plist``; the
only thing here is the filesystem write (the thin part) plus copying the icon and
emitting the exec shim. Installing the app also reconciles the LaunchAgent so a
fresh install can start at login from the .app identity.

This module performs filesystem I/O and is intended for macOS manual QA. It is
NEVER imported at module top level (lazy-imported in ``daemon._install_macos_app``
/ ``daemon._run_uninstall``; ``tests/test_import_safety.py``) and is excluded from
pyright/tests (``pyproject.toml`` ``[tool.pyright] exclude``).
"""

from __future__ import annotations

import logging
import shutil
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from dictatem.assets import asset_path
from dictatem.macos.info_plist import BUNDLE_DISPLAY_NAME, BundleInfo, render_info_plist

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

APP_NAME = f"{BUNDLE_DISPLAY_NAME}.app"


def app_bundle_path() -> Path:
    """Return ``~/Applications/Dictatem.app`` (the install target)."""
    return Path.home() / "Applications" / APP_NAME


def _daemon_launch_command() -> str:
    """Return the shell command the exec shim runs to start the daemon.

    Prefer the uv-installed ``dictatem`` launcher on PATH (ADR-0011); fall back
    to ``<python> -m dictatem`` from a dev checkout. The .app exists for TCC
    identity, so it execs INTO the real daemon rather than reimplementing it.
    """
    launcher = shutil.which("dictatem")
    if launcher:
        return f'exec "{launcher}"'
    return f'exec "{sys.executable}" -m dictatem'


def _write_exec_shim(macos_dir: Path) -> Path:
    """Write the ``Contents/MacOS/dictatem`` shim and mark it executable."""
    shim = macos_dir / "dictatem"
    script = f"#!/bin/sh\n{_daemon_launch_command()}\n"
    shim.write_text(script, encoding="utf-8")
    shim.chmod(
        shim.stat().st_mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )
    return shim


def install_macos_app(out: Callable[[str], None] = print) -> Path:
    """Generate ``~/Applications/Dictatem.app`` and register the LaunchAgent.

    Idempotent: regenerates the bundle in place. Returns the bundle path. After
    writing the bundle it reconciles the LaunchAgent (ADR-0012) so a fresh install
    starts at login from the .app identity (the grant TCC trusts), honouring the
    current ``config.startup.autostart`` flag.
    """
    bundle = app_bundle_path()
    contents = bundle / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    (contents / "Info.plist").write_text(
        render_info_plist(BundleInfo()), encoding="utf-8"
    )
    shutil.copyfile(asset_path("app.icns"), resources / "app.icns")
    _write_exec_shim(macos_dir)

    out(f"Generated {bundle}")
    logger.info("Generated macOS app bundle at %s", bundle)

    _reconcile_launchagent_for_install(out)
    return bundle


def _reconcile_launchagent_for_install(out: Callable[[str], None]) -> None:
    """Reconcile the LaunchAgent to ``config.startup.autostart`` on install.

    Reuses the pure ``apply_autostart`` decision (ADR-0012) so install and the
    daemon launch path agree. Best-effort: a failure here is logged, not fatal —
    the .app itself is the primary deliverable.
    """
    try:
        from dictatem.autostart.launchagent_registrar import LaunchAgentAutostart
        from dictatem.autostart.reconcile import apply_autostart
        from dictatem.config import load_config

        config_path = Path.home() / ".dictatem" / "config.toml"
        config = load_config(config_path)
        action = apply_autostart(
            desired=config.startup.autostart, registrar=LaunchAgentAutostart()
        )
        out(f"LaunchAgent reconciled (autostart={config.startup.autostart}): {action.value}")
    except Exception:
        logger.warning("Failed to reconcile LaunchAgent during install", exc_info=True)


def remove_macos_app(out: Callable[[str], None] = print) -> None:
    """Remove ``~/Applications/Dictatem.app`` if present (uninstall step, #61).

    Idempotent: a no-op when the bundle is already absent. The LaunchAgent is
    removed separately by ``run_uninstall`` via the LaunchAgent registrar.
    """
    bundle = app_bundle_path()
    if bundle.exists():
        shutil.rmtree(bundle, ignore_errors=True)
        out(f"Removed {bundle}")
        logger.info("Removed macOS app bundle at %s", bundle)
    else:
        out(f"No app bundle at {bundle} (already removed)")
