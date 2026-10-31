"""Pure Usage Guide HTML builders — no Qt or OS imports.

The [Usage Guide](../../CONTEXT.md#usage-guide) is the read-only, offline,
in-app help window the tray's "How to use Dictatem…" item opens. Its content is
generated here as a single HTML string so the full matrix is unit-tested; the
Qt adapter (``qt_tray``) only hosts the window. The guide reflects the **live
configuration** — the actual Hotkey Combo via ``format_hotkey`` — so it can
never drift from what the user has set. See ADR-0019.

Layout: the live hotkey drawn as keycaps opens the page (the one thing every
user must learn), followed by the two recording modes, a legend for the pill's
phase colours, then one section per feature. Styling uses only the subset of
CSS Qt rich text supports (no border-radius, no flex), and the palette follows
the OS light/dark scheme via :data:`LIGHT` / :data:`DARK`.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dictatem.overlay.state import HELD_CAPTION, PILL_BODY_HEX, PILL_HEX, PillColor
from dictatem.tray.hotkey_hint import format_hotkey, hotkey_keys

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class GuideTheme:
    """The guide's colour tokens (pill swatches come from ``overlay.state``)."""

    page: str
    text: str
    muted: str
    rule: str
    keycap: str
    keycap_edge: str
    chip: str
    code: str


LIGHT = GuideTheme(
    page="#FAFBFC",
    text="#20232A",
    muted="#5F6573",
    rule="#E3E6EC",
    keycap="#FFFFFF",
    keycap_edge="#BCC2CE",
    chip="#EDEFF4",
    code="#3B4FA8",
)

DARK = GuideTheme(
    page="#1D2027",
    text="#E7E9EE",
    muted="#9AA1AE",
    rule="#343842",
    keycap="#2B2F38",
    keycap_edge="#4C5260",
    chip="#2B2F38",
    code="#A9B6FF",
)

# The pill's phase hues come straight from the overlay's pure palette, so the
# legend can never drift from what the widget paints. Swatches sit on the pill's
# dark body colour (recording is white) rather than the page.
PILL_BODY = PILL_BODY_HEX
PILL_HUES = {
    "recording": PILL_HEX[PillColor.ACCENT],
    "transcribing": PILL_HEX[PillColor.PROCESSING],
    "computing": PILL_HEX[PillColor.COMPUTING],
    "held": PILL_HEX[PillColor.HELD],
    "say_again": PILL_HEX[PillColor.SAY_AGAIN],
    "error": PILL_HEX[PillColor.ERROR],
}


def _h(theme: GuideTheme, text: str) -> str:
    return (
        f'<h3 style="color:{theme.text}; font-size:13pt; font-weight:600; '
        f'margin-top:22px; margin-bottom:6px;">{text}</h3>'
    )


def _p(theme: GuideTheme, body: str, *, muted: bool = False) -> str:
    colour = theme.muted if muted else theme.text
    return f'<p style="color:{colour}; margin-top:0; margin-bottom:8px;">{body}</p>'


def _code(theme: GuideTheme, text: str) -> str:
    return f'<code style="color:{theme.code};">{text}</code>'


def _chips(theme: GuideTheme, words: Sequence[str]) -> str:
    cells = "".join(
        f'<td style="background-color:{theme.chip}; padding:2px 8px;">'
        f"{html.escape(word)}</td>"
        for word in words
    )
    return f'<table cellspacing="4" cellpadding="0"><tr>{cells}</tr></table>'


def _keycaps(theme: GuideTheme, keys: Sequence[str], combo: str) -> str:
    """The live hotkey as large keycaps — the guide's opening element.

    Each key is a bordered table cell (Qt rich text has no border-radius); a
    muted ``+`` joins them on Windows, while macOS glyph chords sit side by side
    as the platform writes them. The full combo string is carried in the table's
    ``title`` so the plain chord text (``Win+Alt``) is always present.
    """
    joiner = "" if any(len(k) == 1 for k in keys) else "+"
    cells: list[str] = []
    for i, key in enumerate(keys):
        if i and joiner:
            cells.append(
                f'<td style="color:{theme.muted}; font-size:16pt; padding:0 2px;">'
                f"{joiner}</td>"
            )
        cells.append(
            f'<td style="background-color:{theme.keycap}; color:{theme.text}; '
            f"border:1px solid {theme.keycap_edge}; border-bottom:3px solid "
            f'{theme.keycap_edge}; font-size:17pt; font-weight:600; '
            f'padding:6px 14px;">{html.escape(key)}</td>'
        )
    return (
        f'<table title="{html.escape(combo)}" cellspacing="6" cellpadding="0" '
        f'style="margin-top:4px; margin-bottom:10px;"><tr>{"".join(cells)}</tr></table>'
    )


def _dictating_section(theme: GuideTheme, combo: str, keys: Sequence[str]) -> str:
    c = html.escape(combo)
    rows = (
        ("Hold to talk", f"Hold {c} while you speak, then release. Dictatem "
         "transcribes and pastes the moment you let go. Best for quick phrases."),
        ("Tap to toggle", f"Tap {c} to start recording hands-free, then tap "
         "again to stop. Best for longer dictation."),
    )
    table = "".join(
        f'<tr><td style="color:{theme.text}; font-weight:600; padding:0 14px 8px 0;" '
        f'width="112">{name}</td><td style="color:{theme.text}; padding:0 0 8px 0;">'
        f"{desc}</td></tr>"
        for name, desc in rows
    )
    return (
        f'<p style="color:{theme.muted}; margin-bottom:0;">Your dictation hotkey '
        f"is <b>{c}</b></p>"
        + _keycaps(theme, keys or [combo], combo)
        + f'<table cellspacing="0" cellpadding="0">{table}</table>'
        # #240: a press mid-work gets a "Still working" caption, not a new take.
        + _p(
            theme,
            f"{c} is ignored while Dictatem is working on your last dictation — "
            "the pill briefly shows <i>Still working</i>. <b>Esc</b> cancels.",
            muted=True,
        )
    )


def _pill_section(theme: GuideTheme) -> str:
    rows = (
        ("recording", "Listening — the bars follow your voice"),
        ("transcribing", "Turning your speech into text"),
        ("computing", "Running a trigger word"),
        (
            "held",
            f"<b>{HELD_CAPTION}</b> — your dictation was kept instead of pasted; "
            "focus where it belongs and say <i>paste</i>",
        ),
        (
            "say_again",
            "<b>Say again</b> — that sounded close to a trigger word but Dictatem "
            "wasn't sure, so nothing was pasted; just say it again",
        ),
        (
            "error",
            "Didn't catch that — nothing to paste",
        ),
    )
    body = "".join(
        f'<tr><td style="background-color:{PILL_BODY}; padding:2px 8px;">'
        f'<span style="color:{PILL_HUES[key]}; font-size:11pt;">▮▮▮</span></td>'
        f'<td style="color:{theme.text}; padding:0 0 0 10px;">{label}</td></tr>'
        for key, label in rows
    )
    return (
        _h(theme, "The pill")
        + _p(
            theme,
            "While recording, a pill appears in the corner of your screen. Its "
            "colour tells you what Dictatem is doing:",
        )
        + f'<table cellspacing="0" cellpadding="0" style="margin-bottom:6px;">{body}</table>'
    )


def _trigger_words_section(
    theme: GuideTheme, trigger_words: Sequence[str], paste_aliases: Sequence[str]
) -> str:
    section = (
        _h(theme, "Trigger words")
        + _p(
            theme,
            "Right after dictating, say a single word like <i>polish</i> or "
            "<i>summarize</i> on its own. Instead of typing it, Dictatem runs that "
            "word's transform and replaces what you just pasted with the result. "
            "It only fires in the <b>same window</b>, within a few minutes of the "
            "paste.",
        )
        + _p(
            theme,
            "<b>Clean up your last dictation:</b> say <i>polish</i> on its own "
            "just after dictating and Dictatem rewrites what you pasted — removing "
            "filler and false starts and tightening the wording while keeping your "
            "meaning and voice. <i>summarize</i> condenses it instead. Both ship "
            "built in and need the Transform (Ollama) set up.",
        )
        # #248: the Borderline outcome and its workaround.
        + _p(
            theme,
            "<b>Say again:</b> if a short word sounds <i>close to</i> a trigger "
            "word but Dictatem isn't sure, the pill flashes the say-again colour "
            "and nothing is pasted — your last dictation is kept, so just say the "
            "trigger word again, clearly. If a real one-word dictation (say, "
            "<i>Summer.</i>) trips it, dictate it inside a longer phrase instead.",
            muted=True,
        )
    )
    if trigger_words:
        section += _p(theme, "Your trigger words:", muted=True) + _chips(
            theme, trigger_words
        )
    else:
        section += _p(
            theme,
            "You haven't added any trigger words yet — drop a prompt file in "
            + _code(theme, "~/.dictatem/prompts/")
            + ".",
            muted=True,
        )
    if paste_aliases:
        # [trigger_words].paste_aliases (#250): the user's own words for the
        # built-in `paste` action.
        section += _p(
            theme, "Words that also mean <i>paste</i>:", muted=True
        ) + _chips(theme, paste_aliases)
    return section


def _recovery_section(theme: GuideTheme) -> str:
    return _h(theme, "Recovering a lost dictation") + _p(
        theme,
        "If a dictation lands nowhere — you weren't focused on a text box — it "
        "isn't lost. Focus where it should have gone and say <i>paste</i> on its "
        "own to drop it in. You can also use <b>Copy last dictation</b> in the "
        "tray menu to put it on your clipboard.",
    )


def _first_use_section(theme: GuideTheme) -> str:
    return (
        _h(theme, "First use")
        + _p(
            theme,
            "The speech model downloads <b>once</b>, on Dictatem's first run after "
            "install — a tray notification marks it. After that it works fully "
            "offline: every dictation, including the first, needs no network. (If "
            "you happen to be offline at that first run, the model downloads on "
            "your first dictation instead.)",
        )
        + _p(
            theme,
            "From then on the model loads when you <b>arm</b> a dictation, so the "
            "load overlaps the time you spend talking. If a load — or that "
            "one-time download — is still finishing, the pill shows a "
            "<b>Loading Dict. Model…</b> or <b>Downloading model…</b> caption and "
            "pastes automatically once it's ready, so you never press the hotkey "
            "again. Use <b>Preload model</b> in the tray menu to warm it up ahead "
            "of time.",
        )
    )


def _changing_hotkey_section(
    theme: GuideTheme, modifiers: tuple[str, ...], platform: str
) -> str:
    """The "Changing your hotkey" config-discoverability section (ADR-0022).

    Shows the live Hotkey Combo, names ``config.toml`` and the
    ``[hotkey].modifiers`` key, lists the curated vocabulary (modifiers + mouse
    buttons), and notes that a restart applies changes — Dictatem's in-app answer
    to "how do I change this?", since there is no settings UI. The vocabulary
    must stay in step with ``config.VALID_MODIFIER_NAMES`` (a test enforces it).
    """
    combo = html.escape(format_hotkey(modifiers, platform=platform))
    names = (
        ("win", "(or " + _code(theme, "meta") + ") Windows key / ⌘ Command"),
        ("alt", "Alt / ⌥ Option"),
        ("ctrl", "Ctrl / Control"),
        ("shift", "Shift"),
        ("mouse4", "and " + _code(theme, "mouse5") + " — the two side mouse buttons"),
        ("middle", "the mouse-wheel click"),
    )
    rows = "".join(
        f'<tr><td style="padding:1px 12px 1px 0;">{_code(theme, name)}</td>'
        f'<td style="color:{theme.text}; padding:1px 0;">{desc}</td></tr>'
        for name, desc in names
    )
    return (
        _h(theme, "Changing your hotkey")
        + _p(
            theme,
            f"Your dictation hotkey is <b>{combo}</b>. To change it, edit "
            + _code(theme, "config.toml")
            + " in "
            + _code(theme, "~/.dictatem/")
            + " (use <b>Open config file…</b> in the tray menu), set the "
            + _code(theme, "[hotkey].modifiers")
            + " list, then restart Dictatem to apply it (use <b>Restart</b> in the "
            "tray menu). Pick from this set — Dictatem has no free-form key "
            "binding:",
        )
        + f'<table cellspacing="0" cellpadding="0" style="margin-bottom:8px;">{rows}</table>'
        + _p(
            theme,
            "Use one on its own (e.g. "
            + _code(theme, '["mouse4"]')
            + ") or combine several (e.g. "
            + _code(theme, '["ctrl", "alt"]')
            + "). Any other name is ignored and the default is kept.",
        )
        + _p(
            theme,
            "Some mice only report a click, not a held press. On those, a "
            "mouse-button trigger taps to toggle but can't hold-to-talk.",
            muted=True,
        )
    )


def usage_guide_html(
    modifiers: tuple[str, ...],
    *,
    platform: str,
    trigger_words: Sequence[str] = (),
    paste_aliases: Sequence[str] = (),
    dark: bool = False,
) -> str:
    """Build the full Usage Guide document as an HTML string.

    The dictating section interpolates the live chord formatted for *platform*
    (Windows ``Win+Alt`` / macOS ``⌥⌘``); see ``format_hotkey``. *trigger_words*
    is the user's configured aliases (the daemon's alias map keys) — listed in
    the trigger-words section, or replaced by an empty-state pointer when none
    are configured. *paste_aliases* is the live ``[trigger_words].paste_aliases``
    (#250), listed beside them when non-empty. *dark* selects the
    :data:`DARK` palette to match the OS.
    """
    theme = DARK if dark else LIGHT
    combo = format_hotkey(modifiers, platform=platform)
    keys = hotkey_keys(modifiers, platform=platform)
    sections = [
        _dictating_section(theme, combo, keys),
        _pill_section(theme),
        _trigger_words_section(theme, trigger_words, paste_aliases),
        _recovery_section(theme),
        _first_use_section(theme),
        _changing_hotkey_section(theme, modifiers, platform),
    ]
    return (
        f'<html><body style="background-color:{theme.page}; color:{theme.text}; '
        f'font-size:10.5pt;">' + "".join(sections) + "</body></html>"
    )
