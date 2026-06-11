"""Pure Usage Guide HTML builders — no Qt or OS imports.

The [Usage Guide](../../CONTEXT.md#usage-guide) is the read-only, offline,
in-app help window the tray's "How to use Dictatem…" item opens. Its content is
generated here as a single HTML string so the full matrix is unit-tested; the
Qt adapter (``qt_tray``) only hosts the window. The guide reflects the **live
configuration** — the actual Hotkey Combo via ``format_hotkey`` — so it can
never drift from what the user has set. See ADR-0019.

It grows by appending one section per feature; v1 covers dictating and
first-use model loading.
"""

from __future__ import annotations

import html

from dictatem.tray.hotkey_hint import format_hotkey


def _dictating_section(combo: str) -> str:
    c = html.escape(combo)
    return (
        "<h3>Dictating</h3>"
        f"<p><b>{c}</b> is your dictation hotkey.</p>"
        f"<p><b>Hold to talk</b> — Hold {c} while you speak, then release. "
        "Dictatem transcribes and pastes the moment you let go. "
        "Best for quick phrases.</p>"
        f"<p><b>Tap to toggle</b> — Tap {c} to start recording hands-free, then "
        "tap again to stop. Best for longer dictation.</p>"
        "<p><i>While recording, a pill appears in the corner of your screen.</i></p>"
    )


def _first_use_section() -> str:
    return (
        "<h3>First use</h3>"
        "<p>The first time you dictate or run a trigger word, Dictatem loads the "
        "matching model, which can take a few seconds. Use <b>Preload Model</b> "
        "in this menu to warm it up first.</p>"
    )


def usage_guide_html(modifiers: tuple[str, ...], *, platform: str) -> str:
    """Build the full Usage Guide document as an HTML string.

    The dictating section interpolates the live chord formatted for *platform*
    (Windows ``Win+Alt`` / macOS ``⌥⌘``); see ``format_hotkey``.
    """
    combo = format_hotkey(modifiers, platform=platform)
    sections = [_dictating_section(combo), _first_use_section()]
    return "<html><body>" + "".join(sections) + "</body></html>"
