"""macOS LaunchAgent AutostartRegistrar (#55 / ADR-0012, ADR-0014) — manual QA.

The macOS analogue of ``win32_registrar.py``: implements the ``AutostartRegistrar``
Protocol by writing / removing a per-user LaunchAgent plist under
``~/Library/LaunchAgents``. The daemon owns autostart and reconciles this entry to
``config.startup.autostart`` on launch via the pure
``reconcile.apply_autostart`` — the SAME decision Windows runs; only this adapter
differs.

Per ADR-0014 the LaunchAgent launches the **.app identity shell**
(``~/Applications/Dictatem.app``), not the bare venv binary, so a login-started
daemon keeps the Accessibility / Input Monitoring grants TCC bound to the bundle.
``open -a`` (rather than execing the binary directly) launches through the bundle
so the grant identity is preserved; ``RunAtLoad`` starts it at login and
``loadctl`` (``launchctl``) is asked to (un)load the agent so the change takes
effect without a logout.

Excluded from pyright/tests (``pyproject.toml`` ``[tool.pyright] exclude``); its
behaviour is exercised through ``FakeAutostartRegistrar`` in the unit suite and
the pure ``reconcile_autostart`` decision. Never imported at module top level by a
pure core (lazy-imported in the daemon path; ``tests/test_import_safety.py``).
"""

from __future__ import annotations

import logging
import plistlib
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# The LaunchAgent label doubles as the plist filename stem. Stable so reconcile
# can find and remove exactly the entry it wrote.
_LABEL = "com.dictatem.Dictatem"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _app_bundle_path() -> Path:
    # ~/Applications/Dictatem.app — the identity TCC trusts (ADR-0014).
    return Path.home() / "Applications" / "Dictatem.app"


def _agent_plist_bytes() -> bytes:
    """Build the LaunchAgent plist that launches the .app at login.

    Uses ``/usr/bin/open -a <bundle>`` so the daemon starts through the bundle
    identity (grants survive), with ``RunAtLoad`` for start-at-login.
    """
    program_args = ["/usr/bin/open", "-a", str(_app_bundle_path())]
    payload = {
        "Label": _LABEL,
        "ProgramArguments": program_args,
        "RunAtLoad": True,
    }
    return plistlib.dumps(payload)


class LaunchAgentAutostart:
    """AutostartRegistrar backed by a ~/Library/LaunchAgents plist."""

    def enable(self) -> None:
        path = _plist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_agent_plist_bytes())
        self._launchctl("load", path)
        logger.info("Wrote LaunchAgent -> %s", path)

    def disable(self) -> None:
        path = _plist_path()
        if path.exists():
            self._launchctl("unload", path)
            path.unlink(missing_ok=True)
            logger.info("Removed LaunchAgent %s", path)

    def is_enabled(self) -> bool:
        return _plist_path().exists()

    @staticmethod
    def _launchctl(verb: str, path: Path) -> None:
        """Best-effort ``launchctl load/unload``; a failure is logged, not fatal.

        Writing the plist is what reconcile keys ``is_enabled`` off; asking
        launchctl to (un)load makes it take effect this session. If launchctl is
        unavailable the plist still applies at next login.
        """
        try:
            subprocess.run(
                ["launchctl", verb, str(path)],
                check=False,
                capture_output=True,
            )
        except Exception:  # pragma: no cover - native/launchctl dependent
            logger.warning("launchctl %s failed for %s", verb, path, exc_info=True)
