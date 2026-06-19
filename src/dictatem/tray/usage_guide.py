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
from typing import TYPE_CHECKING

from dictatem.tray.hotkey_hint import format_hotkey

if TYPE_CHECKING:
    from collections.abc import Sequence


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


def _trigger_words_section(trigger_words: Sequence[str]) -> str:
    section = (
        "<h3>Trigger words</h3>"
        "<p>Right after dictating, say a single word like <i>polish</i> or "
        "<i>summarize</i> on its own. Instead of typing it, Dictatem runs that "
        "word's transform and replaces what you just pasted with the result. It "
        "only fires in the <b>same window</b>, within a few minutes of the "
        "paste.</p>"
        "<p><b>Clean up your last dictation:</b> say <i>polish</i> on its own "
        "just after dictating and Dictatem rewrites what you pasted — removing "
        "filler and false starts and tightening the wording while keeping your "
        "meaning and voice. <i>summarize</i> condenses it instead. Both ship "
        "built in and need the Transform (Ollama) set up.</p>"
    )
    if trigger_words:
        words = ", ".join(html.escape(word) for word in trigger_words)
        section += f"<p><i>Your trigger words: {words}</i></p>"
    else:
        section += (
            "<p><i>You haven't added any trigger words yet — drop a prompt file "
            "in <code>~/.dictatem/prompts/</code>.</i></p>"
        )
    return section


def _recovery_section() -> str:
    return (
        "<h3>Recovering a lost dictation</h3>"
        "<p>If a dictation lands nowhere — you weren't focused on a text box — "
        "it isn't lost. Focus where it should have gone and say <i>paste</i> on "
        "its own to drop it in. You can also use <b>Copy last dictation</b> in "
        "this menu to put it on your clipboard.</p>"
    )


def _first_use_section() -> str:
    return (
        "<h3>First use</h3>"
        "<p>The first time you dictate or run a trigger word, Dictatem loads the "
        "matching model, which can take a few seconds. Use <b>Preload Model</b> "
        "in this menu to warm it up first.</p>"
    )


def usage_guide_html(
    modifiers: tuple[str, ...],
    *,
    platform: str,
    trigger_words: Sequence[str] = (),
) -> str:
    """Build the full Usage Guide document as an HTML string.

    The dictating section interpolates the live chord formatted for *platform*
    (Windows ``Win+Alt`` / macOS ``⌥⌘``); see ``format_hotkey``. *trigger_words*
    is the user's configured aliases (the daemon's alias map keys) — listed in
    the trigger-words section, or replaced by an empty-state pointer when none
    are configured.
    """
    combo = format_hotkey(modifiers, platform=platform)
    sections = [
        _dictating_section(combo),
        _trigger_words_section(trigger_words),
        _recovery_section(),
        _first_use_section(),
    ]
    return "<html><body>" + "".join(sections) + "</body></html>"
