# Testing Dictatem on your Mac 🎤

Thanks for helping test **Dictatem** — a little app that turns your voice into typed
text anywhere on your Mac. You hold a hotkey, talk, and your words appear in
whatever you're typing into.

This guide walks you through it **one step at a time**. You don't need to be
technical — just:

1. **Do** what each step says.
2. **Look** at what happens.
3. **Write** what you saw in the box marked **✍️**.

When you're done, send the whole filled-in guide back (or just the **✍️** boxes and
the summary at the very bottom). If you get stuck or something is confusing, that's
useful too — just write it down and move on.

⏱️ **Time:** about 30–45 minutes. You can stop partway and send back what you have.

> 💡 Throughout, "**dictate**" means: hold the hotkey, say a sentence out loud, then
> release — and your words should get typed out for you.

---

## What you'll need

- A Mac (either the newer **Apple Silicon** kind or an older **Intel** one — both are fine).
- Permission to change settings on the Mac (an admin account).
- A working microphone (the built-in one is fine).
- About 30–45 minutes.

---

## A few basics first (please read once)

You'll be copying a few **commands** into an app called **Terminal**. Here's all you
need to know:

**▸ How to open Terminal**
1. Press **Command (⌘) + Space** to open Spotlight search.
2. Type **Terminal** and press **Return**.
3. A window with a text prompt opens. Leave it open — you'll use it a few times.

**▸ How to run a command**
- Copy the whole gray box, click into the Terminal window, paste (**⌘ + V**), and
  press **Return**.
- Some commands print a lot of text or take a minute. That's normal — wait until the
  text stops and you see a fresh prompt line again.

**▸ The hotkey**
- Dictatem's hotkey is **Option + Command** — that's the **⌥** key and the **⌘** key,
  held together. (Option is sometimes labelled **alt**.)
- **Hold** them while you talk, then **release** to type out your words.

**▸ The menu-bar icon**
- Once installed, Dictatem shows a small **icon at the top-right of your screen** (the
  menu bar, near the clock and Wi-Fi). Clicking it opens Dictatem's menu.

---

## Part 1 — Install Dictatem

1. Open **Terminal** (see above).
2. Copy this command, paste it into Terminal, and press **Return**:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.6.0/install.sh | sh
   ```

3. Wait. It downloads a few hundred megabytes and can take **several minutes**. Lots
   of text will scroll by — that's fine. It's finished when it prints something like
   **"Dictatem is starting in the menu bar"** and you get a normal prompt back.

✅ **What you should see:** the install finishes without a big red error, and a small
**Dictatem icon appears at the top-right of your screen** (the menu bar).

**✍️ Your result — Part 1 (Install):**
- Did it finish and show the menu-bar icon? → write **PASS** or **FAIL**: 
- What you saw (or any error text): 

---

## Part 2 — Turn on permissions 🔐 (the important part)

macOS won't let an app type for you or hear the hotkey until **you** allow it. Dictatem
will pop up dialog boxes that **walk you through this** — please follow them.

> ⚠️ **Very important:** in the macOS settings, the item you're allowing will be called
> **`python3.12`** — **not** "Dictatem". **That is correct and expected.** Turn on
> `python3.12`.

**Follow Dictatem's pop-ups:**
1. Soon after install, Dictatem shows a dialog about **Accessibility** with a button
   that opens System Settings to the right place. Click it, find **`python3.12`** in
   the list, and switch it **ON**.
2. It then does the same for **Input Monitoring**. Find **`python3.12`** and switch it
   **ON**.
3. After turning each one on, **restart Dictatem** so the change takes effect. Copy
   this into Terminal and press Return:

   ```sh
   launchctl kickstart -k gui/$(id -u)/com.dictatem.daemon
   ```

**If you don't see the pop-ups**, set it by hand:
- Open  **Apple menu → System Settings → Privacy & Security**.
- Go to **Accessibility** → turn **`python3.12`** ON.
- Go to **Input Monitoring** → turn **`python3.12`** ON.
- If `python3.12` isn't in the list yet, that's OK — it appears after Dictatem first
  tries to use it. Try the hotkey once, then look again.
- Then run the restart command above.

✅ **What you should see:** you were able to turn on **`python3.12`** for both
**Accessibility** and **Input Monitoring**.

**✍️ Your result — Part 2 (Permissions):**
- Were you able to turn both on? → **PASS** or **FAIL**: 
- Was anything confusing or unclear about the pop-ups / wording? (be honest — this is
  exactly what we're testing): 

---

## Part 3 — Your first dictation (quick check)

1. Open the **Notes** app (or any app you can type in) and click into a blank note so
   the cursor is blinking.
2. **Hold** **Option (⌥) + Command (⌘)**, say clearly: *"Hello, this is my first test."*,
   then **release** the keys.
3. The **first time** you do this, macOS may ask to use the **Microphone** — click
   **Allow**. The very first dictation can also take **10–30 seconds** to get ready —
   after that it's quick.

✅ **What you should see:** your spoken sentence gets **typed into the note**.

**✍️ Your result — Part 3 (First dictation):**
- Did your words get typed in? → **PASS** or **FAIL**: 
- What you saw: 

> If this didn't work, the most common reason is a permission from Part 2 didn't take
> effect — run the restart command from Part 2 once more and try again. If it still
> fails, note it here and carry on to grab a log at the end.

---

# The tests

Please do these in order. Each one is short.

---

### Test 1 — Tap to start/stop, and Esc to cancel

This checks two things: that you can **tap** (instead of hold) to record, and that
**Esc** throws away a recording.

1. Click into a blank note.
2. **Tap** Option + Command **once** (a quick press and release — don't hold). It
   should start listening.
3. Say: *"This is a tap to toggle test."*
4. **Tap** Option + Command **once more** to stop. Your words should get typed in.
5. Now start again: tap once and say something — but this time press the **Esc** key
   before stopping normally.

✅ **What you should see:** tapping starts and stops recording (step 4 types your
words); pressing **Esc** (step 5) cancels it and **nothing gets typed**.

**✍️ Your result — Test 1:**
- Tap-to-start/stop worked? → **PASS** or **FAIL**: 
- Esc cancelled with nothing typed? → **PASS** or **FAIL**: 
- What you saw: 

---

### Test 2 — Typing into two different apps

This checks your words always land in the **right** window.

1. Open **two** apps you can type in — for example **Notes** and **TextEdit** (or
   Notes and a Mail message). Put them side by side if you can.
2. Click into the **first** app and dictate a sentence (hold ⌥⌘, talk, release).
3. Now click into the **second** app and dictate a different sentence.

✅ **What you should see:** the first sentence lands in the first app, and the second
sentence lands in the second app — **nothing ends up in the wrong window**.

**✍️ Your result — Test 2:**
- Did each sentence land in the right app? → **PASS** or **FAIL**: 
- What you saw: 

---

### Test 3 — The "right after a restart" check 🔁

We're checking a specific worry: whether the **first few** dictations right after
restarting might silently go missing — especially in a **web browser** text box.

1. Open a **web browser** (Safari or Chrome) and go to any page with a text box you
   can type in (a search box, a Google Doc, a chat box, etc.). Click into it.
2. Restart Dictatem by pasting this into Terminal and pressing Return:

   ```sh
   launchctl kickstart -k gui/$(id -u)/com.dictatem.daemon
   ```

3. **Right away**, dictate a short sentence into that browser text box. Then do it
   again. Do this **6 times in a row**, one after another.
4. **Count** how many of the 6 actually showed up on screen.
5. Now do the same thing **6 times into the Notes or TextEdit app** (a normal Mac app,
   not a browser) and count again.

✅ **What you should see:** ideally all 6 land both times. We specifically want to know
if the **first one or two in the browser** go missing right after the restart.

**✍️ Your result — Test 3:**
- In the **browser**: how many of 6 showed up? → ___ / 6
- In **Notes/TextEdit**: how many of 6 showed up? → ___ / 6
- If any went missing, which ones (e.g. "the first 2") and what did you see (nothing
  appeared? something flashed?): 

---

### Test 4 — Trigger Words *(optional — skip unless you're comfortable)*

This feature uses extra software (**Ollama**) that needs separate setup, so **it's
fine to skip this one**. If you'd like to try it, reply and we'll send you simple
setup steps.

**✍️ Your result — Test 4:**
- Skipped, or tried it? → **SKIPPED** / **PASS** / **FAIL**: 
- (if you tried it) What you saw: 

---

### Test 5 — Does it survive a logout/restart?

This checks Dictatem comes back on its own after you log out or restart the Mac.

1. **Log out** of your Mac (Apple menu → Log Out), then **log back in**. *(Restarting
   the Mac works too.)*
2. After logging back in, **don't** reinstall or change anything. Just look at the
   menu bar, then open Notes and dictate a sentence (hold ⌥⌘, talk, release).
3. Click the **Dictatem menu-bar icon** and look for a **"Start at Login"** item — it
   should be there with a **checkmark**.

✅ **What you should see:** the menu-bar icon is back by itself, dictation works
**without** you re-doing any permissions, and **"Start at Login"** is checked.

**✍️ Your result — Test 5:**
- Did it come back and work after logging in, with no re-setup? → **PASS** or **FAIL**: 
- Is "Start at Login" present and checked? → **PASS** or **FAIL**: 
- What you saw: 

---

### Test 6 — Reinstalling doesn't create a duplicate

1. With Dictatem already running, run the **install command from Part 1 again** (paste
   it into Terminal, press Return, wait for it to finish).
2. Look at the menu bar.

✅ **What you should see:** there is still **only ONE** Dictatem icon in the menu bar —
not two.

**✍️ Your result — Test 6:**
- Still only one icon? → **PASS** or **FAIL**: 
- What you saw: 

---

### Test 7 — Uninstalling cleanly *(do this LAST — it removes the app)*

1. Run these **two** commands, one at a time (paste, Return, wait, then the next):

   ```sh
   dictatem --uninstall
   ```

   ```sh
   uv tool uninstall dictatem
   ```

2. *(Optional double-check)* run this — it should say it **could not find** the
   service (that's the good result, meaning it's fully gone):

   ```sh
   launchctl print gui/$(id -u)/com.dictatem.daemon
   ```

✅ **What you should see:** the **menu-bar icon disappears** and Dictatem is removed,
with no errors.

**✍️ Your result — Test 7:**
- Did it remove cleanly (icon gone, no errors)? → **PASS** or **FAIL**: 
- What you saw (and the result of the optional check, if you ran it): 

---

## 🪵 If something went wrong: grab a log

For any test that **failed**, this helps us a lot. Two easy options:

**Option A — the menu (easiest):** click the **Dictatem menu-bar icon** and choose
**"Show Log"**. A window opens with the log — select all the text (**⌘ + A**), copy
(**⌘ + C**), and paste it into your reply, saying which test it was for.

**Option B — Terminal:** paste this in, press Return, then copy everything it prints:

```sh
tail -n 60 ~/Library/Logs/Dictatem/daemon.log
```

*(If you already uninstalled in Test 7, the log may be gone — that's OK.)*

---

## 📋 Quick summary to send back

Fill this in and send it back along with the **✍️** boxes above. Just write **PASS**,
**FAIL**, or **SKIP** next to each.

| # | Test | Your result (PASS / FAIL / SKIP) |
|---|------|----------------------------------|
| 1 | Install | |
| 2 | Permissions | |
| 3 | First dictation | |
| 4 | Tap to start/stop + Esc cancels | |
| 5 | Lands in the right app (two apps) | |
| 6 | Right-after-restart: browser ___/6, Notes ___/6 | |
| 7 | Trigger Words (optional) | |
| 8 | Survives logout/restart + "Start at Login" checked | |
| 9 | Reinstall = still one icon | |
| 10 | Uninstalls cleanly | |

**Anything else you noticed, found confusing, or want to mention?**


Thank you! 🙏 Every note helps — even "this part was confusing" is valuable.

---
<sub>**For the Dictatem team (testers can ignore):** This guide covers issues **#94**
(runbook: Test 1 = part D, Test 2 = part E rails, Test 5 = part F login, Test 7 = part
G uninstall, Test 6 = single-instance #92) and **#93** (Test 3 = paste-not-landing
watch) against released **v0.6.0**. Trigger Fire (#94 part E) is deferred as optional
(needs Ollama). Issues **#121** (macOS mouse hook) and **#95** (first-run onboarding
polish) are **not** covered — they need a dev build that doesn't exist yet; QA them in
a later round once their code lands. See the agent-facing relay version in
`08-s10-macos-qa.md`.</sub>
