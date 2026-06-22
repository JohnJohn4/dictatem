# QA Handoff — Session S9: Overlay & focus UX (#96 #163 #97 #171)

> **STATUS: PASS (2026-06-23)** — run on Windows 11 (dev clone on `main` after
> #173/#174/#175). All four sections passed; **#96/#163/#97/#171 closed** with
> evidence. A — phase colours render (blue→white recording / amber / violet / red
> + loading caption, no dot; machine-verified via `QWidget.grab()` + live, Tap/Hold
> OK). B — pill never steals focus (objective `GetForegroundWindow` watch: Notepad
> held through recording; Win32 `WS_EX_NOACTIVATE`/`TRANSPARENT`/`TOPMOST` land;
> paste `target_id` tracks the real window). C — drift **held + recovered** via
> voice `paste` *and* tray copy (`Focus drifted … holding … for recovery`). D —
> staggered Win+Alt release activated no menu; Alt-alone still does. Follow-ups:
> recording hue reverted blue→white (06765e0); delayed-release edge → **#177**.
> Pure cores **1112 green**.

**Device required:** Windows 11, your usual microphone, and an app with a **menu
bar and a text caret** (Notepad is ideal for section D). A second window to click
into for section C. A GPU is handy for section C (a real cold load makes the drift
window wide) but not required — you can also just talk for a few seconds.
**Build under test:** **`main` after PRs #173 (#96/#163), #174 (#97), and #175
(#171) merge.** They're independent and merge clean; if they haven't all merged
yet, QA on a scratch branch that merges the three:
```
git checkout main
git merge feat/overlay-phase-colour-96-163 feat/focus-drift-detect-and-hold-97 feat/win-alt-menu-mask-171
```
Run from the **dev clone**, not the installed `dictatem` tool (the installed tool
is pinned to an older tag and lacks these changes).
**Why this is manual:** the pill is a Qt widget (colours/flags render only on a
real display); "the pill never steals activation" and "a lone Alt-up activates the
menu bar" are native window/OS behaviours; and the focus-drift hold depends on the
real foreground changing between record-start and paste. The pure cores — the
`OverlayState` phase→colour map, `focus_drifted()`, and the classifier's
`pending_mask` decision — are fully unit-tested; this checklist confirms the rest.

## Prerequisites
- **Stop the installed daemon first.** The dev clone and any installed build share
  the single-instance lock (`~/.dictatem/daemon.lock`, #92), so kill the installed
  daemon (Task Manager → `pythonw.exe`, or the installed tray's **Quit**) before
  launching the clone, or the clone just logs "Another Dictatem instance is already
  running" and exits. (See the dev-double-daemon note.)
- Launch the clone:
  ```
  cd C:\Code\dictatem
  uv run python -m dictatem
  ```
  Config is read once at startup and never rewritten by the app (ADR-0009).
- Log: tray **"Open log"**, or `%APPDATA%\Dictatem\logs\daemon.log`.
- Default hotkey is **Win+Alt** (Tap = toggle, Hold = push-to-talk).

## Checklist (run on the Windows machine)

### A — Overlay: phase by colour, no Status Dot (#96) (~4 min)
The red dot is gone; recording **phase is the pill's colour**. Hues are an
implementer call — current build: **recording = blue waveform**, **transcribing =
amber**, **a Transform computing = violet**, **model loading/downloading = a text
caption** with cycling dots.
- [ ] **Hold** Win+Alt and speak. **Expect:** a pill with a live **blue** waveform
      and **no red dot** anywhere. · **Issue:** #96
- [ ] Release. **Expect:** the pill turns to a static **amber** "processing"
      indicator while it transcribes, then pastes and fades. · **Issue:** #96
- [ ] **Tap** Win+Alt (quick press) to start a toggle recording, speak, Tap again
      to stop. **Expect:** same colours; **no** dot and **no** Tap/Hold "mode" dot
      shape (the cue was dropped — at most a subtle text, never a dot). · **Issue:** #96
- [ ] If the model is **cold** (tray **Unload Model** first), arm a dictation:
      **Expect:** the **"Loading Dict. Model…"** text caption (cycling dots), which
      flips to the amber transcribing colour once loaded. · **Issue:** #96 (with #74)
- [ ] *(Optional — needs Ollama + a Trigger Word configured.)* Dictate something,
      then say **"summarize"** (or your alias) **twice**. **Expect:** the first
      (cold) Trigger Fire shows the **"Loading LLM Model…"** caption; a second one
      within the keep-alive window shows the **violet "computing" colour** (not a
      caption — a warm generation is a phase, not a load). · **Issue:** #96

### B — Pill never steals activation (#163) (~3 min)
- [ ] Click into **Notepad** and leave the **text caret blinking**. Arm a dictation
      (Hold Win+Alt). **Expect:** when the pill appears, Notepad stays the active
      window and the **caret keeps blinking** — focus/activation is NOT taken by the
      pill. · **Issue:** #163
- [ ] While recording, **click around** on the desktop / other windows near the
      pill. **Expect:** the pill is click-through (clicks pass to whatever is under
      it) and never grabs focus. · **Issue:** #163
- [ ] Confirm the pill still appears **on top** and in the bottom-right of the
      active monitor. · **Issue:** #163

### C — Focus-drift detect-and-hold (#97) (~5 min)
Make the wait wide: tray **Unload Model** first (so the next dictation cold-loads),
or just keep talking for several seconds.
- [ ] Click into **window 1** (e.g. Notepad), arm a dictation, speak — then **click
      into window 2** (e.g. a browser address bar) **before** the text lands.
      **Expect:** the text is **NOT** pasted into window 2. The pill shows a brief
      **quiet flash** (no error *sound* — Dictatem has no sound surface), and your
      windows are **not** rearranged (no focus-restore). Log:
      `Focus drifted between record-start and paste … holding … for recovery`.
      · **Issue:** #97
- [ ] Now click back into **window 1** and say **"paste"**. **Expect:** the held
      text pastes into window 1. (Or use tray **"Copy last dictation"** → Ctrl+V.)
      · **Issue:** #97
- [ ] **Control:** arm, speak, and **don't** switch windows. **Expect:** it pastes
      normally into the same window, exactly as before. · **Issue:** #97

### D — Win+Alt chord release doesn't activate the menu bar (#171) (~4 min)
This is the bug found in S8 QA. Use **Notepad** (visible **File/Edit/…** menu bar)
and type some text so there's a caret in the body.
- [ ] Put the caret in the Notepad body. **Hold** Win+Alt, say a few words, and
      release the chord with a slight **stagger — let Win up a fraction before
      Alt.** **Expect:** the **File menu is NOT highlighted/activated**, the body
      caret stays put, and the dictation pastes **at the caret**. · **Issue:** #171
- [ ] Repeat releasing **Alt before Win** (reverse stagger). **Expect:** same — no
      menu activation, no Start menu pop, caret holds. · **Issue:** #171
- [ ] Repeat a few times at a natural pace (the bug is timing-dependent; count
      through a longer utterance and release casually). **Expect:** consistently no
      menu/Start activation. · **Issue:** #171
- [ ] **Regression:** plain dictation still works (tap toggles, hold push-to-talk),
      and pressing **Alt alone** still opens Notepad's menu bar normally (the mask
      only fires on a *combo* release, not a lone Alt tap). · **Issue:** #171

## What to capture
- A: a note/screenshot of each phase colour (blue recording / amber transcribing /
  violet computing if tested) and confirmation there is **no dot**.
- B: that the caret kept blinking when the pill appeared (a short screen capture is
  ideal).
- C: the `Focus drifted … holding … for recovery` log line, and that "paste"
  recovered the text into the right window.
- D: that the menu bar did **not** activate on a staggered release (the original
  bug was Notepad's **File** menu highlighting). Note GPU/CPU and how staggered the
  release was.
- Any failure: exact step, observed vs expected, and the app used.

## Gotchas
- **Stop the installed daemon first** (single-instance lock) or the clone exits.
- For C, the drift window is only as wide as the wait — with a warm model the paste
  is near-instant, so **unload the model first** (or talk longer) to have time to
  click away.
- #171 is **timing-dependent**: a perfectly simultaneous Win+Alt release may not
  reproduce the original bug at all. The fix should hold across *any* release order;
  if you can't repro the menu activation even on the pre-fix build, that's fine —
  the regression check (Alt-alone still opens the menu) is the key counter-test.
- A cold faster-whisper load can't be cancelled mid-flight (ADR-0016) — unrelated
  to these changes.

## On result
- **PASS** → comment the evidence on **#96**, **#163**, **#97**, **#171** and close
  them; mark QA done in the **S9 ledger** entry in `docs/agents/roadmap.md`.
- **FAIL** → comment the captured evidence on the relevant issue, keep it open, note
  the hypothesis. Likely suspects: a phase colour not rendering (overlay/tick
  wiring); the pill still taking focus (a window flag not applied on this Windows
  build — capture which); drift hold not triggering (the foreground `target_id`
  didn't actually change — some apps reuse one HWND across views, which is
  *window*-granular by design, #93 territory); or #171's mask not landing before the
  Alt-up on a very fast release. Don't silently drop.

## Carried over (still owed from earlier sessions)
- **#126** vocabulary recognition-lift — `qa-handoffs/02-vocabulary-recognition-qa.md`
  (real-model run on Windows; independent of S9).
