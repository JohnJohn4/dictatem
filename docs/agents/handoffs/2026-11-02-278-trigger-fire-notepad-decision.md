# Decision memo: Trigger Fire mangled in Windows 11 Notepad (#278)

**For:** owner. **Date:** 2026-11-02. **Status:** awaiting decision. No code changed.

## Recommendation

**Do (b): route only `RichEditD2DPT` targets (Win11 Notepad) to select-and-paste.
Keep the typed `SendInput` path everywhere else.** For those targets a Trigger
Fire becomes: Shift down → Shift+Left × Backspace Units (paced, as today) →
Shift up → clutter-proof clipboard write → Ctrl+V → the existing deferred
restore (1.5 s, #66).

- Do **not** switch globally (option a). Shift+Left doesn't select in terminals
  and some chat inputs, and the typed path works there today.
- This is a narrow amendment to ADR-0004, not a reversal. Record it as a new
  Consequence: "known-bad editors get select-and-paste".
- **First, do a 10-minute pre-check (no code):** turn off Notepad's *Spellcheck*,
  *Autocorrect* and *Formatting* settings, then try the current build again. The
  result tells us the cause (see below). It doesn't change the recommendation.
  Pasting avoids Notepad's per-keystroke processing either way, and users won't
  turn those settings off for us.
- Keep the README known-issue note until the test below passes.

## Root cause: evidence vs inference

**Evidence**
- Win11 Notepad's editor is the Microsoft 365 RichEdit (not msftedit.dll),
  hosted in the `RichEditD2DPT` window class
  ([Murray Sargent, *Windows 11 Notepad*](https://devblogs.microsoft.com/math-in-office/windows-11-notepad/);
  [*RichEditD2D window controls*](https://devblogs.microsoft.com/math-in-office/richeditd2d-window-controls/)).
- Since 2024 Notepad has spellcheck and autocorrect, on by default
  ([Insider blog, 2024-03-21](https://blogs.windows.com/windows-insider/2024/03/21/spellcheck-in-notepad-begins-rolling-out-to-windows-insiders/)).
  Since 2025 it also has Markdown "lightweight formatting"
  ([Insider blog, 2025-05-30](https://blogs.windows.com/windows-insider/2025/05/30/text-formatting-in-notepad-begin-rolling-out-to-windows-insiders/)).
  So the editor now does work on each word you type.
- Other tools see the same class of failure, in Notepad only:
  - Microsoft's own winappCli lost about 566 of 1,000 injected chars, and
    throttling to 16 chars / 15 ms fixed it
    ([#657](https://github.com/microsoft/winappCli/issues/657),
    [PR #667](https://github.com/microsoft/winappCli/pull/667)).
  - Plover output in Notepad lags until the next physical input
    ([plover#1619](https://github.com/openstenoproject/plover/issues/1619)),
    and an AutoHotkey user reports the same.
- KEYEVENTF_UNICODE produces a `WM_KEYDOWN(VK_PACKET)`, which the target's own
  `TranslateMessage` turns into `WM_CHAR`
  ([KEYBDINPUT docs](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-keybdinput)).
  The target app decides what happens to each key.
- Our data (#275, #278):
  - `SendInput` accepted every event, both before and after pacing.
  - **VK** Backspaces were also under-delivered, even after pacing (the
    partial delete, `…the loLook`).
  - Regular dictation (a single Ctrl+V) into the same Notepad works.

**Inference (not proven)**
- Notepad handles a long stream of injected keys unreliably. This is not
  specific to VK_PACKET, because plain VK Backspaces failed too. Pacing fixed
  the dropped *count* but not the corruption.
- The repeated `c…c` and the blanks most likely come from Notepad's per-word
  processing (autocorrect/spellcheck/formatting run at word boundaries). That
  processing moves the caret or selection while our keys keep arriving.
- Supporting hint: winappCli's passing test typed 1,000 × `X` with no spaces,
  so no word boundary ever fired. It passed at about our own rate (~1,000
  keys/s), while our text with spaces did not.
- I found no public source that documents the repeat-character symptom itself.

**What this means for the options:** a single paste avoids per-keystroke text
processing. Only the selection keys remain, and they insert no text, so
autocorrect has nothing to act on. The selection count is still keystroke-based,
though, so the test below has to check that the span is exact.

## Options

| | What it fixes | #23 race risk | Win+V / clipboard risk | Effort | Testability |
|---|---|---|---|---|---|
| **(a) Select-and-paste everywhere** | Notepad (likely); single-step undo everywhere | Low–medium. See below. | Low: `set_text` and `restore` already apply the exclusion markers (ADR-0023). The user's clipboard is replaced for 1.5 s during each Trigger Fire. | S–M | Good |
| **(b) Same, `RichEditD2DPT` only** ✅ | Notepad (likely); nothing else changes | Same as (a), but only in Notepad | Same as (a), but only in Notepad | M: (a) plus a focus-class check in the Win32 adapter (the diag line already reads it) | Good; other apps don't need re-QA |
| **(c) VK/scan-code typing, slower pacing, other SendInput tweaks** | Unlikely to fix it. VK Backspaces already fail, and autocorrect still fires on typed spaces. | None (no clipboard) | None | S, but it needs layout mapping (`VkKeyScanEx`) and injected Shift for capitals | Good, but likely to fail |
| **(d) UI Automation** | TextRange can only *select*; the Text pattern has no write method. ValuePattern `SetValue` replaces the **whole document** ([MS docs](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-implementingtextandtextrange)). Usable only as a precise *selector* before Ctrl+V. | Same as (a) | Same as (a) | L: new COM dependency; provider quality varies by app (ADR-0023 already rejected UIA for this reason) | Medium |
| **(e) Leave it as a Known issue** | Nothing | None | None | 0 (README note already shipped) | n/a |

### The #23 race, re-checked

**What went wrong in #23:**
- 182 *unpaced* Backspaces went out as one batch, then Ctrl+V.
- The restore ran *synchronously 100 ms later*, while Notepad was still working
  through the Backspaces.
- So the target read the user's old clipboard.

**What is different now:**
1. The restore is deferred 1.5 s after Ctrl+V is sent (#66, `_RESTORE_DELAY_S`).
2. The selection keys are paced (#276), so the backlog in front of Ctrl+V is
   small.
3. Regular dictation already relies on (1) in this same Notepad, and it works.

**Remaining risk:** if Notepad falls more than about 1.5 s behind (the Plover
lag report says it can), it pastes the user's clipboard over the selection.
That is recoverable with Ctrl+Z, and the test below is designed to catch it.

**If the test catches it:** replace the timer with **delayed rendering**:
`SetClipboardData(CF_UNICODETEXT, NULL)`, serve the text on `WM_RENDERFORMAT`,
then restore. That is the only true "target has read it" signal Win32 offers.
It's a follow-up, not part of v1.

**Other costs of (a)/(b):**
- Shift is held for the whole selection phase. It must be released in a
  `finally` block, and the #269 modifier wait applies.
- If Ctrl+V fails, the original text stays on screen (selected). That is safer
  than today, where the Backspaces have already deleted it.
- Shift+Left steps by cluster in RichEdit. Treat that as **unverified** for
  ZWJ emoji, and test it.
- macOS is not affected. The Windows full-format clipboard snapshot is #243;
  #244 is its macOS half, still open.

## Verification test (owner, or an agent with a background recorder)

**Setup**
- Branch build, with the installed daemon stopped (#92).
- Background recorder running:
  - a `WH_KEYBOARD_LL` log of injected events (`LLKHF_INJECTED`, Dictatem's
    `dwExtraInfo` tag, timestamps);
  - an `AddClipboardFormatListener` log (sequence number, formats, whether the
    exclusion markers are present);
  - a Win+V history count before and after
    (`Clipboard.GetHistoryItemsAsync`).
- Read Notepad's text afterwards with UIA `DocumentRange.GetText`. No
  screenshots needed.

**Steps**
1. **Pre-check (current build).** Notepad: Spellcheck, Autocorrect and
   Formatting off. Dictate about 180 chars, then say "polish". Repeat 3×, then
   3× more with the settings back on. Write down which settings, if any, fix it.
2. **Fixture.** Put the canary string `CLIPBOARD-CANARY-278` on the clipboard,
   or a screenshot for the #243 snapshot case.
3. **Notepad, branch build.** Formatting on, autocorrect on. Run 10 Trigger
   Fires each at 20, 180 and 1,000 chars, plus one that keeps `café 👍🏽`.
   - **Pass when all of these hold:**
     - the document equals prefix + expected rewrite, 10/10;
     - the canary never appears in the document;
     - the clipboard is back to the canary within 2 s;
     - the Win+V history count is unchanged;
     - the recorder shows Ctrl+V after the last Shift+Left, and Shift released;
     - no `restore lost race` warning appears in `daemon.log`.
4. **Stress the race.** Open a 5 MB file in Notepad and repeat the 1,000-char
   case. If the canary appears, do the delayed-rendering follow-up before
   shipping.
5. **Regression.** Notepad++, a Chrome textarea and Windows Terminal stay on the
   typed path: the recorder shows `VK_PACKET`, no clipboard writes, and the
   result is correct.
