# Hotkey modifiers are configurable and honoured by the classifier

`[hotkey].modifiers` in `config.toml` was parsed and round-tripped correctly
but **never wired into the classifier** — the daemon always triggered on
Win+Alt regardless of what was configured. This ADR records the fix.

## Decision

`HotkeyClassifier` now accepts a `modifiers: tuple[str, ...]` parameter
(default `("win", "alt")`). In `__init__` the names are resolved once to a
list of VK groups using a `{"win": WIN_VKS, "alt": ALT_VKS, "ctrl": CTRL_VKS,
"shift": SHIFT_VKS}` mapping. `combo_held` returns `True` iff **every
resolved group** has at least one key currently pressed.

`_start_windows_daemon()` passes `modifiers=config.hotkey.modifiers` into the
classifier so the configured set is honoured at runtime.

`config.py` validates modifier names on load: any tuple where at least one
element is not in `{"win", "alt", "ctrl", "shift"}`, or that reduces to empty
after filtering, is rejected with a `WARNING` log and replaced by the default
`("win", "alt")`. A typo therefore never silently disables the hotkey.

## Considered options

- **Empty-groups always-true guard.** `all([])` is `True` in Python, so an
  empty resolved-groups list would make `combo_held` permanently `True` and
  fire the hotkey on every key event. We guard explicitly: if
  `_modifier_groups` is empty, `combo_held` returns `False` — the hotkey is
  effectively disabled rather than always triggered.
- **Partial-name filtering (accept known, drop unknown).** Would silently
  shorten `["win", "turbo"]` to `["win"]`, giving a single-modifier combo the
  user did not intend. Rejected in favour of a strict "all-or-nothing" fallback
  that logs a warning.
- **Remove the field entirely.** Considered as fix option (b) in issue #44.
  Rejected because the field already round-trips correctly and per-user hotkeys
  are a reasonable want.

## Consequences

- Default behaviour is unchanged: Win+Alt still activates recording out of the
  box.
- Users can configure any combination of `win`, `alt`, `ctrl`, and `shift` as
  their activation chord; a single-modifier config (e.g. `["ctrl"]`) is valid.
- Unknown modifier names or an empty list fall back to `("win", "alt")` with a
  logged warning — a typo never silently changes or disables the hotkey.
- The classifier is pure logic with no OS dependency, so the full modifier
  matrix is unit-tested without mocking.
