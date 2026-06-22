"""Pure Usage Guide HTML builders — no Qt or OS imports.

The [Usage Guide](../../CONTEXT.md#usage-guide) is the read-only, offline,
in-app help window the tray's "How to use Dictatem…" item opens. Its content is
generated here as a single HTML string so the full matrix is unit-tested; the
Qt adapter (``qt_tray``) only hosts the window. The guide reflects the **live
configuration** — the actual Hotkey Combo via ``format_hotkey`` — so it can
never drift from what the user has set. See ADR-0019.

It grows by appending one section per feature: dictating, trigger words,
recovering a lost dictation, first-use model loading, and changing your hotkey.
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
        "<p>The speech model downloads <b>once</b>, on Dictatem's first run "
        "after install — a tray notification marks it. After that it works fully "
        "offline: every dictation, including the first, needs no network. (If "
        "you happen to be offline at that first run, the model downloads on your "
        "first dictation instead.)</p>"
        "<p>From then on the model loads when you <b>arm</b> a dictation, so the "
        "load overlaps the time you spend talking. If a load — or that one-time "
        "download — is still finishing, the pill shows a "
        "<b>Loading Dict. Model…</b> or <b>Downloading model…</b> caption and "
        "pastes automatically once it's ready, so you never press the hotkey "
        "again. Use <b>Preload Model</b> in this menu to warm it up ahead of "
        "time.</p>"
    )


def _changing_hotkey_section(modifiers: tuple[str, ...], platform: str) -> str:
    """The "Changing your hotkey" config-discoverability section (ADR-0022).

    Shows the live Hotkey Combo, names ``config.toml`` and the
    ``[hotkey].modifiers`` key, lists the curated vocabulary (modifiers + mouse
    buttons), and notes that a restart applies changes — Dictatem's in-app answer
    to "how do I change this?", since there is no settings UI. The vocabulary
    must stay in step with ``config.VALID_MODIFIER_NAMES`` (a test enforces it).
    """
    combo = html.escape(format_hotkey(modifiers, platform=platform))
    return (
        "<h3>Changing your hotkey</h3>"
        f"<p>Your dictation hotkey is <b>{combo}</b>. To change it, edit "
        "<code>config.toml</code> in <code>~/.dictatem/</code> (use "
        "<b>Open config file…</b> in this menu), set the "
        "<code>[hotkey].modifiers</code> list, then restart Dictatem to apply it "
        "(use <b>Restart</b> in this menu).</p>"
        "<p>Pick from this set — Dictatem has no free-form key binding:</p>"
        "<ul>"
        "<li><code>win</code> (or <code>meta</code>) — Windows key / ⌘ Command</li>"
        "<li><code>alt</code> — Alt / ⌥ Option</li>"
        "<li><code>ctrl</code> — Ctrl / Control</li>"
        "<li><code>shift</code> — Shift</li>"
        "<li><code>mouse4</code>, <code>mouse5</code> — the two side mouse buttons</li>"
        "<li><code>middle</code> — the mouse-wheel click</li>"
        "</ul>"
        "<p>Use one on its own (e.g. <code>[\"mouse4\"]</code>) or combine several "
        "(e.g. <code>[\"ctrl\", \"alt\"]</code>). Any other name is ignored and the "
        "default is kept.</p>"
        "<p><i>Heads up: some mice only report a click, not a held press. On those, "
        "a mouse-button trigger taps to toggle but can't hold-to-talk.</i></p>"
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
        _changing_hotkey_section(modifiers, platform),
    ]
    return "<html><body>" + "".join(sections) + "</body></html>"
