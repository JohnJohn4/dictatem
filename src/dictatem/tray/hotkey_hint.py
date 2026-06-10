"""Pure tray hotkey-hint formatting — no Qt or OS imports (#104).

Turns the live ``[hotkey].modifiers`` config into the activation-chord label the
tray shows, formatted for the running platform: Windows spells the keys out
(``Win+Alt``) and keeps the configured order; macOS uses the modifier glyphs
(``⌥⌘``) in the platform's canonical ``⌃⌥⇧⌘`` order. ``win`` and ``meta`` are
aliases for the OS key (ADR-0010/0018). Pure logic so the full modifier matrix is
unit-tested; the menu wiring (``qt_tray``) is manual-QA.
"""

from __future__ import annotations

# Windows / generic word names, keyed by the canonical modifier name.
_WORD_NAMES = {"win": "Win", "meta": "Win", "alt": "Alt", "ctrl": "Ctrl", "shift": "Shift"}

# macOS glyphs, keyed by canonical modifier name.
_MAC_GLYPHS = {"win": "⌘", "meta": "⌘", "alt": "⌥", "ctrl": "⌃", "shift": "⇧"}

# The order macOS renders modifier glyphs in, regardless of config order.
_MAC_GLYPH_ORDER = ("⌃", "⌥", "⇧", "⌘")


def format_hotkey(modifiers: tuple[str, ...], *, platform: str) -> str:
    """Format *modifiers* as a platform-appropriate chord string.

    macOS (``darwin``) renders the modifier glyphs in canonical ``⌃⌥⇧⌘`` order
    with no separator; every other platform spells the names out joined by ``+``
    in the configured order. Unknown names are dropped (config validation already
    rejects them); an empty or all-unknown set yields ``""`` so the tray hides the
    hint rather than showing an empty chord.
    """
    names = [name.lower() for name in modifiers]
    if platform == "darwin":
        glyphs = {_MAC_GLYPHS[name] for name in names if name in _MAC_GLYPHS}
        return "".join(glyph for glyph in _MAC_GLYPH_ORDER if glyph in glyphs)
    return "+".join(_WORD_NAMES[name] for name in names if name in _WORD_NAMES)


def hotkey_hint_label(modifiers: tuple[str, ...], *, platform: str) -> str:
    """The full disabled-header label, e.g. ``Hotkey: Win+Alt (hold to talk …)``.

    Conveys both activation styles — hold-to-talk and tap-to-toggle — so a new
    user learns what to press and how. Returns ``""`` when there is no usable
    chord, signalling the tray to hide the header item.
    """
    combo = format_hotkey(modifiers, platform=platform)
    if not combo:
        return ""
    return f"Hotkey: {combo} (hold to talk · tap to toggle)"
