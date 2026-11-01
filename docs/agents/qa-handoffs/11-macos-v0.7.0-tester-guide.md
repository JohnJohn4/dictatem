# Testing Dictatem v0.7.0 on your Mac 🎤 (round 2)

Thanks for testing **Dictatem** again. It turns your voice into typed text anywhere
on your Mac: hold a hotkey, talk, let go, and your words appear wherever you're
typing.

This round tests the **v0.7.0 release**. A lot is new since last time: a faster
speech model on Apple Silicon, an optional **Apple GPU engine**, an update button,
better clipboard handling, and language settings. Your job is the same as always:

1. **Do** what each step says.
2. **Look** at what happens.
3. **Write** what you saw in the boxes marked **✍️**.

Send back the filled-in guide (or just the **✍️** boxes and the summary at the
bottom). "This part was confusing" is a useful result too.

⏱️ **Time:** about 90 minutes, in **two sittings**:
- **Sitting 1** (Parts 1–7, ~50 min): the normal install everyone gets.
- **Sitting 2** (Parts 8–11, ~40 min): the Apple GPU engine and the update button.

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

**▸ `python3.12` is expected.** macOS settings call Dictatem **`python3.12`**, not
"Dictatem". That's correct for this beta. Turn on `python3.12`.

**▸ Editing the settings file.** Some tests change `~/.dictatem/config.toml`. Open it
with menu-bar icon → **Open config file…** (it opens in TextEdit). Make the change,
save with **⌘ + S**, then menu-bar icon → **Restart**. If a setting is already in the
file, change that line instead of adding a second copy.

**▸ Counting seconds.** For speed tests, count from **releasing the keys** to **the
text appearing**. "One-Mississippi" counting is fine.

---

# Sitting 1 — the normal install

## Part 1 — Start clean

This clears any old version and its permissions so you see exactly what a brand-new
user sees. It also moves your old settings aside. **Run it even if you're not sure.**
Errors like "not found" or "No such file" are fine.

```sh
dictatem --uninstall; uv tool uninstall dictatem; tccutil reset Accessibility; tccutil reset ListenEvent; mv ~/.dictatem ~/.dictatem-round1-backup
```

**✍️ Done?** (yes / no): 

---

## Part 2 — Install v0.7.0

```sh
curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.7.0/install.sh | sh
```

It downloads a few hundred megabytes and can take several minutes.

✅ **What you should see:**
- A line saying which **engine set** it chose (it should be the **CPU** set this
  time; the GPU one comes in Part 8).
- Near the end, **"Waiting for Dictatem to start…"** with dots growing, instead of a
  long silent pause.
- Then the Dictatem icon appears in the menu bar.
- Then a short message saying **setup isn't finished** until you turn on two
  permissions and restart Dictatem.

**✍️ Your result — Install:**
- Engine-set line, "Waiting…" line, icon, setup message? → **PASS** / **FAIL**: 
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
twice); the "Hotkey off" line before you allowed Input Monitoring; Restart brings the
icon back.

**✍️ Your result — Permissions:**
- Two dialogs, no duplicates? → **PASS** / **FAIL**: 
- "Hotkey off — allow Input Monitoring" shown before granting? → **PASS** / **FAIL**: 
- Restart from the menu worked? → **PASS** / **FAIL**: 
- Was the wording clear? What would you change? 

---

## Part 4 — First dictation, and speed ⏱️

1. Open **Notes**, click into a blank note.
2. Hold **⌥ + ⌘**, say *"Hello, this is my first test of version zero point seven."*,
   release.
3. The first time, macOS may ask for the **Microphone**: click **Allow**.
4. Now dictate **five more** sentences of about **5 seconds** each and count the
   seconds for each.

✅ **What you should see:** your words typed into the note. After the first one, each
should appear in **about 2 seconds or less**.

**✍️ Your result — First dictation:**
- Words typed in? → **PASS** / **FAIL**: 
- First one took ___ seconds
- The next five (roughly): ___ / ___ / ___ / ___ / ___ seconds
- Was the text accurate? Any words it got wrong: 
- Which Mac ( → About This Mac): Chip ______ · Memory ___ GB · macOS ______

---

## Part 5 — Everyday tests

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
4. Click the menu-bar icon → **Copy last dictation**, then click into the note and
   press **⌘ + V**. Your sentence should paste in.
5. Turn **`python3.12` back ON**, then menu-bar icon → **Restart**.

**✍️** Saw the "couldn't paste" dialog? **PASS** / **FAIL**: · Copy last dictation
recovered the text? **PASS** / **FAIL**: 

### Test E — Your clipboard survives 📋
Dictatem briefly uses the clipboard to paste. Whatever you had copied before should
still be there afterwards.

1. **Screenshot:** press **⌘ + Ctrl + Shift + 4** and drag over part of the screen
   (this copies it, no file is saved). Dictate a sentence into Notes. Then open
   **Preview** → File → **New from Clipboard**.
2. **A file:** in Finder, click any file and press **⌘ + C**. Dictate a sentence into
   Notes. Then click your Desktop and press **⌘ + V**.
3. **Formatted text:** in Safari, select a paragraph with a link or bold text and
   press **⌘ + C**. Dictate a sentence into Notes. Then open a new **TextEdit**
   document and press **⌘ + V**.

**✍️** Screenshot came back? **PASS** / **FAIL**: · File pasted as a copy?
**PASS** / **FAIL**: · Formatting/link kept? **PASS** / **FAIL**: 

### Test F — "Say again" 🔵
Saying just the word **"paste"** on its own re-pastes your last dictation. If a short
word only *sounds close* to "paste", Dictatem shows a **sky-blue "say again"** flash on
the pill and pastes nothing.

1. Dictate a sentence into a note.
2. Dictate just **"paste"** (a quick 1–2 second press). Your last sentence should
   paste again.
3. Now dictate a near-miss word on its own, about 1–2 seconds: try **"pastry"**,
   **"based"** and **"pace"**, a few times each.

For each near-miss, note whether you got a **sky-blue flash**, the word typed in, or
your sentence pasted, and **how long** before something happened.

**✍️** "paste" re-pasted? **PASS** / **FAIL**: · Near-misses (what happened, how many
seconds): 

### Test G — Languages 🌐
1. In a note, dictate **"Summer."** on its own, 5 times. It should come out in
   English every time (older builds sometimes turned it into French or Greek).
2. Open the config file and, under the `[model]` section, add:
   ```toml
   language = "auto"
   ```
   Save, **Restart**, and dictate **"Hello."** on its own, 3 times.
3. If you speak a second language, change that line to
   `languages = ["en", "zh"]` (use your language's
   [code](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py) instead of
   `zh`; delete the `language = "auto"` line), save, Restart, and dictate one longer
   sentence (5+ seconds) in each language.
4. Finally **delete** the line(s) you added, save, and Restart.

**✍️** "Summer." English 5/5? ___ / 5 · "Hello." with auto: ___ · Your macOS display
language: ______ · Second-language test (which language, did both work?): 

---

## Part 6 — Log out and reinstall

### Test H — Survives a log out
Log out ( → Log Out) and back in. Don't change anything. Check the menu-bar icon is
back, dictate a sentence, and check the menu shows **"Start at login"** with a
checkmark.

**✍️** Came back and worked with no setup? **PASS** / **FAIL**: · "Start at login"
checked? **PASS** / **FAIL**: 

### Test I — Reinstall doesn't duplicate
Run the install command from Part 2 again. There should still be **one** Dictatem
icon and **no** permission dialogs this time.

**✍️** One icon, no dialogs? **PASS** / **FAIL**: 

---

## Part 7 — Grab the log (end of Sitting 1)

This tells us which speech model your Mac picked, when it downloaded, and how fast
each dictation was. It never contains what you said. Paste this into Terminal and
copy everything it prints into your reply:

```sh
grep -E "starting|[Tt]ier|model|[Ff]etch|download|Transcription|Trigger Word|Paste diag|clipboard" ~/Library/Logs/Dictatem/daemon.log | tail -n 150
```

**✍️** Log pasted? (yes / no): 

---

# Sitting 2 — Apple GPU engine and updates

> Only for **Apple Silicon** Macs (M1/M2/M3/M4) on **macOS 14 or later**. If yours is
> older, skip to Part 10.

## Part 8 — Install with the Apple GPU engine 🚀

This moves your Sitting 1 settings aside (so Dictatem picks fresh GPU settings) and
installs the extra engine. It adds about 230 MB.

```sh
mv ~/.dictatem/config.toml ~/.dictatem/config-cpu.toml; curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.7.0/install.sh | DICTATEM_APPLE_GPU=1 sh
```

✅ **What you should see:** the engine-set line now says **Apple GPU (MLX)**. No
permission dialogs (you already granted them). The first dictation afterwards may
take a while (it downloads the GPU model once); that's expected.

**✍️** Engine line said Apple GPU? **PASS** / **FAIL**: · Permission dialogs
appeared? (yes / no): · First dictation took ___ seconds

## Part 9 — GPU tests

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

### Test L — Works offline ✈️
1. Turn **Wi-Fi off** (and unplug any network cable).
2. Menu-bar icon → **Restart**, then dictate 2 sentences.
3. Turn Wi-Fi back on.

**✍️** Dictation worked with no internet? **PASS** / **FAIL**: 

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
the GPU each launch). The config file is not changed by Dictatem.

**✍️** Sentence typed despite the failure? **PASS** / **FAIL**: · Exactly one
notification? **PASS** / **FAIL**: · Notification wording: 
· After Restart it tried again (one new notification)? **PASS** / **FAIL**: 

## Part 10 — The update button 🔄

This installs a special test build that pretends to be an **old version**, so you can
see Dictatem offer the v0.7.0 update.

1. Install the test build:
   ```sh
   curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/qa/193-fake-old-version/install.sh | DICTATEM_REF=qa/193-fake-old-version sh
   ```
   The bottom of the menu-bar menu should read **"Dictatem v0.6.0"**.
2. Menu-bar icon → **Check for Updates…**. A dialog should appear **in front of**
   your other windows: **"Dictatem v0.7.0 is available"**, "You have v0.6.0", with an
   install command on its own line.
3. While it's open, click **Check for Updates…** again: no second dialog.
4. Click **Later**. Check again and click **Open Instructions**: a web page about
   updating opens.
5. Check again and click **Copy Update Command**. A notification says it was copied.
   Nothing else should happen by itself (no Terminal window opens).
6. Paste the command into Terminal and run it. When it finishes, the menu footer
   should read **v0.7.0** and dictation should still work **without** re-granting
   permissions.
7. Check for Updates… once more: it should say **Dictatem is up to date (v0.7.0)**.

**✍️** Dialog appeared in front, right versions? **PASS** / **FAIL**: · No double
dialog? **PASS** / **FAIL**: · Later / Open Instructions worked? **PASS** / **FAIL**:
· Copy put the command on the clipboard, nothing ran? **PASS** / **FAIL**: · Update
installed v0.7.0, still works? **PASS** / **FAIL**: · "Up to date" after?
**PASS** / **FAIL**: 

## Part 11 — Log, then uninstall *(do this LAST)*

1. Run the log command from **Part 7** again and paste the output into your reply.
2. Uninstall:

   ```sh
   dictatem --uninstall
   ```

   ```sh
   uv tool uninstall dictatem
   ```

**✍️** Log pasted? (yes / no) · Icon gone, no errors? **PASS** / **FAIL**: 

---

## 📋 Summary to send back

| # | Test | PASS / FAIL / SKIP |
|---|------|--------------------|
| 2 | Install (engine line + waiting line + setup message) | |
| 3 | Permissions: two dialogs, "Hotkey off" line, Restart | |
| 4 | First dictation + speed (___ s first, ~___ s after) | |
| A | Tap + Esc | |
| B | Two apps | |
| C | After restart: browser ___/6, Notes ___/6 | |
| D | Missing permission: dialog + Copy last dictation | |
| E | Clipboard: screenshot / file / formatted text | |
| F | "paste" + say-again flash | |
| G | Languages: Summer ___/5, auto, second language | |
| H | Survives log out + "Start at login" | |
| I | Reinstall = one icon, no dialogs | |
| 7 | Log pasted (Sitting 1) | |
| 8 | GPU install | |
| J | GPU speed (~___ s for 5 s clips) + memory | |
| K | Silence + special words ___/5 | |
| L | Offline | |
| M | GPU failure falls back, one notification | |
| 10 | Update button | |
| 11 | Log pasted + uninstall | |

**Anything else you noticed or found confusing?**


Thank you! 🙏

---
<sub>**For the Dictatem team (testers can ignore):** Round 2 = tracking issue #281,
build = tag **v0.7.0** (send only after it's published; Parts 2/8 need the tag). Mapping:
Parts 2–3 + Test D = #95/PR #210 onboarding (installer wait, two dialogs, hotkey-off
row, re-prompt-on-use, Restart via launchd); Part 4 = #206 Apple-Silicon CPU tier
(`small`; revert to `base` if warm 5 s clips are much over ~2 s) and #213 (first-run
fetch in the Part 7 log); Test C = #93; Test E = #244 (pass → drop the README macOS
clipboard caveat); Test F = #249 confirm pass (log timestamps between the Borderline
and the `Trigger Word confirm pass:` line should be well under 1 s on CPU; near-misses
may simply dictate, which is fine — the log shows whether a Borderline occurred);
Test G = #274 (`Transcription language: auto-detect (OS UI language …)` line);
Parts 8–9 = #230–#233 Apple-GPU opt-in: J = PR #263 latency targets (5 s p50 ≤ 1.5 s,
worst ≤ 2.5 s; 15 s p50 ≤ 2.5 s; RSS within 300 MB of baseline after Unload), K =
silence + Vocabulary ≥ 3/5 via `initial_prompt`, L = offline (Wi-Fi off stands in for
`HF_HUB_OFFLINE=1`), M = `FallbackTranscriber` one-notification + retry-next-launch;
Part 10 = #193/PR #211 via QA-only branch `qa/193-fake-old-version` (v0.6.0 + #211;
never merge), which now offers v0.7.0. **Not covered:** the opt-in real-engine contract
run (`DICTATEM_REAL_ENGINES=1 uv run pytest tests/test_transcriber_contract.py -m
real_engine`) needs a dev clone on the Mac — run it in a coordinator session with the
tester, or ask them separately. When Parts 8–9 pass, merge the draft PR that makes
the `apple-gpu` extra default-on again (reverts the opt-in in `install.sh`,
`tests/test_apple_gpu_extra.py` and the README; linked from #281). The Part 8 command
stays valid: it is pinned to the v0.7.0 script, and later scripts ignore
`DICTATEM_APPLE_GPU=1`.</sub>
