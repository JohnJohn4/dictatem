"""macOS LaunchAgent autostart: pure plist renderer + registrar I/O seam (#61).

The macOS autostart entry is a per-user LaunchAgent plist (ADR-0012) whose
``ProgramArguments`` launch the generated ``Dictatem.app`` — the identity TCC
trusts (ADR-0014) — never the bare venv binary. The plist rendering is a pure
function; :class:`LaunchAgentRegistrar` is only the file I/O seam around an
*injected* LaunchAgents directory, so every method runs against ``tmp_path``
on any OS. The reconcile *decision* stays in ``autostart.reconcile``.

Registration is the plist file's existence: ``RunAtLoad`` makes launchd start
the daemon at the next login. The registrar deliberately does not shell out to
``launchctl`` — immediate load/unload is native, manual-QA-only behaviour.
"""

from __future__ import annotations

import logging
import os
import plistlib
from pathlib import Path
from typing import TYPE_CHECKING

from dictatem.macapp.plist import BUNDLE_ID

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


def default_agents_dir() -> Path:
    """``~/Library/LaunchAgents`` — the production value for the injected
    *agents_dir*. The registrar seam itself stays injected (tmp_path-tested);
    this is the single place the wiring gets the real directory from."""
    return Path.home() / "Library" / "LaunchAgents"


def render_launch_agent_plist(*, label: str, program_arguments: Sequence[str]) -> bytes:
    """Render the LaunchAgent plist registering *program_arguments* at login.

    Pure: (label, argv) -> plist XML bytes via stdlib ``plistlib``. *label* is
    the launchd job identity — the canonical bundle id, so the LaunchAgent and
    the ``.app`` share one name in ``launchctl list`` and on disk.
    """
    agent: dict[str, object] = {
        "Label": label,
        "ProgramArguments": list(program_arguments),
        "RunAtLoad": True,
    }
    return plistlib.dumps(agent, sort_keys=True)


class LaunchAgentRegistrar:
    """``AutostartRegistrar`` backed by a per-user LaunchAgent plist file.

    *agents_dir* (``~/Library/LaunchAgents`` in production) and
    *program_arguments* (the ``.app`` launch command) are injected at wiring
    time, keeping this seam free of any ``~/Library`` knowledge so it is fully
    unit-testable against ``tmp_path`` on any OS.
    """

    def __init__(
        self,
        *,
        agents_dir: Path,
        program_arguments: Sequence[str],
        label: str = BUNDLE_ID,
    ) -> None:
        self._agents_dir = agents_dir
        self._program_arguments = list(program_arguments)
        self._label = label

    @property
    def plist_path(self) -> Path:
        """Where the LaunchAgent plist lives: ``<agents_dir>/<label>.plist``."""
        return self._agents_dir / f"{self._label}.plist"

    def enable(self) -> None:
        """Write the LaunchAgent plist. Idempotent — rewriting converges on the
        same file, mirroring the Win32 adapter's unconditional ``SetValueEx``.

        Written atomically (sibling tmp file + ``os.replace``) so a crash
        mid-write can never leave a truncated plist that the existence-only
        ``is_enabled()`` would report as registered.

        Note that the reconcile driver (``apply_autostart``) only reaches this
        when ``is_enabled()`` is False, and ``is_enabled()`` checks existence,
        not content — an existing plist with a stale launch command is never
        rewritten through reconcile (the Win32 adapter shares this property).
        Staleness instead heals on the upgrade path: ``--install-macos-app``,
        which every install/upgrade runs, rewrites an existing plist with the
        current launch command (see ``macapp.bundle.install_app_bundle``).
        """
        self._agents_dir.mkdir(parents=True, exist_ok=True)
        rendered = render_launch_agent_plist(
            label=self._label, program_arguments=self._program_arguments
        )
        tmp_path = self.plist_path.with_name(self.plist_path.name + ".tmp")
        tmp_path.write_bytes(rendered)
        os.replace(tmp_path, self.plist_path)
        logger.info("Registered LaunchAgent %s", self.plist_path)

    def disable(self) -> None:
        """Remove the LaunchAgent plist. Idempotent — a no-op if absent."""
        try:
            self.plist_path.unlink()
        except FileNotFoundError:
            return
        logger.info("Removed LaunchAgent %s", self.plist_path)

    def is_enabled(self) -> bool:
        """Whether the LaunchAgent plist currently exists."""
        return self.plist_path.is_file()
