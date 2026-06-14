# Handoff — Clutter-proof dictation clipboard + reliable backup-paste (design)

**Type:** Grill / design session (decisions + docs, *not* a code PR).
**Goal:** Settle the definitions and design decisions so Dictatem's regular
dictation is **clutter-proof** (never pollutes the Windows clipboard history /
cloud clipboard) *and* has a **reliable backup-paste** path for the case where a
dictation doesn't land (no active text cursor). Output: amended **ADR-0023**,
sharpened **CONTEXT.md** vocabulary, and re-scoped implementation issues.

## Skills to use (in order)
1. **`grill-with-docs`** — stress-test the design against the existing domain
   language, sharpen terms, and write the ADR-0023 amendment + CONTEXT.md term
   updates *inline* as each decision lands. This is the primary skill.
2. **`to-issues`** — once the ADR amendment is settled, spin out / re-scope the
   implementation issues (tracer-bullet slices) on the tracker.

Follow the roadmap's **grill-session handoff** protocol (`docs/agents/roadmap.md`
§ Handoff protocol): the session is done when the ADR records the decision +
rejected options + consequences, CONTEXT.md terms are updated, issues are spun
out naming the ADR as spec, and the roadmap's ▶ Current Session Prompt is
rewritten so no one re-grills it.

## HARD CONSTRAINT — do not reopen
**Regular dictation pastes via the clipboard + Ctrl+V. SendInput/typed paste was
already tried for regular dictation and rejected — it is the wrong path.** Do
not relitigate it. (SendInput *is* correctly used for Trigger Fire only —
`replace_chars > 0`, ADR-0004. Leave that alone.) The clutter fix must be
achieved *without* abandoning Ctrl+V.

## The core insight (the lever the design should be built on)
Win+V clutter is **not** an inherent cost of using the clipboard. Windows lets a
clipboard *writer* opt each write out of clipboard **history** and **cloud
sync** via registered clipboard-format markers:
- `CanIncludeInClipboardHistory` (DWORD `0` → excluded from Win+V history)
- `CanUploadToCloudClipboard` (DWORD `0` → excluded from cloud sync)
- (`ExcludeClipboardContentFromMonitorProcessing` is the blunter all-monitors variant)

These were observed live on this machine — a clipboard read during QA showed an
image carrying exactly `CanIncludeInClipboardHistory, CanUploadToCloudClipboard`.
Setting them on Dictatem's writes makes Ctrl+V paste work unchanged while the
transient dictation write (and the restore) become **invisible to Win+V**.
`win32_clipboard.Win32ClipboardIO.set_text` does **not** set them today — that is
the root cause of the 3-entry history the user saw (dictation text + duplicated
original). Validate the exact pywin32 handle mechanics during implementation
(register the format, `SetClipboardData(fmt, <DWORD 0>)`); treat the *mechanism*
as proven, the *binding details* as TBD.

## Two distinct problems — keep them separate in the ADR
1. **Clutter (normal case).** Every regular dictation's clipboard juggling lands
   in Win+V. **Fix:** history + cloud exclusion markers on Dictatem's clipboard
   writes (the transient set *and* the restore). Thin change to the win32
   adapter; Windows manual-QA. **Not tracked by any issue yet — new issue.**
2. **Backup paste / recovery (no-target case).** When a dictation has nowhere to
   land (no active cursor), the text must be recoverable **without** cluttering
   the clipboard. ADR-0023 already settled the *philosophy* (no editable-focus
   detection — too unreliable across Electron/games/custom controls; guarantee
   "never lost" instead). The planned pieces:
   - **#119** tray "Copy last dictation" — reads an internal last-dictation
     buffer; zero new key bindings. (OPEN, `ready-for-agent`)
   - **#124** no-target auto-dump to clipboard + Overlay Pill notice. (OPEN,
     `ready-for-agent`) — **this is the one that clutters**; if kept, it should
     carry the exclusion marker so it replaces the *active* clipboard for Ctrl+V
     recovery without showing in Win+V history.
   - **#128** "paste last dictation" hotkey — re-pastes the most-recent dictation
     from the internal buffer; **cleanest for the clutter goal** (never leaves
     anything on the clipboard). Parked because it needs a **second** trigger
     binding and the classifier handled one combo. NOTE: #118 (mouse-button
     classifier, shipped in PR #133) is the groundwork that may now make the
     second binding feasible — re-evaluate the parked status. (OPEN, `backlog`)
   - **#129** opt-in auto-cleanup LLM pass — unrelated to clipboard; ignore here.

## The decision fork to resolve with the user
For no-target **backup paste**, which is primary?
- **(a) Paste-last hotkey (#128)** — cleanest (clipboard never touched), but needs
  the second-binding work first. *Lead recommendation* (matches the user's stated
  "don't clutter the clipboard" value).
- **(b) Clipboard-dump fallback (#124)** — zero new bindings, recovery = Ctrl+V
  muscle memory, but replaces the active clipboard (acceptable in the failure
  case if excluded from history).
- **(c) Both** — #124 now as the cheap catch-all, #128 as the clean follow-up.

The user is undecided and explicitly wants this **discussed/grilled**, not
assumed. Drive the decision tree; don't just pick.

## ADR-0023 conflict to fix (surface, don't silently override)
`docs/adr/0023-dictation-is-never-lost-clipboard-fallback.md` Consequences says
*"regular dictation and Trigger Fire never touch the clipboard."* That is
**factually wrong** vs the shipped pipeline (regular dictation uses clipboard +
Ctrl+V — confirmed correct by the user). Amend ADR-0023 so it records the real
design: regular dictation pastes via **clipboard + Ctrl+V with save/restore AND
history/cloud exclusion**, which is what actually delivers the "your clipboard
stays put / stays clean" property the ADR was reaching for. The "Always-also-copy
every dictation" rejected-option and the "Clipboard preservation is moot"
consequence both need revisiting under this reality.

## CONTEXT.md vocabulary to sharpen/add
`CONTEXT.md` currently defines **Last Paste** (the Trigger-Word operand) and
references **Clipboard Fallback** / "most recent dictation". The design needs
crisp, distinct terms — likely:
- **Most-recent dictation** (the internal buffer that backs copy-last / paste-last;
  exists even when nothing landed and no `target_id` was captured — distinct from
  **Last Paste**, which requires a successful paste and arms Trigger Words).
- A term for the **clutter-proof clipboard write** (history/cloud-excluded paste).
- A term for **backup paste** (the recovery action) vs the normal paste.
Reconcile these against the existing glossary so issue titles/tests/commits use
one vocabulary.

## Key files / artifacts (reference, don't re-summarise)
- `docs/adr/0023-dictation-is-never-lost-clipboard-fallback.md` — the ADR to amend.
- `docs/adr/0004-trigger-fire-types-via-sendinput-not-clipboard.md` — why Trigger
  Fire (only) types; the SendInput precedent. Do not extend it to regular dictation.
- `src/dictatem/paste/pipeline.py` — `paste()`: `replace_chars == 0` = clipboard
  path (set/Ctrl+V/deferred restore, #66); `replace_chars > 0` = typed path.
- `src/dictatem/paste/win32_clipboard.py` — `set_text`/`restore`; **where the
  exclusion markers must be added**.
- `CONTEXT.md` — glossary (Last Paste etc.).
- Issues: #119, #124 (`ready-for-agent`); #128, #129 (`backlog`/parked).
- `docs/agents/roadmap.md` — S5 is "Clipboard last-dictation rail (#119 → #124)";
  this design changes its scope. Update the roadmap row + ledger when done.

## Definition of done (grill session)
- [ ] ADR-0023 amended (real Ctrl+V design + clutter-proof exclusion + backup-paste
      decision; rejected options + consequences in house style).
- [ ] CONTEXT.md terms added/sharpened and used consistently.
- [ ] New issue created for the **clipboard history/cloud exclusion** clutter fix
      (win32 adapter, manual-QA). #119/#124/#128 re-scoped to the settled design;
      #128's parked status re-evaluated against #118.
- [ ] Roadmap S5 row + ▶ Current Session Prompt rewritten; ledger entry appended.
- [ ] No code beyond docs unless the user asks — this is a design session.

## Parallel state (separate thread — don't lose it)
The **single-instance guard (#92)** was implemented and partially QA'd in this
session, on branch **`feat/single-instance-guard-92`** (changes **uncommitted**):
- `src/dictatem/daemon.py`: `_acquire_single_instance_lock()` (QLockFile at
  `~/.dictatem/daemon.lock`, lazy import for import-safety) wired early in
  `_run_daemon`; logs `"Another Dictatem instance is already running; exiting"`.
- `tests/test_single_instance_guard.py` (5 tests). Full suite 955 passed; ruff +
  pyright clean.
- **Manual QA done & PASSED on this Windows box:** QA-1 (second instance exits,
  no second tray/process) and QA-2 (stale dead-PID lock is stolen, no deadlock).
  QA-3 (boot-smoke dictation) is what surfaced this clipboard design tangent.
- **Still owed for #92:** commit + `/code-review` + PR to `main`; the installer
  "stop running daemon before swapping files" upgrade-path follow-up; optional
  tray-flash UX. A dev daemon (the guarded build) may still be running in the
  background from QA — the installed v0.5.6 autostart build is NOT upgraded, so
  the double-paste can still recur at next login until #92 ships + the installer
  stops the old daemon (see `docs/agents/handoffs/single-instance-guard-92.md`).

Keep #92 and this clipboard design as **separate threads** — this handoff is the
clipboard design; #92 is just flagged so it isn't dropped.
