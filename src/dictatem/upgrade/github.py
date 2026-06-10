"""Fetch the latest GitHub release tag (thin network adapter).

A small urllib wrapper around the GitHub ``releases/latest`` endpoint; the JSON
parse and every decision live in the pure :mod:`dictatem.upgrade.core`. Kept thin
on purpose — the only behaviour here is "make the HTTPS request, hand the body to
the pure parser" — so the live request is verified by manual QA while the parsing
is unit-tested. Any network failure propagates to the caller, which treats it as
"couldn't check" (an UNKNOWN decision).
"""

from __future__ import annotations

import urllib.request

from dictatem.upgrade.core import GITHUB_REPO, parse_latest_tag


def fetch_latest_tag(*, repo: str = GITHUB_REPO, timeout_s: float = 6.0) -> str | None:
    """Return the latest release ``tag_name`` for *repo*, or ``None``.

    ``None`` means the response had no usable tag. A network/HTTP error is raised
    (the caller's worker thread turns any exception into an UNKNOWN decision), so
    the tray never blocks longer than *timeout_s*.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "dictatem-update-check",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        body = response.read().decode("utf-8")
    return parse_latest_tag(body)
