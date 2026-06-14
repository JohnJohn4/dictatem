# QA Handoff — Session S5: Clutter-proof clipboard + last-dictation recovery (#138 / #119 / #139)

**Device required:** Windows 11, with a real Whisper model and your usual
microphone. Win+V (Clipboard history) must be **on** (Settings → System →
Clipboard → "Clipboard history"). For the cloud-clipboard check, "Sync across
your devices" must be on and signed in.
**Build under test:** `main` after PRs **#141** (#138), **#142** (#119), and
**#143** (#139) are all merged. Run from the **dev clone**, not the installed
`dictatem` — the installed tool is pinned to **v0.5.6** and won't contain this
work until a new tag is cut.
**Why this is manual:** the win32 `SetClipboardData` markers, the Qt tray item,
and the real Ctrl+V paste are native/Qt adapters — the pure logic (marker
decision, buffer retention, `paste` routing) is already machine-tested; this
confirms the *behaviour* on real hardware, including the one thing no test can
see: whether Win+V history actually stays clean.

## Prerequisites
- Run the merged code from the clone:
  ```
  cd C:\Code\dictatem
  uv run python -m dictatem
  ```
- Transform is **not** required for the `paste` recovery (it's a built-in
  action). If you want to exercise the "works with Transform disabled" case,
  set `[transform].enabled = false` in `C:\Users\johnc\.dictatem\config.toml`
  and restart; for the "armed Trigger Word after paste" case, leave it enabled
  with Ollama running.
- Log: tray **"Open log"**, or `%APPDATA%\Dictatem\logs\daemon.log`.
- Have a known string on your clipboard before each #138 run (e.g. copy
  "ORIGINAL-XYZ" from Notepad) so you can confirm it's restored and not
  duplicated.

## Checklist (run on the Windows machine)

### #138 — Clutter-proof clipboard write (~5 min)
- [ ] Copy a recognisable string (e.g. `ORIGINAL-XYZ`) so it's your current
      clipboard. Open Notepad, focus it, dictate a short phrase, let it paste.
      **Expect:** the phrase is typed into Notepad correctly (Ctrl+V path
      unchanged). · **Issue:** #138
- [ ] Press **Win+V**. **Expect:** **no** new entry for the dictation text and
      **no** duplicate of `ORIGINAL-XYZ` — the dictation juggling left Win+V
      history untouched. · **Issue:** #138
- [ ] Press **Ctrl+V** in Notepad now. **Expect:** `ORIGINAL-XYZ` pastes — your
      original clipboard was restored (the deferred #66 restore), and it's the
      original, not the dictation. · **Issue:** #138
- [ ] (Cloud, optional) With "Sync across devices" on, dictate, then check the
      clipboard on another signed-in device. **Expect:** the dictation text did
      **not** sync. · **Issue:** #138

### #119 — Most-recent dictation buffer + "Copy last dictation" (~3 min)
- [ ] Fresh start, before any dictation: open the tray menu. **Expect:** **"Copy
      last dictation"** is present but **disabled** (greyed). · **Issue:** #119
- [ ] Do one dictation. Open the tray menu again. **Expect:** "Copy last
      dictation" is now **enabled**. · **Issue:** #119
- [ ] Click **"Copy last dictation"**, then Ctrl+V into Notepad. **Expect:** the
      most-recent dictation text pastes. Press **Win+V** — this copy **should**
      appear in history (it's an explicit copy, deliberately not clutter-proofed,
      unlike the automatic dictation write). · **Issue:** #119
- [ ] Do a second, different dictation, then click "Copy last dictation" again.
      **Expect:** it copies the **newer** dictation (the buffer tracks the
      latest and survives the intervening paste). · **Issue:** #119

### #139 — built-in `paste` recovery (~5 min)
- [ ] Dictate a sentence **with focus on something non-editable** (e.g. click the
      desktop / an empty area) so it lands nowhere. Now click into Notepad and
      say **"paste"** on its own. **Expect:** the lost dictation appears in
      Notepad. · **Issue:** #139
- [ ] Repeat saying **"Paste."** and **"PASTE"** (case/punctuation variants).
      **Expect:** all forms fire. Say **"paste this"** (two words). **Expect:** it
      is typed as regular dictation, not treated as the command. · **Issue:** #139
- [ ] With `[transform].enabled = false` (restart first), confirm "paste" still
      re-pastes. **Expect:** works with Transform off. · **Issue:** #139
- [ ] Fresh start with an **empty** buffer (no dictation yet): focus Notepad and
      say "paste". **Expect:** the overlay flashes its **error**; **nothing** is
      typed (it never types the literal word "paste"). · **Issue:** #139
- [ ] (Transform on, Ollama running) Dictate, say "paste" to re-paste, then say a
      configured Transform word (e.g. "summarize"). **Expect:** the Transform
      fires on the re-pasted text — the re-paste became the new Last Paste.
      · **Issue:** #139
- [ ] (Optional) Drop a Prompt File whose alias is `paste` into
      `~/.dictatem/prompts/`, restart, and check the log. **Expect:** a warning
      that the `paste` alias is shadowed by the built-in. · **Issue:** #139

## What to capture
- A Win+V screenshot after a dictation (#138) showing no new/duplicate entry.
- The "Copy last dictation" item disabled→enabled (#119).
- A note that "paste" recovered a lost dictation, plus the empty-buffer error
  behaviour (#139).
- Any log lines (e.g. `paste` action re-paste, or the shadowed-alias warning).

## Gotchas
- Win+V history must be **enabled** or the #138 "no new entry" check is moot
  (nothing is ever recorded). Confirm it's on first by copying normally and
  seeing the entry appear.
- The original-clipboard restore is **deferred ~1.5 s** (#66) — give it a moment
  before the Ctrl+V check.
- `paste`/`summarize` must be said as the **lone word** right after recording;
  multi-word utterances are dictation by design.
- Run from the **clone**, not the installed v0.5.6 tool.

## On result
- **PASS** → comment the evidence (screenshots/log lines) on **#138**, **#119**,
  and **#139** respectively and close each; mark QA done in the **S5 ledger**
  entry in `docs/agents/roadmap.md`.
- **FAIL** → comment the captured evidence on the relevant issue, reopen/keep it
  open, and note the hypothesis. Likely suspects: the win32 marker handle
  mechanics (#138) if a dictation still shows in Win+V; the tray enable wiring
  (#119); or the buffer/routing (#139) if "paste" mis-fires. Don't silently drop.
