# Windows morning QA — release candidate `rc/2026-11-01`

Everything that's ready to ship, on one branch:

- **The launch work:** #205 visual refresh, #208 small fixes, #209 updater confirm, #223 Restart, plus the macOS PRs, which are inert on Windows.
- **Spec #225, reliability:** PR #262.
- **Spec #226, Trigger Words:** PR #265.
- **Spec #224, Apple-GPU:** PR #263. Mac-only, so nothing to see on Windows.

Tick each box. When something fails, note what you saw and grab the log (tray → **Show log**).
⏱️ About 60–75 minutes. Sections A–C are the launch gate; D–E are the two specs.

---

## 0. Setup (5 min)

1. **Quit the installed Dictatem.** Right-click its tray icon → **Quit**. Confirm nothing is left running (an empty result is good):
   ```powershell
   Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'dictatem' } | select ProcessId,CommandLine
   ```
   If anything is listed, run `Stop-Process -Id <id>` on it. Two copies running means every dictation pastes twice.
2. **Back up your config:**
   ```powershell
   Copy-Item ~\.dictatem\config.toml ~\.dictatem\config.backup.toml
   ```
3. **Get the build and run it:**
   ```powershell
   cd C:\Code\dictatem
   git fetch origin
   git checkout rc/2026-11-01
   uv sync --extra runtime-gpu --group dev
   uv run python -m dictatem
   ```
   Leave this PowerShell window open: the dev daemon runs in it, and Ctrl+C stops it.

## A. The new look (#205, plus the pill states from #262/#265) — 10 min

- [ ] **Tray menu:** right-click the icon. Rounded Windows 11 menu, sentence-case labels, separators between groups, your hotkey at the top, the version at the bottom.
- [ ] **Usage Guide:** tray → **How to use Dictatem…**
  - Your hotkey shows as big keycaps at the top.
  - There's a legend with six pill colours.
  - Switch Windows to Dark mode (Settings → Personalisation → Colours), close the guide and reopen it: it should be dark.
- [ ] **Pill while dictating:** a dark capsule with white bars following your voice. After you release, the bars turn amber and a wave moves across them.
- [ ] **Mint, "Saved — say paste":** start dictating in Notepad. While still holding the hotkey, Alt+Tab to another window, then release. The pill should show mint with the caption, and nothing is pasted. Click back into Notepad and say **paste** on its own: the text appears.
- [ ] **Busy caption:** dictate a long passage (20–30 s). While it's still amber, press the hotkey again. You should see "Still working — Esc cancels", and no new recording starts.
- [ ] **Colours:**
  - white: listening
  - amber: transcribing
  - violet: running a trigger word (section E)
  - coral: something failed
  - mint: saved
  - sky: say again (section E)

  Are the **six colours easy to tell apart**? Note any that look too alike: 

## B. Restart (#223) — 5 min

- [ ] In `~\.dictatem\config.toml`, change `[hotkey].modifiers` to a different combo, e.g. `["ctrl", "alt"]`, and save.
- [ ] Tray → **Restart**. The icon disappears and comes back within a few seconds, with no console window flashing.
- [ ] The **new** hotkey dictates **once**, with no double paste. The old hotkey does nothing.
- [ ] Put the hotkey back the way it was, then tray → **Restart** again.

## C. Everyday smoke test — 10 min

- [ ] **Hold to talk** into Notepad, Chrome, Word and VS Code. Each lands once, in the right place.
- [ ] **Tap to toggle:** tap, speak, tap. **Esc** while recording cancels it, and nothing is pasted.
- [ ] **Copy last dictation** in the tray puts your last text on the clipboard.
- [ ] Say **paste** on its own in a text box: it re-pastes your last dictation.
- [ ] **Updater (optional):** tray → **Check for updates…** says you're up to date. The "Install update?" dialog (#209) only appears when your version is older than the latest release. To see it:
  1. Change `version = "0.6.4"` to `"0.6.0"` in `pyproject.toml`.
  2. Ctrl+C the daemon, run `uv sync --extra runtime-gpu --group dev`, then `uv run python -m dictatem`.
  3. **Check for updates…** should show the dialog, with **Not now** highlighted. Click **Not now**: you get a "skipped" message and nothing runs.
  4. Revert the version with `git checkout pyproject.toml`, re-sync, and restart.

## D. Reliability (#262) — 20 min

- [ ] **Clipboard is kept.** Each time: copy the item, dictate into Notepad, then paste with **Ctrl+V** somewhere suitable. The original item should come back intact.
  - a screenshot (**Win+Shift+S**), pasted into Paint
  - files copied in Explorer, pasted into a folder
  - formatted text from a web page, pasted into Word
  - a large Excel range. Note how long the dictation takes to paste: 
- [ ] **Win+V history stays clean:** neither your dictations nor the restored items appear in it.
- [ ] **Esc during a slow transcription:** dictate about 30 s, press **Esc** while it's amber, then immediately dictate a short sentence. **Only the short sentence** should paste.
- [ ] **Config problems are reported, not destructive.**
  1. Set `tap_threshold_ms = "fast"` in config.toml, then tray → **Restart**. You should get **one** notification naming the bad value, and Dictatem still works.
  2. Now delete a closing `]` somewhere to make the file invalid, and Restart. Again one notification, and Dictatem still runs.
  3. With the broken file in place, toggle **Start at login**. Open config.toml: **your broken file is unchanged**, not overwritten.
  4. Restore your config: `Copy-Item ~\.dictatem\config.backup.toml ~\.dictatem\config.toml -Force`, then Restart.
- [ ] **Hotkey and mouse button** both still work after a Restart and after Quit plus a fresh start. If you use mouse4, test that too.
- [ ] **Unload during dictation:** start a long dictation, and while it's amber click tray → **Unload model**. The text still pastes, then the model unloads (`daemon.log` says the unload was deferred).
- [ ] **Trigger Fire with emoji and accents** (needs Ollama running): dictate "café déjà vu", say **polish**. The replacement leaves no stray characters and deletes nothing extra. Try it in Notepad, Chrome and Word.

## E. Trigger Words (#265) — 15 min

- [ ] **Quick "paste":** dictate something, click into another text box, press the hotkey and say "paste" **immediately and quickly**. It should paste, not type "haste".
- [ ] **Soft "summarise"** (needs Ollama): after a dictation, say "summarise" quietly and quickly. It should run (violet pill), or flash **sky blue** ("say again") if it wasn't sure. It must never type "some of us".
- [ ] **A real one-word dictation:** say "Summer." on its own. Note what happens; a sky "say again" flash is the accepted trade-off: 
- [ ] **Your own paste word:** add this to config.toml, then Restart:
  ```toml
  [trigger_words]
  paste_aliases = ["pasta"]
  ```
  Saying **pasta** on its own should re-paste your last dictation.
- [ ] **Sound-alike warning:**
  1. Create `~\.dictatem\prompts\palace.md` containing:
     ```
     ---
     aliases: [palace]
     ---
     Rewrite the text formally.
     ```
  2. Restart. tray → **Show log** should have a warning that "palace" sounds like "paste".
  3. Delete the file and Restart.
- [ ] The **say-again flash never steals focus:** your cursor stays where it was.

## When you're done

1. Ctrl+C the dev daemon. Restore your config if you haven't (`config.backup.toml`).
2. Go back to your normal install: `git checkout main`, then start **Dictatem** from the Start menu, or run `dictatem`.
3. Send back the ticked list, anything unticked with what you saw, and any log lines.

**If A–C pass,** the launch work is good to merge: PR #267, then close #205, #207–#211 and #223. **If D and E pass,** #262 and then #265 are ready (retarget #265 to `main` after #262 merges). #263 (Apple-GPU) waits for the Mac tester.
