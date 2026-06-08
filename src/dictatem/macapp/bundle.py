"""Pure ``.app`` bundle generator for the Dictatem identity shell (#61 / ADR-0014).

Generates the minimal, unsigned ``Dictatem.app`` whose only job is to give TCC
a stable permission identity: the user grants "Dictatem" (not "Python") and the
grant survives ``uv tool upgrade``. The layout::

    Dictatem.app/
    └── Contents/
        ├── Info.plist          (rendered by ``macapp.plist``)
        ├── PkgInfo             (legacy "APPL????" marker)
        ├── MacOS/Dictatem      (exec shim into the uv-installed launcher)
        └── Resources/app.icns  (copied from ``dictatem.assets``)

Everything here is pure file I/O against *injected* paths — the same seam
pattern as ``LaunchAgentRegistrar`` — so the whole generator runs against
``tmp_path`` on any OS. Only "the generated ``.app`` actually launches and
binds TCC grants" is real-Mac QA. ``--install-macos-app`` (the thin darwin
glue in ``daemon``) supplies the production paths.

The shim embeds the launcher path resolved at *generation* time (mirroring the
win32 registrar's ``_launch_command``): launchd starts login items with a bare
``PATH``, so runtime ``command -v`` resolution would be dead code, and every
install/upgrade re-runs ``--install-macos-app``, which regenerates the shim —
staleness heals on the same path that could introduce it.
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

from dictatem.autostart.launch_agent import LaunchAgentRegistrar
from dictatem.macapp.plist import APP_NAME, render_info_plist

#: Bundle directory name under ``~/Applications``.
APP_BUNDLE_NAME = f"{APP_NAME}.app"

#: Name of the ``Contents/MacOS`` exec shim — must match ``CFBundleExecutable``.
EXECUTABLE_NAME = APP_NAME

#: Icon filename in ``Contents/Resources`` — must match ``CFBundleIconFile``.
ICON_FILENAME = "app.icns"


def default_apps_dir() -> Path:
    """``~/Applications`` — per-user, so generation never needs admin rights."""
    return Path.home() / "Applications"


def default_app_bundle_path() -> Path:
    """``~/Applications/Dictatem.app`` — the canonical generated location."""
    return default_apps_dir() / APP_BUNDLE_NAME


def resolve_launcher(which_result: str | None, *, home: Path) -> Path:
    """Resolve the uv-installed ``dictatem`` launcher the shim will exec.

    *which_result* is ``shutil.which("dictatem")`` from the caller (injected so
    this stays pure). Falls back to ``~/.local/bin/dictatem`` — uv's documented
    tool-bin directory on macOS — when the launcher isn't on the generating
    shell's PATH. Mirrors the win32 registrar's ``_launch_command`` preference
    for the installed launcher; unlike its interpreter fallback, the fallback
    path here may not exist yet, so the ``--install-macos-app`` glue warns
    when it doesn't.
    """
    if which_result:
        return Path(which_result)
    return home / ".local" / "bin" / "dictatem"


def launch_arguments(launcher: Path) -> list[str]:
    """The canonical command that launches the daemon (ADR-0012/0014, revised).

    Launches the uv-installed *launcher* **directly** — NOT via ``/usr/bin/open``
    on the ``.app``. Real-Mac QA (#54) found that launching through the bundle
    makes the daemon process inherit the bundle's LaunchServices identity
    (``NSRunningApplication.bundleIdentifier == com.dictatem.daemon``), and
    macOS then silently refuses to render a menu-bar status item for it — the
    tray icon never appeared. A directly-launched (non-bundle) process shows it
    fine. The ``.app`` no longer launches the daemon; it survives only as the
    icon/identity shell and the future home of a signed bundle (#91). Used by
    the LaunchAgent ``ProgramArguments``; install.sh's first launch mirrors it
    in shell.

    ``as_posix()`` (identical to ``str()`` on macOS) keeps the rendering
    deterministic when the pure function is unit-tested on Windows.
    """
    return [launcher.as_posix()]


def render_exec_shim(launcher: Path) -> str:
    """Render the ``Contents/MacOS`` shim: ``exec`` straight into *launcher*.

    ``exec`` replaces the shell with the daemon in the same PID, so the
    process launchd/LaunchServices attributed to the bundle *is* the daemon —
    no wrapper process lingers and TCC attribution stays with the ``.app``.

    The ``proc_translated`` guard undoes a LaunchServices quirk found in
    real-Mac QA (#61, macOS 26): a bundle whose only executable is a shell
    script has no Mach-O header to declare architectures, and LS launches it
    under Rosetta (the plist-level overrides that were tried and ignored, and
    the rejected Mach-O-trampoline alternative, are recorded in ADR-0014's
    amendment). A translated shim would hand a universal interpreter its
    x86_64 slice, which dies importing the arm64-only wheels, so the shim
    re-execs itself natively via ``arch -arm64`` first. Absolute paths
    throughout — launchd/LS launch with a bare PATH (the module docstring's
    rationale). On Intel Macs the sysctl key does not exist and the guard is
    a no-op; ``exec`` keeps the PID either way.

    ``as_posix()`` (identical to ``str()`` on macOS) keeps the rendering
    deterministic when the pure function is unit-tested on Windows.
    """
    return (
        "#!/bin/sh\n"
        '[ "$(/usr/sbin/sysctl -n sysctl.proc_translated 2>/dev/null)" = "1" ]'
        ' && exec /usr/bin/arch -arm64 /bin/sh "$0" "$@"\n'
        f'exec "{launcher.as_posix()}" "$@"\n'
    )


def generate_app_bundle(
    *,
    apps_dir: Path,
    launcher: Path,
    icns_source: Path,
    version: str | None = None,
) -> Path:
    """Generate (or refresh in place) the ``.app`` shell under *apps_dir*.

    Idempotent: re-running overwrites every generated file, so an upgrade
    refreshes the shim's launcher path and the Info.plist version while the
    bundle path — the TCC identity anchor — never changes. Returns the bundle
    path. The exec bit on the shim is best-effort off POSIX (irrelevant there:
    the bundle only runs on macOS).
    """
    bundle = apps_dir / APP_BUNDLE_NAME
    macos_dir = bundle / "Contents" / "MacOS"
    resources_dir = bundle / "Contents" / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    (bundle / "Contents" / "Info.plist").write_bytes(
        render_info_plist(
            executable=EXECUTABLE_NAME,
            icon_filename=ICON_FILENAME,
            version=version,
        )
    )
    (bundle / "Contents" / "PkgInfo").write_bytes(b"APPL????")

    shim = macos_dir / EXECUTABLE_NAME
    shim.write_text(render_exec_shim(launcher), encoding="utf-8", newline="\n")
    shim.chmod(
        shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )

    shutil.copyfile(icns_source, resources_dir / ICON_FILENAME)
    return bundle


def install_app_bundle(
    *,
    apps_dir: Path,
    agents_dir: Path,
    launcher: Path,
    icns_source: Path,
    version: str | None = None,
) -> tuple[Path, bool]:
    """Generate the bundle, then refresh an existing LaunchAgent to launch it.

    The refresh is keyed on the LaunchAgent plist's *existence* — the persisted
    form of ``config.startup.autostart`` (the daemon reconciles the two into
    agreement on every launch) — so this never loads config. Rewriting it with
    the current :func:`launch_arguments` render is what heals a stale launch
    command across upgrades: ``is_enabled()`` is existence-only, so the
    launch-time reconcile deliberately never rewrites content (PR #86), and
    every install/upgrade runs ``--install-macos-app``, which lands here.

    Returns ``(bundle_path, launch_agent_refreshed)``.
    """
    bundle = generate_app_bundle(
        apps_dir=apps_dir,
        launcher=launcher,
        icns_source=icns_source,
        version=version,
    )
    registrar = LaunchAgentRegistrar(
        agents_dir=agents_dir, program_arguments=launch_arguments(launcher)
    )
    refreshed = registrar.is_enabled()
    if refreshed:
        registrar.enable()
    return bundle, refreshed


def remove_app_bundle(bundle_path: Path) -> Path | None:
    """Remove the generated bundle; return the removed path or ``None`` if absent.

    Part of the macOS uninstall (#61): the ``.app`` and the LaunchAgent must go
    away *before* ``uv tool uninstall``, which deletes the shim's exec target.
    """
    if not bundle_path.exists():
        return None
    shutil.rmtree(bundle_path)
    return bundle_path
