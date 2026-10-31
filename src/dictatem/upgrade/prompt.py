"""Per-platform update path + the "update available" prompt content (#193) — pure.

Once a check finds a newer release, *what happens next* is a per-platform
decision, made here and nowhere else:

- ``IN_APP`` (Windows): Dictatem re-runs the pinned ``install.ps1`` for the user
  (``upgrade.win32_upgrader``) — the existing #100 path.
- ``MANUAL`` (macOS, phase 1 of #193): **nothing auto-executes.** The user gets
  a prompt carrying the pinned ``install.sh`` one-liner to copy into Terminal
  and a link to the README "Updating" section. A real in-app macOS upgrade
  (re-run ``install.sh`` with the stop-old-daemon dance) is phase 2, a
  separate follow-up.
- ``UNSUPPORTED``: no daemon/install path on this platform; the tray hides the
  item.

:class:`UpdatePrompt` is the shared shape of the user-facing *confirmation*
step — headline, body, the affirmative action's label — so an "Install
update?" confirmation for the ``IN_APP`` path can be built as a sibling of
:func:`manual_update_prompt` and shown by the same kind of Qt dialog, keeping
"what does the user agree to before anything happens" in one pure, tested
place for both platforms.

PURE: strings in, values out — no network, no Qt, no process I/O.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from dictatem.upgrade.core import GITHUB_REPO


class UpdateMode(enum.Enum):
    """How this platform turns "a newer release exists" into an update."""

    IN_APP = "in_app"
    MANUAL = "manual"
    UNSUPPORTED = "unsupported"


def update_mode_for(platform: str) -> UpdateMode:
    """The update path for *platform* (a ``sys.platform`` value)."""
    if platform == "win32":
        return UpdateMode.IN_APP
    if platform == "darwin":
        return UpdateMode.MANUAL
    return UpdateMode.UNSUPPORTED


# README anchor for the "Updating" section (one per platform inside it).
UPDATING_DOCS_URL = f"https://github.com/{GITHUB_REPO}#updating"


def install_sh_url(tag: str) -> str:
    """Raw-GitHub URL of ``install.sh`` pinned to *tag* (mirrors the README)."""
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{tag}/install.sh"


def install_sh_command(tag: str) -> str:
    """The documented macOS install/update one-liner, pinned to *tag*.

    Exactly the README's ``curl -fsSL … | sh`` form at the newer tag —
    re-running it is the supported macOS update path (ADR-0011/0015): it
    stops the running daemon, reinstalls the tool, refreshes the ``.app`` and
    the LaunchAgent, and relaunches under launchd.
    """
    return f"curl -fsSL {install_sh_url(tag)} | sh"


@dataclass(frozen=True)
class UpdatePrompt:
    """Content of the "update available" confirmation step."""

    title: str
    """Short headline (the dialog's bold line)."""

    text: str
    """What happens and what the user needs to do."""

    accept_label: str
    """Label of the affirmative button."""

    command: str | None
    """A command for the user to copy and run (``MANUAL``), else ``None``."""

    docs_url: str
    """Where the full update instructions live."""


def _display_version(version: str) -> str:
    return version if version.startswith("v") else f"v{version}"


def manual_update_prompt(current_version: str, tag: str) -> UpdatePrompt:
    """The macOS "update available" prompt: copy the command, run it yourself.

    Says plainly that Dictatem will not update itself, that the command is the
    same installer the user first ran (so it is safe while Dictatem runs),
    and that existing permission grants carry over.
    """
    current = _display_version(current_version) if current_version else "this version"
    return UpdatePrompt(
        title=f"Dictatem {_display_version(tag)} is available",
        text=(
            f"You have {current}. To update, copy the command below, paste it "
            "into Terminal, and press Return. It re-runs the installer for the "
            "new version and restarts Dictatem — your settings and permissions "
            "carry over."
        ),
        accept_label="Copy Update Command",
        command=install_sh_command(tag),
        docs_url=UPDATING_DOCS_URL,
    )


COMMAND_COPIED_NOTIFICATION = (
    "Update command copied",
    "Paste it into Terminal and press Return to update Dictatem.",
)
