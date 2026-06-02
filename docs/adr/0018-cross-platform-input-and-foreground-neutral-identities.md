# Cross-platform input and foreground Protocols reason in neutral identities

Bringing Dictatem to macOS (#51) exposed two OS seams that looked
platform-neutral but were secretly Windows-shaped: the "pure" hotkey classifier
matched **Windows virtual-key codes**, and the Last Paste safety rail compared a
**window handle named `hwnd`**. macOS delivers neither (a CGEventTap reports
macOS key codes; there is no integer HWND). Rather than fake Windows values
inside the macOS adapters, both seams are generalised so the shared logic is
genuinely OS-agnostic and the per-platform translation lives — pure and
unit-tested — in each adapter. This refines [ADR-0010](0010-hotkey-modifiers-are-configurable.md).

## Decision

**Hotkey input → neutral `Key` identities.** The `KeyboardHook` callback and
`HotkeyClassifier` no longer traffic in raw OS key codes. A small
platform-neutral `Key` enum (`META`, `ALT`, `CTRL`, `SHIFT`, `ESCAPE`, the
arrows) is the classifier's vocabulary. Each hook owns a **pure** map from its
native codes to `Key`: the Windows hook maps `0x5B → Key.META`, `0x1B →
Key.ESCAPE`, …; the macOS hook maps `0x37 → Key.META`, `0x35 → Key.ESCAPE`, ….
`config.toml` gains `meta` as the canonical name for the OS key, with `win` kept
as a permanent alias, so existing `["win","alt"]` configs are unchanged and the
default chord is Win+Alt on Windows / Option+Command on macOS (see the
**Hotkey Combo** entry in `CONTEXT.md`).

**Foreground identity → `target_id: int`.** `ForegroundTracker.capture()`,
`LastPaste.hwnd`, and the rail parameter are renamed `hwnd → target_id` and kept
typed `int` — an opaque equality token, not "a window handle". The Windows
adapter still returns the HWND; the macOS adapter returns the frontmost app's
**PID** (`NSWorkspace.frontmostApplication.processIdentifier`). The rail
(`rails_ok`) is unchanged: it still compares two ints.

## Considered options

- **Fake Windows values in the macOS adapters.** Have the CGEventTap emit
  Windows VK integers (Command → `0x5B`) and use a window id as the `hwnd`.
  Smallest diff, but it bakes a lie into code labelled "pure", and a Mac user
  configuring `["win","alt"]` to mean Command+Option is baffling. Rejected.
- **Per-platform code tables injected into the classifier.** Keeps the
  classifier thinking in raw ints but swaps the constant set by platform. Two
  parallel tables drift and the classifier never becomes truly neutral.
  Rejected in favour of one neutral vocabulary.
- **`CGWindowID` for a true same-window macOS rail.** Gives window-level parity
  with Windows but requires the **Screen Recording** TCC permission — a fourth
  grant and real first-run friction — for a marginal safety gain. Rejected for
  v1.
- **Generalise the foreground identity to an opaque `Hashable`** (e.g. an
  AXUIElement window ref). Most precise without Screen Recording, but it is a
  second cross-cutting type change and AX window refs are the least
  CI-verifiable piece. Rejected; `int` (a PID) is enough for an equality token.

## Consequences

- The macOS Last Paste rail is **app-granular, not window-granular**: a Trigger
  Fire after switching to a different window of the *same* macOS app still
  passes the same-target rail. Accepted as the right v1 trade-off; a precise
  per-window identity is a possible follow-up.
- Both generalisations touch the **Windows** path (its hook now emits `Key`
  identities; `hwnd` is renamed `target_id`), so they are fully exercised and
  regression-tested on Windows/CI before any macOS hardware exists — the bulk of
  the macOS input/paste design is validated without a Mac.
- The neutral `Key` map and each platform's native→`Key` translation are pure
  and unit-tested; only the live event tap / PID lookup is manual-QA, consistent
  with how native adapters are treated elsewhere.
- `meta`/`win` are interchangeable in config forever; dropping `win` later would
  be a breaking change and is explicitly not planned.
