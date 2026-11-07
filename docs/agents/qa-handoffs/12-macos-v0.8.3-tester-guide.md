# Testing Dictatem v0.8.3 on your Mac 🎤

Thanks for testing **Dictatem** again. It turns your voice into typed text anywhere
on your Mac: hold a hotkey, talk, let go, and your words appear wherever you're
typing.

This round tests the **v0.8.3 release**. Most of the changes since last time were made
and tested on Windows, and **none of them has run on a real Mac yet**. Your job is the
same as always:

1. **Do** what each step says.
2. **Look** at what happens.
3. **Write** what you saw in the boxes marked **✍️**.

Send back the filled-in guide (or just the **✍️** boxes and the summary at the
bottom). "This part was confusing" is a useful result too.

⏱️ **Time:** in **two sittings**:
- **Sitting 1** (Parts 0–12): about **70 minutes**, plus one **35-minute break**
  (Part 11) where you just leave Dictatem alone. This is the important one.
- **Sitting 2** (Parts 13–16, optional): about **35 minutes** for the Apple GPU
  engine, plus a **10-minute update test** that you run later, **when we tell you a
  newer version is out**.

You can stop after any Part and send what you have.

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

**▸ The pill** is the small floating bar that appears near the bottom of the screen
while you dictate.

**▸ `python3.12` is expected.** macOS settings call Dictatem **`python3.12`**, not
"Dictatem". That's correct for this beta. Turn on `python3.12`.

**▸ Editing the settings file.** Some tests change `~/.dictatem/config.toml`. Open it
with menu-bar icon → **Open config file…** (it opens in TextEdit). Make the change,
save with **⌘ + S**, then menu-bar icon → **Restart**.

**▸ Counting seconds.** For speed tests, count from **releasing the keys** to **the
text appearing**. "One-Mississippi" counting is fine.

**▸ The log file** is `~/Library/Logs/Dictatem/daemon.log`. You don't need to open it
yourself: Part 12 gives you one command that copies out the parts we need. It never
contains what you said.

---

## Part 0 — Update from the old version *(only if v0.7.0 is still installed, 5 min)*

If Dictatem is still on your Mac from last time, this checks that updating works for
people who already have it. If it isn't installed, or you're not sure, **skip to
Part 1**.

1. Click the menu-bar icon. The bottom line should say **Dictatem v0.7.0**.
2. Run the install command for the new version:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.8.3/install.sh | sh
   ```

3. When it finishes, click the menu-bar icon again.

✅ **What you should see:** the install finishes without errors, the icon comes back,
and the bottom line of the menu now says **Dictatem v0.8.3**. Dictate one sentence
into **Notes**: it should still work, without asking for permissions again.

**✍️ Your result — Update:**
- Finished without errors? → **PASS** / **FAIL**: 
- Icon came back, menu says v0.8.3? → **PASS** / **FAIL**: 
- Dictation still worked, no new permission dialogs? → **PASS** / **FAIL**: 
- If anything failed, copy the last 20 lines Terminal printed here: 

---

## Part 1 — Start clean (2 min)

This clears any old version and its permissions so you see exactly what a brand-new
user sees. It also moves your old settings aside. **Run it even if you're not sure.**
Errors like "not found" or "No such file" are fine.

```sh
dictatem --uninstall; uv tool uninstall dictatem; tccutil reset Accessibility; tccutil reset ListenEvent; mv ~/.dictatem ~/.dictatem-before-v0.8.3
```

**✍️ Done?** (yes / no): 

---

## Part 2 — Install v0.8.3 (about 8 min)

Before you start, **note the time on the clock**. Then run:

```sh
curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.8.3/install.sh | sh
```

It downloads a few hundred megabytes and can take several minutes.

✅ **What you should see:**
- A line saying which **engine set** it chose (it should say **CPU**).
- Near the end, **"Waiting for Dictatem to start…"** with dots growing, instead of a
  long silent pause.
- Then the Dictatem icon appears in the menu bar.
- Then a short message saying **setup isn't finished** until you turn on two
  permissions and restart Dictatem.

**✍️ Your result — Install:**
- Engine-set line, "Waiting…" line, icon, setup message? → **PASS** / **FAIL**: 
- How long from pressing Return to the icon appearing? ___ minutes
- Anything confusing or alarming in the text it printed: 

---

## Part 3 — Permissions 🔐 (about 8 min)

About 2 seconds after the icon appears, Dictatem shows **two short dialogs**, one at a
time: first **Accessibility**, then **Input Monitoring**.

1. In the **Accessibility** dialog, click **Open System Settings**, find
   **`python3.12`**, and switch it **ON**.
2. **Before** turning on Input Monitoring, click the menu-bar icon and look at the menu.
   The top line should say **"Hotkey off — allow Input Monitoring"**, and the menu
   should include **Start recording** and **Stop recording** (without a hotkey, these
   are how you'd record). Close the menu.
3. Now in the **Input Monitoring** dialog, click **Open System Settings** and switch
   **`python3.12`** **ON**.
4. Click the menu-bar icon and choose **Restart**. The icon should disappear and come
   back within a few seconds.
5. Click the menu-bar icon again. The top line should now say **"⌥⌘ to dictate"**,
   and **Start recording / Stop recording should be gone** (with a working hotkey you
   don't need them).

✅ **What you should see:** exactly two dialogs (Input Monitoring must **not** appear
twice); "Hotkey off" plus Start/Stop recording before you allowed Input Monitoring;
Restart brings the icon back; afterwards "⌥⌘ to dictate" and no Start/Stop.

**✍️ Your result — Permissions:**
- Two dialogs, no duplicates? → **PASS** / **FAIL**: 
- Before Input Monitoring: "Hotkey off" line shown? → **PASS** / **FAIL**: 
- Before Input Monitoring: Start recording / Stop recording shown? → **PASS** / **FAIL**: 
- Restart from the menu worked? → **PASS** / **FAIL**: 
- After Restart: "⌥⌘ to dictate", and Start/Stop gone? → **PASS** / **FAIL**: 
- Was the wording clear? What would you change? 

---

## Part 4 — First dictation, and speed ⏱️ (about 5 min)

The very first dictation after an install is the slowest one, because Dictatem loads
its speech engine for the first time. We want to know **how slow**.

1. Open **Notes**, click into a blank note.
2. Hold **⌥ + ⌘**, say *"Hello, this is my first test of version zero point eight."*,
   release. Count the seconds until the text appears.
3. The first time, macOS may ask for the **Microphone**: click **Allow**. (If it asked,
   dictate the sentence once more and count that one.)
4. While you wait, watch the pill: it may say **Loading Dict. Model…** for a while.
5. Now dictate **five more** sentences of about **5 seconds** each and count the
   seconds for each.

✅ **What you should see:** your words typed into the note. After the first one, each
should appear in **about 2 seconds or less**.

**✍️ Your result — First dictation:**
- Words typed in? → **PASS** / **FAIL**: 
- First one took ___ seconds · Did the pill say "Loading Dict. Model…"? (yes / no)
- The next five (roughly): ___ / ___ / ___ / ___ / ___ seconds
- From pressing the keys to the pill appearing: instant / about half a second /
  a second or more
- Was the text accurate? Any words it got wrong: 
- Which Mac ( → About This Mac): Chip ______ · Memory ___ GB · macOS ______

---

## Part 5 — The menu 📋 (about 6 min)

Dictatem's menu was rearranged in this version. Click the menu-bar icon and read the
whole menu from top to bottom.

1. It should contain, in this order (the lines between groups are fine):
   **⌥⌘ to dictate** (gray) · **Copy last dictation** · **Unload model** ·
   **Start at login** (with a checkmark) · **Show log** · **Open config file…** ·
   **How to use Dictatem…** · **Restart** · **Check for updates…** · **Quit** ·
   **Dictatem v0.8.3** (gray).
2. It should **not** contain **Preload model**, **Start recording**, **Stop
   recording** or **Microphone**. (The Microphone choice is a Windows feature; on a
   Mac, Dictatem uses whatever microphone is selected in System Settings.)
3. Look for odd gaps: two divider lines in a row, or an empty band where an item
   should be.
4. Open the menu and click somewhere else on the screen: the menu should close. Open
   it again and press **Esc**: it should close.
5. Choose **How to use Dictatem…**. While that window is open, open the menu again,
   then click outside it. The menu should close (the guide window can stay open).
   Close the guide.
6. Choose **Copy last dictation**, click into a note and press **⌘ + V**: your last
   sentence from Part 4 should paste in.
7. Choose **Check for updates…**: it should say **Dictatem is up to date (v0.8.3)**.

**✍️ Your result — Menu:**
- Items as listed, in that order? → **PASS** / **FAIL** (what was different?): 
- No Preload / Start / Stop / Microphone? → **PASS** / **FAIL**: 
- Any odd gaps or doubled lines? (yes / no, where?): 
- Clicking outside and Esc both close the menu? → **PASS** / **FAIL**: 
- Closes on an outside click while the guide is open? → **PASS** / **FAIL**: 
- Copy last dictation pasted your sentence? → **PASS** / **FAIL**: 
- "Up to date (v0.8.3)"? → **PASS** / **FAIL**: 

---

## Part 6 — Plugging in a microphone 🎧 (about 8 min)

> Needs a **headset or microphone you can plug in** (USB or a wired headset with a
> mic), or **AirPods / Bluetooth headphones with a mic**. If you have none, skip to
> Part 7.

1. Open  → **System Settings** → **Sound** → **Input** and leave that window open.
   Note which device is ticked: ______
2. **Plug in** (or connect) your headset while Dictatem is running. Look at the
   **Input** list: which device is ticked now? ______
3. Dictate a sentence into Notes, speaking **into the headset**. Did it work?
4. Dictate one more sentence while **watching the pill's level bars**. Then tap on
   the headset mic gently with a finger during a dictation: the bars should jump.
   (If you tap the Mac's own mic area instead and the bars jump more, the Mac's mic
   is being used.)
5. **Unplug** (or disconnect) the headset. Dictate a sentence using the Mac's own
   mic. Did it work, or was nothing typed?
6. Plug the headset back in, and this time **unplug it in the middle of a
   dictation** (hold the keys, start talking, unplug, keep talking, release). Watch
   what happens. Then dictate one more normal sentence.

✅ **What you should see:** every dictation types your words, using whichever
microphone is ticked in System Settings at the time. Unplugging during a dictation
may lose that sentence, but Dictatem should **not** freeze, and the **next**
dictation should work.

**✍️ Your result — Microphones:**
- Headset used: ______ (USB / wired / Bluetooth)
- Dictation with the headset worked? → **PASS** / **FAIL**: 
- Was the headset mic really the one used (step 4)? (yes / no / can't tell): 
- After unplugging, dictation with the Mac's mic worked? → **PASS** / **FAIL**: 
- Unplugging mid-dictation: what happened? Did the next dictation work? 
- Any error message or notification? Write its words here: 

---

## Part 7 — Shortcuts that must NOT start a dictation ⛔ (about 8 min)

On Windows, some people found that **Alt + Enter** (or Alt on its own) started a
dictation by surprise. On a Mac, the matching keys are **Option + Return** and
**Option** on its own. Only **⌥ + ⌘ together** should start a dictation.

Open **TextEdit** with a new document for these tests.

### Test A — Normal typing
1. Press **⌥ + Return** 5 times (each press just adds a new line).
2. **Tap ⌥** on its own 5 times.
3. Hold **⌥** and press the **left arrow** a few times (it jumps by words).

**✍️** Did the pill ever appear, or did anything get typed besides new lines?
(yes / no): 

### Test B — After locking the screen 🔒
1. Lock the screen with **⌃ + ⌘ + Q** (Control + Command + Q).
2. Unlock with your password or Touch ID.
3. Click into TextEdit **right away**, then **tap ⌥** on its own 3 times and press
   **⌥ + Return** 3 times.
4. Repeat steps 1–3 two more times.

**✍️** Did the pill ever appear? (yes / no, on which try?): 

### Test C — After a "secure" window 🔐
Some windows hide your keystrokes from other apps (password boxes, and Terminal's
**Secure Keyboard Entry**). This checks Dictatem doesn't get confused by them.

1. Open **Terminal**, then in the menu bar choose **Terminal** → **Secure Keyboard
   Entry** so it has a checkmark.
2. Click into **TextEdit**. Then hold **⌘**, press **Tab** once to switch to
   **Terminal**, and let go of **⌘** while Terminal is in front.
3. **With the mouse**, click back into the TextEdit window. (Don't use ⌘ + Tab.)
4. **Tap ⌥** on its own 3 times and press **⌥ + Return** 3 times.
5. Repeat steps 2–4 two more times.
6. Turn **Secure Keyboard Entry** off again (Terminal → Secure Keyboard Entry).

**✍️** Did the pill ever appear? (yes / no, on which try?): 

### Test D — The real hotkey still works
1. Hold **⌥ + ⌘**, say a sentence, release. It should be typed in.
2. **Tap** ⌥ + ⌘ once (quick press and release). Say *"This is a tap test."* Tap once
   more to stop. Your words should be typed in.
3. Tap once again, say something, then press **Esc** instead of stopping. Nothing
   should be typed.

**✍️** Hold worked? **PASS** / **FAIL**: · Tap worked? **PASS** / **FAIL**: · Esc
cancelled, nothing typed? **PASS** / **FAIL**: 

> If the pill appeared by surprise in Test A, B or C, please write down roughly
> **what time** it happened. That lets us find the moment in the log.

---

## Part 8 — Everyday checks (about 7 min)

### Test E — Two different apps
Open **Notes** and **TextEdit**. Dictate one sentence into each, clicking into each
app first.

**✍️** Each sentence landed in the right app? **PASS** / **FAIL**: 

### Test F — Right after a restart 🔁
1. Open Safari or Chrome, click into any text box (a search box is fine).
2. Menu-bar icon → **Restart**. Wait for the icon to come back.
3. Right away, dictate a short sentence into the browser box, **3 times in a row**.
4. Do the same 3 times into **Notes**.

**✍️** Browser: ___ / 3 · Notes: ___ / 3 · If any went missing, which ones? 

### Test G — When a permission is missing
1.  → System Settings → Privacy & Security → **Accessibility** → turn
   **`python3.12` OFF**.
2. Dictate into a note.
3. You should see a dialog saying **Dictatem couldn't paste** and asking you to allow
   Accessibility. Close it.
4. Click the menu-bar icon → **Copy last dictation**, then click into the note and
   press **⌘ + V**. Your sentence should paste in.
5. Turn **`python3.12` back ON**, then menu-bar icon → **Restart**.

**✍️** Saw the "couldn't paste" dialog? **PASS** / **FAIL**: · Copy last dictation
recovered the text? **PASS** / **FAIL**: 

---

## Part 9 — Quit, then start it again 🚪 (about 5 min)

We want to know what a normal person would do to get Dictatem back after quitting it.

1. Menu-bar icon → **Quit**. The icon should disappear.
2. **Without reading ahead**, try to start Dictatem again the way you naturally
   would (for example: **⌘ + Space**, type *Dictatem*, press Return). Wait 30
   seconds.
3. Write down what happened: did the icon come back? Does the hotkey work? Did any
   permission dialog appear?
4. Now run the official restart command in Terminal (if Dictatem is already running
   from step 2, this replaces it):

   ```sh
   pkill -f "dictatem" ; sleep 2 ; launchctl kickstart -k gui/$(id -u)/com.dictatem.daemon
   ```

5. Wait for the icon, then dictate a sentence into Notes.

**✍️ Your result — Quit and start again:**
- Quit removed the icon? → **PASS** / **FAIL**: 
- What did you try in step 2? ______ · Did the icon come back? (yes / no) · Hotkey
  worked? (yes / no / didn't try) · Any permission dialog? (yes / no)
- After the Terminal command: icon back, and dictation worked? → **PASS** / **FAIL**: 
- How would you expect to start Dictatem again after quitting it? 

---

## Part 10 — Works offline ✈️ (about 4 min)

Since this version, Dictatem shouldn't need the internet at all after it's installed.

1. Turn **Wi-Fi off** (and unplug any network cable).
2. Menu-bar icon → **Restart**, then dictate 2 sentences. Count the seconds for the
   first one.
3. Turn Wi-Fi back on.

**✍️** Dictation worked with no internet? **PASS** / **FAIL**: · First one took ___
seconds

---

## Part 11 — After a break ☕ (35-minute break, then 3 min)

After about half an hour of not being used, Dictatem frees its memory. The first
dictation after that is a bit slower. We want to know **how much slower**.

1. **Write down the time now:** ______ . Leave Dictatem alone for **at least 35
   minutes** (keep using your Mac for other things if you like, just don't dictate).
2. After the break, open Notes and dictate a sentence. Count the seconds.
3. Dictate one more and count again.

**✍️** Break length: ___ minutes · First dictation after the break: ___ seconds ·
Second: ___ seconds · Did the pill say "Loading Dict. Model…"? (yes / no)

### Test H — Survives a log out
Log out ( → Log Out) and back in. Don't change anything. Check the menu-bar icon is
back, dictate a sentence, and check the menu shows **"Start at login"** with a
checkmark.

**✍️** Came back and worked with no setup? **PASS** / **FAIL**: · "Start at login"
checked? **PASS** / **FAIL**: 

---

## Part 12 — Grab the log (3 min)

This tells us how long Dictatem took to start, load and transcribe, and what the
hotkey saw. It never contains what you said. Paste this into Terminal and copy
**everything** it prints into your reply:

```sh
L=~/Library/Logs/Dictatem/daemon.log; echo "--- startup"; grep -E "Startup timing|Dictatem daemon started|Engine prewarm|Engine kept resident" "$L" | tail -n 20; echo "--- engine"; grep -E "[Tt]ier|Model load breakdown|Transcribe call took|not resolvable from the local cache|[Ff]etch|download|audio.device|AVAudioEngine|microphone" "$L" | tail -n 80; echo "--- hotkey"; grep -E "Hotkey|Permission|Input Monitoring|event tap" "$L" | tail -n 120
```

✅ **What you should see** (you can check this yourself, but just pasting is fine):
- Under `--- startup`, lines starting with **`Startup timing:`**, one per launch.
- **No** line containing `Engine prewarm` or `Engine kept resident` (those are for
  Windows only; on a Mac their absence is correct).

**✍️** Log pasted? (yes / no) · Saw `Startup timing:` lines? (yes / no) · Saw any
`Engine prewarm` line? (yes / no) 

**That's the end of Sitting 1.** Please keep Dictatem installed: Sitting 2 and the
update test build on it.

---

# Sitting 2 — Apple GPU engine and updates (optional)

> Parts 13–15 are only for **Apple Silicon** Macs (M1/M2/M3/M4) on **macOS 14 or
> later**. If yours is older, skip to Part 16.

## Part 13 — Install with the Apple GPU engine 🚀 (about 8 min)

This moves your Sitting 1 settings aside (so Dictatem picks fresh GPU settings) and
installs the extra engine. It adds about 230 MB.

```sh
mv ~/.dictatem/config.toml ~/.dictatem/config-cpu.toml; curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.8.3/install.sh | DICTATEM_APPLE_GPU=1 sh
```

✅ **What you should see:** the engine-set line now says **Apple GPU (MLX)**. No
permission dialogs (you already granted them). The first dictation afterwards may
take a while (it downloads the GPU model once); that's expected.

**✍️** Engine line said Apple GPU? **PASS** / **FAIL**: · Permission dialogs
appeared? (yes / no): · First dictation took ___ seconds

## Part 14 — GPU tests (about 22 min)

### Test J — Speed
1. Open **Activity Monitor** (⌘ + Space → Activity Monitor), **Memory** tab, and find
   **`python3.12`**. Write down its memory now: ___ (this is "before").
2. In Notes, dictate **10 sentences of about 5 seconds** each and count the seconds
   for each.
3. Dictate **3 longer ones of about 15 seconds** each.
4. Look at `python3.12` in Activity Monitor again: ___ ("loaded").
5. Menu-bar icon → **Unload model**, wait 10 seconds, and look again: ___ ("unloaded").

**✍️** 5 s sentences: ___ / ___ / ___ / ___ / ___ / ___ / ___ / ___ / ___ / ___ s
· 15 s sentences: ___ / ___ / ___ s · Memory before / loaded / unloaded:
___ / ___ / ___ · Faster or slower than Sitting 1? 

### Test K — Silence and special words
1. Dictate while saying **nothing at all** for about 5 seconds, 3 times. Nothing
   should be typed (no made-up words like "Thank you.").
2. Open `~/.dictatem/vocabulary.md` (in Terminal: `open -e ~/.dictatem/vocabulary.md`,
   or create it with TextEdit), put an unusual name you use on its own line (a
   surname, a product, a place), save, and **Restart**.
3. Dictate a sentence containing that name **5 times**.

**✍️** Silence typed nothing, 3/3? ___ / 3 · Name you used: ______ · Spelled right
___ / 5

### Test L — GPU engine works offline ✈️
1. Turn **Wi-Fi off** (and unplug any network cable).
2. Menu-bar icon → **Restart**, then dictate 2 sentences. Count the seconds for the
   first one.
3. Turn Wi-Fi back on.

**✍️** Dictation worked with no internet? **PASS** / **FAIL**: · First one took ___
seconds

### Test M — When the GPU engine breaks 🛟
This makes the GPU engine fail on purpose, to check Dictatem quietly falls back to
the normal engine.

1. Open the config file. Under `[model]`, **write down** the current `name = …`
   line here: ______ . Then change it to:
   ```toml
   name = "mlx-community/does-not-exist"
   ```
   Save and **Restart**.
2. Dictate a sentence into Notes.
3. Dictate two more.
4. **Restart** again and dictate one more.
5. Put the `name` line back to what you wrote down in step 1, save, and
   **Restart**.

✅ **What you should see:** step 2's sentence still gets typed (maybe slower), and
**one** notification says the GPU engine failed and it's using the CPU. Step 3:
**no** further notifications. Step 4: the notification comes back once (it retries
the GPU each launch). Dictatem doesn't change the config file itself.

**✍️** Sentence typed despite the failure? **PASS** / **FAIL**: · Exactly one
notification? **PASS** / **FAIL**: · Notification wording: 
· After Restart it tried again (one new notification)? **PASS** / **FAIL**: 

## Part 15 — GPU log (about 3 min)

Run the log command from **Part 12** again and paste everything it prints into your
reply.

**✍️** Log pasted? (yes / no)

---

## Part 16 — The update button 🔄

The **Check for updates…** button is how every future version will reach you, so
this one matters. It has two halves.

### Part 16a — Right now (2 min, do it today)

Menu-bar icon → **Check for updates…**

✅ **What you should see right now:** a message saying **"Dictatem is up to date
(v0.8.3)."**, in front of your other windows. Nothing is downloaded or installed.

**✍️** Said "up to date (v0.8.3)", in front? **PASS** / **FAIL**: · Exact wording if
different: 

### Part 16b — When we tell you a newer version is out (about 10 min)

> ⏸️ **Wait for our message** before doing this part. It only works once a newer
> version (for example **v0.8.4** or **v0.9.0**) has been published. Until then you'll
> just see "up to date" again, which is fine.

Don't reinstall or uninstall anything first: this tests updating the copy you
already have.

1. Click the menu-bar icon. The bottom line should say **Dictatem v0.8.3**.
2. Menu-bar icon → **Check for updates…**. A dialog should appear **in front of**
   your other windows: **"Dictatem v______ is available"** (the new version we told
   you about), **"You have v0.8.3"**, with an install command on its own line, and
   three buttons: **Copy Update Command**, **Open Instructions**, **Later**.
3. While it's open, click **Check for updates…** again: no second dialog should
   appear.
4. Click **Later**. Check again and click **Open Instructions**: a web page about
   updating should open.
5. Check again and click **Copy Update Command**. A notification should say
   **"Update command copied"**. Nothing else should happen by itself (no Terminal
   window opens).
6. Open Terminal, paste the command (**⌘ + V**), press **Return**, and wait for it to
   finish.
7. Click the menu-bar icon: the bottom line should now show the **new version**.
8. Dictate a sentence into Notes. It should work **without** asking for permissions
   again.
9. **If you did Sitting 2 (Apple GPU):** watch for a notification saying the GPU
   engine isn't available and Dictatem is using the CPU. Write down whether it
   appeared, and its wording.
10. **Check for updates…** once more: it should say **"Dictatem is up to date
    (v______)"** with the new version.

**✍️ Your result — Update:**
- Dialog in front, right versions, three buttons? → **PASS** / **FAIL**: 
- No second dialog? → **PASS** / **FAIL**: 
- Later / Open Instructions worked? → **PASS** / **FAIL**: 
- Copy put the command on the clipboard, nothing ran by itself? → **PASS** / **FAIL**: 
- Update finished, menu shows the new version? → **PASS** / **FAIL**: 
- Dictation still worked, no permission dialogs? → **PASS** / **FAIL**: 
- (Apple GPU only) "GPU engine not available / using CPU" notification? (yes / no,
  wording): 
- "Up to date" with the new version afterwards? → **PASS** / **FAIL**: 
- Then run the log command from **Part 12** and paste the output: (yes / no)

When you're completely done, you can keep Dictatem installed. To remove it:

```sh
dictatem --uninstall; uv tool uninstall dictatem
```

---

## 📋 Summary to send back

| # | Test | PASS / FAIL / SKIP |
|---|------|--------------------|
| 0 | Update from v0.7.0 (menu says v0.8.3, still dictates) | |
| 2 | Install (engine line + waiting line + setup message; ___ min) | |
| 3 | Permissions: two dialogs, "Hotkey off" + Start/Stop, then "⌥⌘ to dictate" without Start/Stop | |
| 4 | First dictation ___ s, then ~___ s each | |
| 5 | Menu: items, no Preload/Start/Stop/Microphone, closes properly, up to date | |
| 6 | Microphones: headset, unplugged, unplugged mid-dictation | |
| 7A | ⌥ + Return / lone ⌥ don't dictate | |
| 7B | …nor after locking the screen | |
| 7C | …nor after Secure Keyboard Entry | |
| 7D | Hold, tap and Esc still work | |
| E | Two apps | |
| F | After restart: browser ___/3, Notes ___/3 | |
| G | Missing permission: dialog + Copy last dictation | |
| 9 | Quit, then start again (what you tried: ______) | |
| 10 | Offline | |
| 11 | After a ___ min break: ___ s | |
| H | Survives log out + "Start at login" | |
| 12 | Log pasted | |
| | **Sitting 2 (optional)** | |
| 13 | GPU install | |
| J | GPU speed (~___ s for 5 s clips) + memory | |
| K | Silence + special words ___/5 | |
| L | GPU offline | |
| M | GPU failure falls back, one notification | |
| 15 | GPU log pasted | |
| 16a | Check for updates: "up to date (v0.8.3)" | |
| 16b | Update to v______ (run when told): dialog, copy, install, still works | |

**Anything else you noticed or found confusing?**


Thank you! 🙏

---
<sub>**For the Dictatem team (testers can ignore):** macOS smoke test of v0.8.0–v0.8.3
for tracking issue #281; build = tag **v0.8.3**. Supersedes guide 11, which was
never run. Carried over from guide 11: Sitting 2's Apple-GPU opt-in (#230–#233; Parts
13–15 = guide 11's Parts 8–9, targets in its footnote: 5 s p50 ≤ 1.5 s, worst ≤ 2.5 s;
15 s p50 ≤ 2.5 s; RSS within 300 MB of baseline after Unload; Vocabulary ≥ 3/5;
Test L also covers the MLX load path, which the v0.8 cache-first change did not touch).
Part 16 = #193 update button. It replaces guide 11's `qa/193-fake-old-version` branch
with a real upgrade from installed v0.8.3, so **16b needs a published release newer
than v0.8.3**: `releases/latest` must return a plain `vX.Y.Z` tag, because
`parse_version` rejects `-rc` suffixes (an rc there gives "Couldn't check for
updates", never an offer). Send the tester the version number when it's out. 16b
step 9 checks a known gap: `install_sh_command()` doesn't carry
`DICTATEM_APPLE_GPU=1` and `select_dictatem_extra` reads only that env var, so an
update reinstalls the `runtime` set and drops MLX; an Apple-GPU config then falls back
to CPU with the notification. Still not carried over: guide 11's Tests E–G (clipboard,
say-again, languages). Nothing in v0.8 touched them, but since guide 11 never ran
they have never been confirmed on a Mac (#244, #249, #274); add them to a later round.
Mapping: Part 0 = install.sh PySide6 meta → Essentials migration (`--reinstall-package
pyside6-essentials`, only reached on an upgrade from ≤ v0.7.0; a broken Qt shows as no
icon / import error). Part 3 + Part 5 = ADR-0030 §1 hotkey-first tray on the Qt path
(Start/Stop shown only when `CGEventTapCreate` fails; the startup `check_permissions()`
result does not unhide them, so a FAIL on "Start/Stop shown before Input Monitoring"
means the tap was created without the grant). Part 4 / 10 / 11 = cache-first model
load (`resolve_model_path`; a `not resolvable from the local cache` line means it went
online) and load-on-arm timings; Engine Prewarm and Resident Engine are Windows-only
(`should_prewarm` requires win32), and install.sh has no prewarm step, so `Speech engine
ready (N s)` / `Engine prewarm finished in` never appear on a Mac and the first
dictation after install is not expected to improve; `Startup timing` has no
`interpreter` phase on macOS (`process_age_s` is Windows-only). Part 6 = ADR-0027
AVAudioEngine follows the system default input; the ADR-0031 re-scan and Microphone
menu are PortAudio-only and hidden on macOS, `[audio] device` is ignored there; the
engine and input node are created once and reused, with no configuration-change
observer, so hot-plug is the risk; README "A microphone plugged in…" paragraph is
Windows wording. Part 7 = ADR-0032: no physical-key-state query is wired on darwin
(`physical_state=None`), so a ⌘ key-up missed under secure input or the lock screen
could leave ⌘ "held" and a lone ⌥ tap would then complete ⌥⌘ (look for `Hotkey
KEY_DOWN: IDLE -> …[RECORD_START]` at the times the tester notes). Part 9 = ADR-0030
§3 has no macOS counterpart (README says don't launch from Spotlight / the .app;
check whether that warning is still true after the `TransformProcessType` fix).</sub>
