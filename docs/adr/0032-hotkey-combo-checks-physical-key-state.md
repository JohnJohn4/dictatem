# The hotkey checks the physical key state before a combo can start

> Applies to the [Hotkey Combo](../../CONTEXT.md#hotkey-combo) classifier
> (ADR-0010/0018/0020). Shipped in v0.8.2 (#303).

Field bug, and a top reason users uninstalled: **Alt+Enter in Excel (or any
lone Alt) sometimes started a dictation.** It was intermittent, so the owner
couldn't reproduce it until the cause was known.

The classifier tracked held keys only from low-level hook events. A key-up the
hook never sees leaves that key "held" forever:

- **Win+L:** Win goes down on the user desktop, and its key-up happens on the
  secure (lock) desktop, which low-level hooks don't see.
- **Elevated windows:** a key released while an admin window has focus is
  invisible to a non-elevated hook (UIPI).

With Win stuck, any later Alt completed Win+Alt. Reproduced on demand on the
owner's laptop: Win+L, unlock, Alt+Enter → `Hotkey KEY_DOWN: IDLE -> PRESSED
[RECORD_START…]`.

## Decision

At the instant a key-down would **complete** the combo, the classifier asks the
OS whether the combo's *other* keys are physically down (Windows:
`GetAsyncKeyState`, high bit) and drops any that aren't (logged as `Hotkey:
ignored stale held key(s) …`). It's injected as `physical_state` and is `None`
on platforms without a query.

- Other key-downs are untouched, so ordinary typing pays nothing.
- An unknown state (`None`, unmapped key) trusts the event stream.
- The failure mode is safe: if the OS ever misreports a held key as up, that
  one press doesn't start a dictation (like a missed press). It can never
  cause a false start.

## Consequences

- Owner-verified: after Win+L, Alt+Enter is ignored (the stale `LEFT_META` is
  logged), and a real Win+Alt still records.
- A fuzz test (`tests/test_hotkey_stale_modifier.py`) of random typing with
  15% missed key-ups, never genuinely holding Win+Alt, went from 209/300
  sessions with a false dictation to 0/300. Genuine taps still fire after the
  noise.
- macOS has no equivalent query wired yet. Its hook sees lock-screen
  transitions differently; revisit if the bug is reported there.
