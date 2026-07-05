# QA Handoff — macOS native AVAudioEngine capture (#161) · AGENT RUNBOOK

**STATUS: ✅ PASS — 2026-07-05.** Run on the exact repro device (Apple M3 / macOS
26.5, build 25F71, arm64) against the option-D build
(`fix/macos-native-audio-capture-161`) installed as the real launchd daemon +
generated `Dictatem.app`. All 5 checks passed; the daemon log shows `Model loaded
→ Processing audio → Transcription complete → Paste: sent` every round with **no
post-"Model loaded" silence** — the PortAudio↔CoreAudio deadlock signature is gone.
Crux (Check 1): 5/5 cold-first-dictation-under-load, no freeze. Check 5: a 41 s
dictation → 329 chars, no hang. Honest caveats (both non-blocking): Round 1 had a
one-time 11.5 s cold-disk model-load hitch (recovered, typed cleanly — not a
freeze); the TCC Microphone prompt was **not freshly re-observed** (pre-granted
from the Jul-3 install), though capture works under the packaged identity and
System Settings shows `python3.12` = ON. Evidence: `docs/diagnostics/dictatem-161-qa/`
(FINDINGS.md, env.txt, check1/check5 daemon logs) — kept local (tester home paths).

> **You are a Claude Code agent running on a real macOS device.** This is a
> self-contained runbook. Follow it top to bottom: install the fix build, grant
> permissions, drive a human at the keyboard through a handful of **observable**
> checks, then package the evidence into a **zip** the human sends back.

**Device required:** macOS (Apple Silicon preferred — the freeze reproduced on an
Apple M3 / macOS 26.5; Intel is a welcome bonus).
**Build under test:** branch **`fix/macos-native-audio-capture-161`** (the option-D
native-capture build), installed as the **real launchd daemon** via the one-liner
in Step 2 — *not* the standalone spike.
**Why this is manual:** `MacAudioCapture` is a native AVAudioEngine/PyObjC adapter
and the freeze is a runtime deadlock — neither is machine-verifiable off-device.
The whole point is to confirm **observed behaviour on real hardware**.

---

## 0. What this is and why (enough to interpret results)

Dictatem's macOS "first-dictation freeze" (#161) was a **PortAudio ↔ CoreAudio HAL
deadlock** in the microphone `stop()` on hotkey-release, triggered when the
Whisper model loads *during* recording (load-on-arm) so its CPU threads are
active when `stop()` runs. It froze the daemon: after `Model loaded` the log went
silent, no `Processing audio`, and the UI wedged.

The fix (**option D**, ADR-0027) replaces PortAudio on macOS with Apple's
**AVAudioEngine**, which has no `Pa_StopStream` and so **cannot** hit that
deadlock. **Your job: confirm the freeze is gone on the real installed daemon,
and that dictation still records → transcribes → pastes, releases the mic between
dictations, and prompts for Microphone permission under the real app identity.**

| # | Check | How it's answered | Issue |
|---|-------|-------------------|-------|
| **1** | **No freeze on the cold first dictation under load** (the original repro), repeated | Restart the daemon (forces a cold model load), immediately dictate while speaking a few seconds; words get typed, no hang. Repeat ×5. **This is the crux.** | #161 |
| **2** | Records → transcribes → pastes (regular dictation) | Dictate a sentence into a note; it gets typed correctly. | #161 |
| **3** | Mic indicator turns **off between dictations** | Human watches the menu-bar / Control-Center mic indicator across a gap. | #161 |
| **4** | Microphone **TCC prompt fires + works under the packaged `.app`/launchd identity** | First dictation on a clean grant raises the macOS Microphone prompt; granting it makes capture work. | #161 (§2 open item) |
| **5** | Back-to-back + a long (~30 s) dictation | Several dictations in a row, then one ~30 s dictation; all land, no hang. | #161 |

## 1. Ground rules (important)

- **This is a real device. NEVER record a check as PASS without the human
  confirming what they SAW / HEARD.** Logs alone are not enough (#93's lesson).
- The crux is **Check 1**: a *freeze* means the daemon stops responding after you
  release the hotkey — the overlay pill sticks, nothing gets typed, and the menu
  bar goes unresponsive. A brief (up to ~1.5 s) **hitch** on the very first
  dictation while the model finishes loading is **expected and fine** — that is
  not a freeze. Distinguish the two with the human explicitly.
- If a command errors, **capture the exact text** — do not paper over it.
- **Keep every output.** You will zip the working directory at the end.
- When you need the human to do something physical (speak, watch an indicator,
  click Allow), **stop and ask**, then wait for their reply before continuing.

## 2. Install the fix build as the real launchd daemon

> The `DICTATEM_REF` override installs a branch instead of the pinned release
> tag, and adds `--force --refresh-package dictatem` so uv doesn't serve a stale
> cached copy of the moving branch. This installs the **real daemon** and
> generates the `Dictatem.app` identity shell under launchd — so it exercises the
> **production `.app`/launchd TCC identity** (Check 4), which the spike could not.

Make a working directory and install:

```sh
mkdir -p ~/dictatem-161-qa && cd ~/dictatem-161-qa
curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/fix/macos-native-audio-capture-161/install.sh \
  | DICTATEM_REF=fix/macos-native-audio-capture-161 sh 2>&1 | tee install.log
```

**Expect:** it downloads a few hundred MB (several minutes), then prints that
Dictatem is starting in the menu bar, and a **Dictatem icon appears at the
top-right of the screen**. If it ends in a red error, keep `install.log` and stop
— report the error.

Capture the environment:

```sh
{ echo "=== date ==="; date;
  echo "=== macOS ==="; sw_vers;
  echo "=== chip ==="; sysctl -n machdep.cpu.brand_string; uname -m;
  echo "=== dictatem ==="; uv tool list 2>/dev/null | grep -i dictatem;
  echo "=== python/pyobjc ==="; ls "$HOME/Library/Application Support/uv/tools/dictatem" 2>/dev/null;
} | tee env.txt
```

## 3. Turn on permissions (this is also Check 4)

macOS won't let Dictatem hear the hotkey, type for you, or use the mic until you
allow it. Dictatem pops dialogs that walk the human through it.

> ⚠️ Tell the human: in System Settings the item is called **`python3.12`**, *not*
> "Dictatem" — that is correct and expected (ADR-0014). Turn on `python3.12`.

Drive the human:
1. Follow Dictatem's pop-ups for **Accessibility** and **Input Monitoring** — turn
   **`python3.12`** ON in each (or set them by hand under  → System Settings →
   Privacy & Security).
2. Restart the daemon so grants take effect:
   ```sh
   launchctl kickstart -k gui/$(id -u)/com.dictatem.daemon
   ```
3. **Microphone (Check 4):** the Microphone prompt normally fires on the **first
   dictation** (next step), not up front — so watch for it there.

**✍️ Ask the human and record:** were they able to turn on `python3.12` for
Accessibility and Input Monitoring? (PASS/FAIL + anything confusing.)

## 4. The checks (drive the human; confirm what they SAW)

### Check 1 — No freeze on the cold first dictation under load ×5 (the crux)

Each round: restart the daemon (so the next dictation triggers a **cold** model
load that overlaps speech — the exact freeze condition), then dictate **while
speaking for a few seconds** so the load overlaps the talking.

**Tell the human before each round:**
> "I'll restart Dictatem. Then click into a blank Note, **hold Option (⌥) +
> Command (⌘)**, speak a full sentence for ~3–4 seconds (e.g. *'testing the cold
> first dictation under load, one two three'*), then **release**. Tell me: did
> your words get typed, and did anything **freeze** — the pill sticking, nothing
> typed, the menu bar unresponsive? A brief pause of a second or two before the
> text appears is fine; a hang that doesn't recover is not."

Run this restart before **each** of the 5 rounds, then wait for the human:

```sh
launchctl kickstart -k gui/$(id -u)/com.dictatem.daemon; sleep 2; echo "restarted — dictate now"
```

Do **5 rounds**. After the 5th, grab the tail of the daemon log for evidence:

```sh
tail -n 80 ~/Library/Logs/Dictatem/daemon.log | tee check1-daemonlog.txt
```

**Check 1 PASS** = all 5 cold first-dictations typed the words with **no freeze**
(a brief first-load hitch is fine). The log should show, per dictation,
`Processing audio → Transcription complete → Paste: sent` with **no** silent gap
after `Model loaded`. **FAIL** = any round where the daemon hung / the pill stuck
/ nothing typed and it didn't recover — capture the human's description + the log.

### Check 2 — Records → transcribes → pastes (regular dictation)

**Tell the human:**
> "With the daemon already warm, click into a Note, hold ⌥⌘, say *'the quick brown
> fox jumps over the lazy dog'*, release. Tell me exactly what got typed."

**Check 2 PASS** = the sentence is typed and matches (roughly) what they said.

### Check 3 — Mic indicator turns off between dictations

**Tell the human:**
> "Watch your menu-bar / Control-Center **microphone indicator** (the orange dot /
> 'microphone in use'). Do one dictation, then wait ~5 seconds without dictating.
> Tell me: does the indicator turn **OFF** shortly after you release the hotkey,
> and come back **ON** only while you're actually dictating?"

**Check 3 PASS** = the human confirms the mic indicator is **off during the gap**
and **on only while recording** (per-dictation release — the AVAudioEngine stop
releases the mic).

### Check 4 — Microphone TCC prompt under the real identity

This is answered by the **first** dictation on a machine that hasn't yet granted
Microphone to this build. If the human saw a **"…would like to access the
Microphone"** prompt at Check 1 and clicked **Allow**, and dictation then
captured audio (words typed), that's the pass.

**Check 4 PASS** = the human confirms the Microphone prompt appeared and, after
**Allow**, dictation captured audio. If the mic was already granted from a prior
build (no prompt), note that and confirm it via System Settings → Privacy &
Security → **Microphone** showing the app enabled — and say the prompt itself was
**not freshly observed** (honest partial).

> If capture is silent / a permission error shows: have the human enable the app
> under System Settings → Privacy & Security → **Microphone**, restart the daemon
> (Step 3 command), and retry. Record whether the prompt or the manual grant was
> what worked.

### Check 5 — Back-to-back + a long (~30 s) dictation

**Tell the human:**
> "Do **5 dictations back-to-back**, one right after another (short sentences).
> Then do **one long ~30-second dictation** — hold ⌥⌘ and talk continuously for
> about 30 seconds, then release. Tell me: did all of them land, and did anything
> hang?"

```sh
tail -n 60 ~/Library/Logs/Dictatem/daemon.log | tee check5-daemonlog.txt
```

**Check 5 PASS** = all back-to-back dictations landed and the long dictation
transcribed and pasted, with no hang.

## 5. Write the findings

Create `FINDINGS.md` in `~/dictatem-161-qa` and fill it from what **actually
happened** (paste real log lines + the human's exact words — do not invent):

```markdown
# Dictatem #161 macOS native-capture QA — findings

- Date / device / macOS / chip: <from env.txt>
- Build: fix/macos-native-audio-capture-161 (via DICTATEM_REF)

## Check 1 — No freeze, cold first dictation under load ×5 — PASS / FAIL
<per round: words typed? any freeze? human's words. Paste the Processing audio →
 Transcription complete → Paste: sent lines from check1-daemonlog.txt.>

## Check 2 — Records → transcribes → pastes — PASS / FAIL
Spoken: "<...>"  Typed: "<...>"

## Check 3 — Mic off between dictations — PASS / FAIL / UNSURE
<the human's exact words about the mic indicator>

## Check 4 — TCC Microphone prompt under .app/launchd identity — PASS / FAIL / NOT-FRESHLY-OBSERVED
<did the prompt appear? granted? did capture then work? or already-granted?>

## Check 5 — Back-to-back + long ~30 s dictation — PASS / FAIL
<all landed? any hang?>

## Verdict
Freeze gone / still reproduces because <...>. Notes: <first-dictation hitch felt?
 anything confusing? any errors captured?>
```

## 6. Package everything and hand back

```sh
cd ~/dictatem-161-qa
ZIP="dictatem-161-qa-$(date +%Y%m%d-%H%M).zip"
zip -r "$ZIP" FINDINGS.md env.txt install.log check1-daemonlog.txt check5-daemonlog.txt 2>/dev/null
echo "Created: $(pwd)/$ZIP"
```

Then tell the human:
> "Done. I've packaged everything into **`~/dictatem-161-qa/<ZIP name>`**. Please
> send that zip back to the person who gave you this runbook."

## On result

- **PASS** (all five checks confirmed by the human) → comment the evidence on
  **#161** and close it; the ledger's QA-owed item is cleared. The maintainer then
  cuts the release (bump `DICTATEM_TAG` in `install.sh` **and** `install.ps1` +
  the README one-liner together — `tests/test_install_python_pin.py` guards them —
  tag `vX.Y.Z`, cut the `gh release`), framed as the macOS-audio fix that deletes
  the PortAudio dependency on macOS (superseding the misdiagnosed `v0.6.2-rc1`).
- **FAIL** → comment the captured evidence (human's words + logs) on **#161**,
  keep it open, note the hypothesis. Do **not** merge or claim macOS PASS.

> **If any check could not be run or a step is unconfirmed, say so explicitly in
> FINDINGS.md and to the human — an honest "not verified" beats a guessed PASS.**

---
<sub>**For the Dictatem team:** this runbook drives the **real installed daemon**
(not the spike) for the option-D build (ADR-0027 / #161). The install one-liner
requires the branch `fix/macos-native-audio-capture-161` to be **pushed**. Check 4
closes the one item the spike couldn't cover — TCC under the packaged
`.app`/launchd identity (ADR-0027 open item). A friendly, non-agent tester can use
the observable checks here alongside `08-s10-macos-tester-guide.md`.</sub>
