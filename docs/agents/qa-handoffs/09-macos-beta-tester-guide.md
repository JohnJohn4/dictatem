# Testing the Dictatem beta on your Mac 🎤

Thanks for testing **Dictatem**. It turns your voice into typed text anywhere on your
Mac: hold a hotkey, talk, let go, and your words appear wherever you're typing.

This is a **beta build** with a lot of new pieces: a smoother first-time setup, a
better speech model for Apple Silicon Macs, a refreshed look, and an update button.
Your job is the same as always:

1. **Do** what each step says.
2. **Look** at what happens.
3. **Write** what you saw in the boxes marked **✍️**.

Send back the filled-in guide (or just the **✍️** boxes and the summary at the
bottom). "This part was confusing" is a useful result too.

⏱️ **Time:** about 45 minutes. You can stop partway and send what you have.

> 💡 "**Dictate**" means: hold the hotkey, say a sentence, release. Your words should
> get typed in.

---

## A few basics (read once)

**▸ Terminal.** Press **⌘ + Space**, type **Terminal**, press **Return**. To run a
command: copy the whole gray box, paste into Terminal (**⌘ + V**), press **Return**,
and wait for the prompt to come back.

**▸ The hotkey** is **Option + Command** (**⌥ + ⌘**) held together.

**▸ The menu-bar icon** is Dictatem's small icon at the top-right of your screen,
near the clock. Clicking it opens Dictatem's menu.

**▸ `python3.12` is expected.** macOS settings will call Dictatem **`python3.12`**,
not "Dictatem". That's correct for this beta. Turn on `python3.12`.

---

## Part 1 — Start clean

If you tested Dictatem before, this clears the old version and its permissions so you
see exactly what a brand-new user sees. **Run it even if you're not sure.** Errors
like "not found" are fine.

```sh
dictatem --uninstall; uv tool uninstall dictatem; tccutil reset Accessibility; tccutil reset ListenEvent
```

**✍️ Done?** (yes / no): 

---

## Part 2 — Install the beta

```sh
curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/beta/mac-2026-10-31/install.sh | DICTATEM_REF=beta/mac-2026-10-31 sh
```

It downloads a few hundred megabytes and can take several minutes.

✅ **What you should see:**
- Near the end, a line like **"Waiting for Dictatem to start…"** with dots growing,
  instead of a long silent pause.
- Then the Dictatem icon appears in the menu bar.
- Then a short message saying **setup isn't finished** until you turn on two
  permissions and restart Dictatem.

**✍️ Your result — Install:**
- Saw the "Waiting…" line, then the icon, then the setup message? → **PASS** / **FAIL**: 
- Anything confusing or alarming in the text it printed: 

---

## Part 3 — Permissions 🔐 (the most important part)

About 2 seconds after the icon appears, Dictatem shows **two short dialogs**, one at a
time: first **Accessibility**, then **Input Monitoring**.

1. In each dialog click **Open System Settings**, find **`python3.12`**, and switch it
   **ON**.
2. Before turning on Input Monitoring, click the menu-bar icon. The top line of the
   menu should say **"Hotkey off — allow Input Monitoring"**.
3. Once both are on, click the menu-bar icon and choose **Restart**. The icon should
   disappear and come back within a few seconds.

✅ **What you should see:** exactly two dialogs (Input Monitoring must **not** appear
twice), short and easy to follow; the "Hotkey off" line before you allowed Input
Monitoring; Restart brings the icon back.

**✍️ Your result — Permissions:**
- Two dialogs, no duplicates? → **PASS** / **FAIL**: 
- "Hotkey off — allow Input Monitoring" shown before granting? → **PASS** / **FAIL**: 
- Restart from the menu worked? → **PASS** / **FAIL**: 
- Was the wording clear? What would you change? 

---

## Part 4 — First dictation, and speed ⏱️

1. Open **Notes**, click into a blank note.
2. Hold **⌥ + ⌘**, say *"Hello, this is my first test of the new beta."*, release.
3. The first time, macOS may ask for the **Microphone**: click **Allow**.
4. Now dictate **three more** sentences of about 5 seconds each. For each one,
   **roughly count the seconds** from releasing the keys until the text appears.

✅ **What you should see:** your words typed into the note. After the first one, each
should appear in **about 2 seconds or less**.

**✍️ Your result — First dictation:**
- Words typed in? → **PASS** / **FAIL**: 
- How long did the first one take to appear? ___ seconds
- The next three (roughly): ___ / ___ / ___ seconds
- Was the text accurate? Any words it got wrong: 
- Which Mac (menu  → About This Mac → Chip, e.g. "Apple M1"): 

---

## Part 5 — The new look 🎨

1. While dictating, look at the **pill** at the bottom-right of the screen.
   - While you talk: a dark rounded pill with **white bars** that move with your voice.
   - Right after you let go: the bars turn **amber** and a gentle wave moves across
     them while it works.
2. Click the menu-bar icon → **How to use Dictatem…**. A help window opens with your
   hotkey drawn as two big keys (**⌥** and **⌘**) at the top, and a colour legend for
   the pill.
3. Turn on **Dark Mode** ( → System Settings → Appearance → Dark), close the help
   window, and open it again from the menu.

**✍️ Your result — Look:**
- Pill looks right (rounded, white bars, amber wave after)? → **PASS** / **FAIL**: 
- Help window shows the ⌥ ⌘ keys and colour legend? → **PASS** / **FAIL**: 
- Help window switches to dark in Dark Mode? → **PASS** / **FAIL**: 
- Does anything look ugly, cut off or hard to read? 

---

## Part 6 — Everyday tests

### Test A — Tap to start/stop, and Esc to cancel
1. In a blank note, **tap** ⌥ + ⌘ once (quick press and release). Say *"This is a tap
   test."* Tap once more to stop. Your words should be typed in.
2. Tap once again, say something, then press **Esc** instead of stopping.

**✍️** Tap worked? **PASS** / **FAIL**: · Esc cancelled, nothing typed? **PASS** / **FAIL**: 

### Test B — Two different apps
Open **Notes** and **TextEdit**. Dictate one sentence into each, clicking into each
app first.

**✍️** Each sentence landed in the right app? **PASS** / **FAIL**: 

### Test C — Right after a restart 🔁
1. Open Safari or Chrome, click into any text box (a search box is fine).
2. Menu-bar icon → **Restart**. Wait for the icon to come back.
3. Right away, dictate a short sentence into the browser box, **6 times in a row**.
   Count how many appear.
4. Do the same 6 times into **Notes**.

**✍️** Browser: ___ / 6 · Notes: ___ / 6 · If any went missing, which ones? 

### Test D — When a permission is missing
1.  → System Settings → Privacy & Security → **Accessibility** → turn
   **`python3.12` OFF**.
2. Dictate into a note.
3. You should see a dialog saying **Dictatem couldn't paste** and asking you to allow
   Accessibility. Close it.
4. Click the menu-bar icon → **Copy last dictation**, then click into the note and press
   **⌘ + V**. Your sentence should paste in.
5. Turn **`python3.12` back ON**, then menu-bar icon → **Restart**.

**✍️** Saw the "couldn't paste" dialog? **PASS** / **FAIL**: · Copy last dictation
recovered the text? **PASS** / **FAIL**: 

### Test E — Survives a log out
Log out ( → Log Out) and back in. Don't change anything. Check the menu-bar icon is
back, dictate a sentence, and check the menu shows **"Start at login"** with a
checkmark.

**✍️** Came back and worked with no setup? **PASS** / **FAIL**: · "Start at login"
checked? **PASS** / **FAIL**: 

### Test F — Reinstall doesn't duplicate
Run the install command from Part 2 again. There should still be **one** Dictatem icon
and **no** permission dialogs this time.

**✍️** One icon, no dialogs? **PASS** / **FAIL**: 

---

## Part 7 — Grab the log (please always do this)

This tells us which speech model your Mac picked and when it downloaded. Paste this
into Terminal, press Return, and copy everything it prints into your reply:

```sh
grep -E "starting|tier|model|fetch|download" ~/Library/Logs/Dictatem/daemon.log | tail -n 40
```

---

## Part 8 — Uninstall *(do this LAST)*

```sh
dictatem --uninstall
```

```sh
uv tool uninstall dictatem
```

**✍️** Icon gone, no errors? **PASS** / **FAIL**: 

---

## 📋 Summary to send back

| # | Test | PASS / FAIL / SKIP |
|---|------|--------------------|
| 1 | Install (waiting line + setup message) | |
| 2 | Permissions: two dialogs, "Hotkey off" line, Restart | |
| 3 | First dictation + speed (___ s first, ~___ s after) | |
| 4 | New look: pill, help window, dark mode | |
| A | Tap + Esc | |
| B | Two apps | |
| C | After restart: browser ___/6, Notes ___/6 | |
| D | Missing permission: dialog + Copy last dictation | |
| E | Survives log out + "Start at login" | |
| F | Reinstall = one icon, no dialogs | |
| 7 | Log pasted | |
| 8 | Uninstall | |

**Anything else you noticed or found confusing?**


Thank you! 🙏

---
<sub>**For the Dictatem team (testers can ignore):** Build under test is branch
`beta/mac-2026-10-31` = `main` + PRs #205 (visual refresh), #207 (Apple-Silicon tier),
#208 + #209 (pre-launch fixes, updater confirm — Windows-facing), #210 (#95 onboarding),
#211 (#193 macOS update prompt), #223 (#212 Restart), with conflicts resolved (macOS
Restart uses #223's `relaunch` seam + `MANUAL_RELAUNCH_HINT`). Mapping: Part 2 = #210
installer wait; Part 3 = #210 dialogs/hotkey-off/Restart; Part 4 = #207 latency
(revert to `base` if warm 5 s clips are much over ~2 s); Part 5 = #205; Test D = #210
re-prompt-on-use; Test C = #93; Tests A/B/E/F/8 = #94 runbook; Part 7 = #207 tier +
#213 (first-run fetch skipped?). **Not covered:** #211's update prompt needs an
installed version older than the latest release — QA it separately via branch
`qa/193-fake-old-version` per PR #211's steps.</sub>
