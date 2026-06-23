# QA Handoff — Session 10: macOS QA & polish (#94 #93 #121 #95)

**Device required:** real Mac — Apple Silicon (arm64), ideally also Intel. macOS 12+.
**Build under test:**
- **#94 runbook + #93 watch:** the **released v0.6.0** (no new code needed) —
  `curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.6.0/install.sh | sh`.
- **#121 + #95:** a **dev build of the session branch** (the agent will provide the
  exact install step once the code is on a branch — typically
  `uv tool install --managed-python --python 3.12 'git+https://github.com/JohnJohn4/dictatem@<branch>#egg=dictatem[runtime]'`
  then the macOS app/LaunchAgent bootstrap). Don't QA #121/#95 against v0.6.0.
**Why this is manual:** CGEventTap / Cocoa / TCC permission grants are not
machine-verifiable, and #93 proves logs can lie (a clean `Paste: sent` whose text
never landed). Pure logic is already unit-tested + CI-checked; this confirms
**observable behaviour on the device.**

## ⚠️ How this QA runs — REMOTE RELAY (read first)

The agent is on **Windows** and cannot touch the Mac. A **separate person on the
Mac** runs everything. The loop is: **agent writes a command block → the user
relays it → the Mac tester runs it in Terminal and reports what they SAW + pastes
the output → the user pastes it back → the agent interprets.**

- The tester runs blocks **verbatim, one at a time**, and reports the **observable
  result** (did the text appear? did the menu bar icon show? did the button arm
  dictation?) — **not just** the log. Logs are captured **in addition**.
- **Nothing is marked PASS without the tester confirming the observable behaviour.**
- The hotkey on macOS is **⌘+⌥ (Cmd+Opt)**.

### macOS launch rules the tester must follow (every time)
- Relaunch the daemon ONLY with:
  `launchctl kickstart -k gui/$(id -u)/com.dictatem.daemon`
- **Never** launch from Spotlight / `~/Applications/Dictatem.app` (kills the menu
  bar icon) or a bare terminal `dictatem` (kills hotkey/paste — grants attach to
  the terminal app).
- Permission entries are listed as **`python3.12`** (not "Dictatem") in System
  Settings → Privacy & Security → **Accessibility** and **Input Monitoring**.
- A newly-granted permission **takes effect after a relaunch** (kickstart again).

## Prerequisites (relay to the tester)
- A Mac with admin rights to flip Accessibility + Input Monitoring grants.
- For **Trigger Fire** (#94 item E): Ollama running + `ollama pull gemma4:e2b`
  (the default `[transform].model_name`; `gemma4:e2b` is deliberate, not a typo —
  see `hardware/resolver.py`. If the user pinned a larger tag, pull that instead).
- For **#121**: a mouse with extra buttons (mouse4/mouse5) and/or a clickable wheel.

### Reusable command block — Capture logs (relay whenever logs are asked for)
```
echo "----- $(date) -----"; tail -n 80 ~/Library/Logs/Dictatem/daemon.log
```
To watch live during a repro: `tail -f ~/Library/Logs/Dictatem/daemon.log`
(Ctrl-C to stop), then paste the relevant lines back.

---

## Part 1 — #94 macOS runbook (run FIRST; no new code; uses v0.6.0)

Re-proves the platform and closes #94. Tester ticks each; report observable result
+ logs.

- [ ] **D — Hotkey semantics:** tap ⌘+⌥ to start, tap again to stop → text
      transcribes + pastes. Then start a recording and press **Esc** → recording
      cancels with **no paste**. · **Expect:** tap-toggle works; Esc = no text. · **Issue:** #94
- [ ] **E — Paste rails (app switch):** dictate into app A, then click into app B
      and dictate → each lands in the **right** window. · **Expect:** no cross-window
      bleed. · **Issue:** #94
- [ ] **E — Trigger Fire (needs Ollama):** with a Trigger Word configured, fire it →
      the `replace_chars > 0` typed path (no clipboard) replaces text; confirm
      cold-load timeout behaves. · **Expect:** transform lands via typing. · **Issue:** #94
- [ ] **F — Login persistence:** log out / back in → daemon **auto-starts via
      launchd**, hotkey works with **no re-grant**; the **"Start at Login"** tray
      toggle is visible/checked. · **Expect:** works after relogin, no re-grant. · **Issue:** #94
- [ ] **G — Uninstall:** `dictatem --uninstall` then `uv tool uninstall dictatem` →
      removes the `.app` + LaunchAgent + tool. Confirm no orphaned job:
      `launchctl print gui/$(id -u)/com.dictatem.daemon` → should report **not
      found**. · **Expect:** clean removal. · **Issue:** #94
- [ ] **Single-instance (#92):** reinstall over a running daemon → `install.sh`'s
      stop-old-daemon prevents duplicates (one menu-bar icon). · **Expect:** no
      double daemon. · **Issue:** #94 (relates #92)

## Part 2 — #93 paste-not-landing watch (run alongside Part 1; v0.6.0)

- [ ] Kickstart the daemon: `launchctl kickstart -k gui/$(id -u)/com.dictatem.daemon`,
      then **immediately** do **5–8 dictations into a browser web input** (e.g. a
      Claude/Google text box). Report **how many of the first few landed** vs the
      log. · **Expect (hypothesis):** the first 1–2 may silently drop then it
      stabilises; the log shows a clean `Paste: sent` even on the misses. · **Issue:** #93
- [ ] Repeat into a **native** app text field (TextEdit) right after a kickstart →
      does the same drop happen, or only in the browser? (Isolates focus-race vs.
      CGEventPost warm-up.) · **Issue:** #93

**What to capture for #93:** the `Paste: captured … / clipboard set … / Paste: sent`
block for each miss, the app/target, and the gap between attempts. If it does NOT
reproduce, say so — that's also data (it was non-deterministic in the original).

## Part 3 — #121 macOS mouse hook (ONLY after the code lands + CI green)

Build: the session branch dev build. Config a mouse button, e.g.
`~/.dictatem/config.toml` → `[hotkey] modifiers = ["mouse4"]` (standalone) or
`["cmd", "mouse4"]` (combined); kickstart after editing.

- [ ] **Standalone** (`["mouse4"]`): press mouse4 → dictation arms (Tap/Hold);
      the button's **normal action is suppressed** while it completes the combo. · **Expect:** arms + suppressed. · **Issue:** #121
- [ ] **Combined** (`["cmd","mouse4"]`): a **bare** mouse4 press does its normal
      action; **⌘+mouse4** arms **and** suppresses. · **Expect:** only suppressed
      with ⌘ held. · **Issue:** #121
- [ ] **Wheel click** (`["middle"]`) arms + is suppressed. · **Issue:** #121
- [ ] **Keyboard regression:** the existing ⌘+⌥ keyboard hotkey still works
      unchanged. · **Expect:** no regression. · **Issue:** #121

## Part 4 — #95 first-run onboarding (ONLY after the code lands + CI green)

Build: the session branch dev build, on a Mac (or user) with **grants revoked** to
simulate first-run. Revoke `python3.12` from Accessibility + Input Monitoring first.

- [ ] **Setup-in-progress signal:** run the installer → the final message makes
      clear setup isn't done until the **menu-bar icon + permission prompts**
      appear (and the first hotkey press won't work until grants are in). · **Expect:**
      no "looks finished" gap confusion. · **Issue:** #95
- [ ] **Re-prompt on use (no silent fail):** with Input Monitoring **missing**,
      press the hotkey → the guided dialog surfaces (deep-linked) instead of a
      no-op; with Accessibility **missing**, attempt a paste → guided dialog. Verify
      it's **throttled** (doesn't nag on every keystroke). · **Expect:** guidance,
      not silence; no nag. · **Issue:** #95
- [ ] **Dialog copy:** the permission dialog is **shorter/action-first**, keeps the
      "Open System Settings" deep-link + one "takes effect after a relaunch" line. · **Expect:**
      concise copy. · **Issue:** #95

---

## What to capture (overall)
- Per item: **PASS/FAIL + what the tester SAW** (the observable result), plus the
  relevant log lines from the capture block.
- For any FAIL: exact repro steps, the app/target, screenshots if useful, and the
  full `Paste:`/event log window around the failure.

## On result
- **PASS** (tester confirmed the observable behaviour) → comment the evidence on the
  issue and close it; tick it here.
- **FAIL / not run** → comment the captured evidence; keep the issue open with the
  hypothesis; leave the item unticked here. **Never close on logs alone or without
  the tester running it.**
- When the session ends, the driving agent records results here + in the roadmap
  S10 ledger, and rewrites the Current Session Prompt.
