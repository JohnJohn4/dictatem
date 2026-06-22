"""Pure tray hotkey-hint formatting — no Qt or OS imports (#104).

Turns the live ``[hotkey].modifiers`` config into the activation-chord label the
tray shows, formatted for the running platform: Windows spells the keys out
(``Win+Alt``) and keeps the configured order; macOS uses the modifier glyphs
(``⌥⌘``) in the platform's canonical ``⌃⌥⇧⌘`` order. ``win`` and ``meta`` are
aliases for the OS key (ADR-0010/0018). Pure logic so the full modifier matrix is
unit-tested; the menu wiring (``qt_tray``) is manual-QA.
"""

from __future__ import annotations

# Windows / generic word names, keyed by the canonical trigger-input name. The
# mouse side buttons and wheel click (ADR-0020) are trigger inputs too, so a
# standalone ``["mouse4"]`` renders a real label instead of a blank chord.
_WORD_NAMES = {
    "win": "Win", "meta": "Win", "alt": "Alt", "ctrl": "Ctrl", "shift": "Shift",
    "mouse4": "Mouse4", "mouse5": "Mouse5", "middle": "Middle",
}

# macOS glyphs, keyed by canonical modifier name.
_MAC_GLYPHS = {"win": "⌘", "meta": "⌘", "alt": "⌥", "ctrl": "⌃", "shift": "⇧"}

# The order macOS renders modifier glyphs in, regardless of config order.
_MAC_GLYPH_ORDER = ("⌃", "⌥", "⇧", "⌘")

# Mouse buttons have no standard glyph, so they keep a word label on macOS too,
# rendered after the modifier glyphs (e.g. ``⌃Mouse4``). At most one mouse button
# is ever in a combo (ADR-0020), so no separator is needed between them.
_MOUSE_LABELS = {"mouse4": "Mouse4", "mouse5": "Mouse5", "middle": "Middle"}


def format_hotkey(modifiers: tuple[str, ...], *, platform: str) -> str:
    """Format *modifiers* as a platform-appropriate chord string.

    macOS (``darwin``) renders the modifier glyphs in canonical ``⌃⌥⇧⌘`` order
    with no separator, with any mouse button appended as a word (``⌃Mouse4``);
    every other platform spells the names out joined by ``+`` in the configured
    order. Unknown names are dropped (config validation already rejects them); an
    empty or all-unknown set yields ``""`` so the tray hides the hint rather than
    showing an empty chord.
    """
    names = [name.lower() for name in modifiers]
    if platform == "darwin":
        glyphs = {_MAC_GLYPHS[name] for name in names if name in _MAC_GLYPHS}
        ordered = "".join(glyph for glyph in _MAC_GLYPH_ORDER if glyph in glyphs)
        mouse = "".join(_MOUSE_LABELS[name] for name in names if name in _MOUSE_LABELS)
        return ordered + mouse
    return "+".join(_WORD_NAMES[name] for name in names if name in _WORD_NAMES)


def hotkey_hint_label(modifiers: tuple[str, ...], *, platform: str) -> str:
    """The compact disabled-header label, e.g. ``Win+Alt to dictate``.

    States the activation chord and its purpose at a glance — narrow enough that
    it no longer drives the tray popup's width. The full hold-to-talk /
    tap-to-toggle teaching lives in the Usage Guide instead (CONTEXT.md /
    ADR-0019). Returns ``""`` when there is no usable chord, signalling the tray
    to hide the header item.
    """
    combo = format_hotkey(modifiers, platform=platform)
    if not combo:
        return ""
    return f"{combo} to dictate"
