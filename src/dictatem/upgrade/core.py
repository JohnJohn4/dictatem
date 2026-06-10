"""Pure upgrade-decision core (#100).

The tray "Check for Updates" action resolves the latest GitHub release tag and
decides whether to upgrade the running install. Every decision here is pure: the
version parse/compare, the release-JSON parse, the upgrade decision, and the
install-one-liner URL take strings and return values with no network or process
I/O, so the whole table is unit-testable on any OS. The GitHub fetch
(``upgrade.github``) and the detached upgrade spawn (``upgrade.win32_upgrader``)
are the thin adapters around this core, verified by manual QA.

Upgrading itself stays ADR-0011/0015-faithful: there is no bundled updater — the
upgrade re-runs the documented ``install.ps1`` one-liner at the newer tag, which
stops the running daemon (the same ``…\\Scripts`` file-lock fix as #98), picks
the correct GPU/CPU extra, installs the tag's tarball, and relaunches.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass

# The GitHub repository the release check and install one-liner target.
GITHUB_REPO = "JohnJohn4/dictatem"


def parse_version(text: str) -> tuple[int, ...] | None:
    """Parse a ``vX.Y.Z`` / ``X.Y.Z`` tag into a comparable int tuple.

    Tolerates a leading ``v``. Returns ``None`` for anything that is not a plain
    dotted run of integers (an empty string, a pre-release suffix like
    ``v0.4.0-rc1``, a moving tag like ``nightly``) so callers treat an
    unrecognised version as "unknown" rather than guessing a partial compare.
    """
    if not text:
        return None
    stripped = text[1:] if text[0] in "vV" else text
    parts = stripped.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer(candidate: str, current: str) -> bool:
    """True when release tag *candidate* is strictly newer than *current*.

    Both are parsed with :func:`parse_version`; if either is unparseable the
    answer is ``False`` — we never claim an upgrade we can't verify (e.g. when
    our own installed version can't be read). Shorter versions are zero-padded so
    ``0.4`` and ``0.4.0`` compare equal.
    """
    cand = parse_version(candidate)
    cur = parse_version(current)
    if cand is None or cur is None:
        return False
    width = max(len(cand), len(cur))
    cand_padded = cand + (0,) * (width - len(cand))
    cur_padded = cur + (0,) * (width - len(cur))
    return cand_padded > cur_padded


def parse_latest_tag(release_json: str) -> str | None:
    """Extract ``tag_name`` from a GitHub ``releases/latest`` JSON body.

    Returns ``None`` for an empty body, malformed JSON, a missing ``tag_name``,
    or a non-string tag — every failure collapses to "couldn't determine the
    latest tag", which the decision surfaces as an UNKNOWN result.
    """
    if not release_json:
        return None
    try:
        data = json.loads(release_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    tag = data.get("tag_name")
    return tag if isinstance(tag, str) and tag else None


class UpgradeKind(enum.Enum):
    """Outcome of comparing the running version to the latest release."""

    UPGRADE_AVAILABLE = "upgrade_available"
    UP_TO_DATE = "up_to_date"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UpgradeDecision:
    """What the tray should do after a check, plus the message to show."""

    kind: UpgradeKind
    message: str
    tag: str | None = None


def _display_version(current: str) -> str:
    """Render the running version for a message, with a single leading ``v``."""
    return current if current.startswith("v") else f"v{current}"


def decide_upgrade(current_version: str, latest_tag: str | None) -> UpgradeDecision:
    """Decide what the tray Upgrade action should do.

    * No / unparseable *latest_tag* → ``UNKNOWN`` (the check couldn't complete).
    * *latest_tag* strictly newer than *current_version* → ``UPGRADE_AVAILABLE``,
      carrying the tag to install.
    * Otherwise (same, or a dev build ahead of the latest release) →
      ``UP_TO_DATE``.
    """
    if latest_tag is None or parse_version(latest_tag) is None:
        return UpgradeDecision(
            kind=UpgradeKind.UNKNOWN,
            message="Couldn't check for updates. See the Releases page on GitHub.",
        )
    if is_newer(latest_tag, current_version):
        return UpgradeDecision(
            kind=UpgradeKind.UPGRADE_AVAILABLE,
            message=f"Updating to {latest_tag} — Dictatem will restart.",
            tag=latest_tag,
        )
    return UpgradeDecision(
        kind=UpgradeKind.UP_TO_DATE,
        message=f"Dictatem is up to date ({_display_version(current_version)}).",
    )


def install_one_liner_url(tag: str) -> str:
    """Raw-GitHub URL of ``install.ps1`` pinned to *tag* (mirrors the README).

    Re-running this one-liner is the documented upgrade path (ADR-0011/0015): no
    bundled updater, just the same provisioning script at a newer tag.
    """
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{tag}/install.ps1"
