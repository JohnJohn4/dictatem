# QA Handoff — Session S6: Windows mouse hook (#120 / ADR-0020)

> **STATUS: PASSED — 2026-06-22**, Windows 11 on a Logitech MX Master 3S (all
> phases below + keyboard regression). Evidence on #120. Kept as the regression
> checklist for future native-hook changes and the macOS mouse hook (#121).

**Device required:** Windows 11, with a real Whisper model + your usual
microphone, and a **mouse with side buttons** (Mouse4/Mouse5) and a wheel click.
For the suppression checks you also need a **browser** (Mouse4 = browser-back by
default).
**Build under test:** PR **#159** (branch `feat/windows-mouse-hook-120`), or
`main` once it merges. Run from the **dev clone**, not the installed `dictatem`
tool (the installed tool is pinned to an older tag and won't contain this work).
**Why this is manual:** `SetWindowsHookEx(WH_MOUSE_LL)` and whether a *physical*
side button (your mouse + its driver) actually emits `WM_XBUTTON*`, plus whether
suppression truly blocks browser-back, can't be machine-verified. The pure
decision logic (keymap, conditional suppression, Tap/Hold) is already unit-tested,
and a **synthetic `SendInput` smoke test passed locally** (the live hook decoded
injected middle/X1/X2 events correctly) — this confirms the rest on real hardware.

## Prerequisites
- **Stop the installed daemon first.** The dev clone and the installed build share
  the single-instance lock (`~/.dictatem/daemon.lock`, #92), so if the installed
  daemon (a `pythonw.exe`) is running, the clone will just log "Another Dictatem
  instance is already running" and exit. Kill the installed one (Task Manager →
  `pythonw.exe`, or the installed tray's Quit) before launching the clone. See the
  dev-double-daemon note.
- Edit `C:\Users\johnc\.dictatem\config.toml`, set the combo under test (see each
  section), then launch:
  ```
  cd C:\Code\dictatem
  uv run python -m dictatem
  ```
  Restart the daemon after each config edit (config is read once at startup;
  the app never rewrites it — ADR-0009).
- Log: tray **"Open log"**, or `%APPDATA%\Dictatem\logs\daemon.log`.

## Checklist (run on the Windows machine)

### A — Standalone `["mouse4"]` (~5 min)
Set `[hotkey] modifiers = ["mouse4"]`, restart.
- [ ] Open the tray menu. **Expect:** the header reads **"Mouse4 to dictate"** (not
      blank). Open **"How to use Dictatem…"**: the Dictating section says **Mouse4**
      is your hotkey. · **Issue:** #120
- [ ] In a browser with history to go back to, focus a text box. **Tap** Mouse4,
      speak, tap again. **Expect:** dictation records (pill appears) and pastes;
      the browser does **not** navigate back. · **Issue:** #120
- [ ] **Hold** Mouse4, speak, release. **Expect:** push-to-talk records while held,
      transcribes + pastes on release; still no browser-back. · **Issue:** #120
- [ ] (Suppression) On a page where Mouse4 would normally go back, just tap Mouse4
      once and watch the address bar. **Expect:** no back-navigation — every Mouse4
      press is the trigger now and is suppressed. · **Issue:** #120

### B — `mouse5` and `middle` standalone (~3 min)
- [ ] Set `["mouse5"]`, restart, repeat a tap-to-dictate. **Expect:** Mouse5 arms
      dictation; its normal action (forward) is suppressed. Header shows
      **"Mouse5 to dictate"**. · **Issue:** #120
- [ ] Set `["middle"]`, restart, tap the **wheel click** over a text box. **Expect:**
      it arms dictation; no middle-click paste / autoscroll fires. Header shows
      **"Middle to dictate"**. (Heads-up: in a browser, middle-click-to-open-tab is
      what's being suppressed.) · **Issue:** #120

### C — Combined `["ctrl", "mouse4"]` — conditional suppression (~4 min)
Set `[hotkey] modifiers = ["ctrl", "mouse4"]`, restart. This is the key ADR-0020
behaviour: the button is suppressed **only** while it completes the combo.
- [ ] **Bare** Mouse4 (no Ctrl) in a browser. **Expect:** browser **goes back** as
      normal — a bare press is NOT suppressed and does NOT arm dictation. · **Issue:** #120
- [ ] **Ctrl held + Mouse4**, focus a text box. **Expect:** dictation arms (tap or
      hold as in A); the browser does **not** go back. Release. · **Issue:** #120
- [ ] Header shows **"Ctrl+Mouse4 to dictate"**. · **Issue:** #120

### D — No keyboard regression + degrade note (~2 min)
- [ ] Set the combo back to the default `["win", "alt"]` (or your usual), restart.
      Confirm the **keyboard** hotkey still arms dictation exactly as before (tap +
      hold). **Expect:** unchanged. · **Issue:** #120 (regression guard)
- [ ] (Informational, only if your mouse is "click-only") If a side button reports
      just a click and not a sustained hold, **hold-to-talk won't engage** but
      **tap-to-toggle still works** — this is the documented graceful degrade
      (ADR-0020), not a bug. The Usage Guide says so.

## What to capture
- The tray header label for each standalone combo (`Mouse4`/`Mouse5`/`Middle` to
  dictate) — a screenshot or note.
- Confirmation that bare Mouse4 still navigates back under `["ctrl","mouse4"]`,
  but Ctrl+Mouse4 arms dictation with no back-navigation.
- Any `daemon.log` lines around a mouse trigger (recording start/stop, paste).
- If anything misfires: the exact combo, the observed vs expected, and the mouse
  model (some vendor mice remap side buttons in their own driver and may not emit
  standard `WM_XBUTTON*`).

## Gotchas
- **Stop the installed daemon first** (single-instance lock), or the clone exits.
- Config is read **once at startup** — restart after every `modifiers` edit.
- Some gaming-mouse drivers (Logitech/Razer/etc.) intercept side buttons or remap
  them to keystrokes; if Mouse4 does nothing, check the vendor software isn't
  swallowing it (this is the hardware caveat the synthetic smoke test can't cover).
- `["ctrl","mouse4"]`: the suppression is conditional, so a near-simultaneous
  Ctrl+Mouse4 chord pressed within the same ~50 ms tick *could* let one
  browser-back slip through before the combo registers — hold Ctrl first (the
  natural gesture) and it's reliable.

## On result
- **PASS** → comment the evidence on **#120** and close it; mark QA done in the
  **S6 ledger** entry in `docs/agents/roadmap.md`.
- **FAIL** → comment the captured evidence on **#120**, keep it open, note the
  hypothesis. Likely suspects: a vendor driver swallowing the side button (hardware,
  not our bug); the `MSLLHOOKSTRUCT` decode if the *wrong* button maps (would also
  fail the synthetic smoke — unlikely); or the suppression return path if
  browser-back still fires while armed. Don't silently drop.
