# Handoff — Implement clutter-proof clipboard + last-dictation recovery (S5)

**Type:** AFK implementation (code + tests + PRs). **This is not a design
session** — ADR-0023 is the settled spec. **Do not re-grill** the design; if you
think something is wrong, surface it (per `docs/agents/domain.md`) rather than
silently changing it.

**Goal:** Ship the three S5 issues so regular dictation never clutters the
Windows clipboard and a dictation that lands nowhere is recoverable by voice:

- **#138** — clutter-proof clipboard write (history/cloud exclusion markers).
- **#119** — Most-recent dictation buffer + tray "Copy last dictation".
- **#139** — built-in `paste` Trigger Word that re-pastes the buffer.

**Spec:** `docs/adr/0023-dictation-is-never-lost-clipboard-fallback.md`
(amended 2026-06-14). Vocabulary: `CONTEXT.md` — **Most-recent dictation**,
**Clutter-proof clipboard write**, **Trigger Word** (now covers built-in
actions). Use these terms in titles, tests, and commits.

## Order of work

1. **#138** — independent; touches only the win32 clipboard adapter. Do first or
   in parallel.
2. **#119** — introduces the **Most-recent dictation** buffer (the foundation
   #139 needs) + the tray copy item.
3. **#139** — the `paste` word. **Blocked by #119.**

**Branch per issue. Run `/code-review` before each PR. PRs target `main`.** Commit
any uncommitted work before spawning worktree agents (worktrees branch from
committed HEAD).

Skills: `tdd` (pure cores), `run`/`verify` (Windows behaviour), `code-review`.

## Architecture seam (preserve it)

Pure logic is unit-tested; Qt + native adapters are manual-QA. For each issue,
keep the *decision* pure and thin-wire the adapter:

- **#138:** isolate the marker registration/handle logic so it is unit-testable
  against a fake clipboard; the actual `SetClipboardData` is Windows manual-QA.
- **#119:** the buffer/retention logic is pure + tested; the tray item +
  clipboard copy are manual-QA.
- **#139:** the built-in-action detection + routing decision is pure + tested;
  the paste itself is manual-QA.

## HARD CONSTRAINTS — do not reopen (from ADR-0023 / ADR-0004)

- **Regular dictation pastes via clipboard + Ctrl+V.** Do **not** route it through
  `SendInput`/typed paste — that was rejected for regular dictation. ADR-0004 is
  correct and untouched (typed `SendInput` is Trigger Fire only).
- **Markers go on BOTH writes** — the transient dictation `set_text` *and* the
  `restore`. Marking only one leaves a duplicate-original entry in Win+V.
- **The buffer is a NEW persistent field**, not "stop clearing `_last_text`".
  `_last_text` doubles as the transient *pending paste payload* and is nulled
  after every paste (`daemon.py:790`) — keep that; add a separate field that
  survives pastes and holds the normalised + Replacements-applied dictation.
- **`paste` is decoupled from `[transform].enabled`.** Built-in action detection
  must run even when Transform is off and when there is no Last Paste — today
  `_detect_trigger` bails on both (`daemon.py:600,604`); the built-in path must
  bypass both gates. It reads the **Most-recent dictation** buffer, not Last
  Paste. Empty buffer → existing overlay error flash, never types the literal
  word "paste". The re-paste then becomes the new Last Paste.
- **`paste` matching reuses `transform.detector._normalise`** (strip whitespace +
  ASCII punctuation, lowercase) so `Paste.`/`paste?`/`PASTE` all fire and
  multi-word `paste this` does not. A user Prompt File aliased `paste` is
  **shadowed** by the built-in (warn on load).
- **Tray "Copy last dictation" is a NORMAL copy** (appears in Win+V) — it is an
  explicit user action; only the *automatic* dictation juggling is
  clutter-proofed. (Flagged reversible — flip to a clutter-proof write if it
  proves surprising.)

## Key files (reference, don't re-summarise the issues)

- `src/dictatem/paste/win32_clipboard.py` — `set_text` / `restore`; **where the
  exclusion markers go** (#138).
- `src/dictatem/paste/pipeline.py` — `paste()` clipboard path (#66 deferred
  restore). #138 rides this unchanged; no change to the Ctrl+V flow itself.
- `src/dictatem/daemon.py` — `_do_paste` (buffer set/clear, ~758-790),
  `_detect_trigger` (gating, 594-606), `check_transcription_result` (trigger
  routing, ~556-575); `DaemonCore` state for the buffer (#119) and `paste`
  routing (#139).
- `src/dictatem/transform/detector.py` — `_normalise`; reuse for the `paste`
  built-in (#139).
- `src/dictatem/tray/qt_tray.py` + `src/dictatem/tray/state.py` — `MenuItem`
  enum, `_MENU_LABELS`, `menu_item_enabled`; add "Copy last dictation" (#119).
- `src/dictatem/tray/usage_guide.py` — add a short "recover a lost dictation —
  say 'paste'" line (#139).
- `CONTEXT.md` / `docs/adr/0023-…` — vocabulary + spec.

## Manual-QA tail (Windows)

This box is Windows, so QA it yourself if you can; otherwise **export a QA
handoff** (`docs/agents/qa-handoffs/<NN>-<slug>.md`) — never claim QA passed
without a human on real hardware.

- **#138:** after a regular dictation, Win+V shows **no** new entry (no dictation
  text, no duplicated original); Ctrl+V still pastes correctly; original
  clipboard still restored; with cloud clipboard on, the dictation does **not**
  sync to another device.
- **#119:** tray "Copy last dictation" is disabled before any dictation, enabled
  after; clicking it copies the most-recent dictation; it survives intervening
  pastes.
- **#139:** with text dictated but landed nowhere, focusing a field and saying
  "paste" (and "Paste.", "PASTE") re-pastes it; works with Transform disabled;
  empty buffer → error flash, nothing typed.

## Definition of done

- [ ] #138, #119, #139 implemented to their acceptance criteria.
- [ ] Pure logic unit-tested; `pytest` + `pyright` + `ruff` green.
- [ ] `/code-review` run per PR; PRs merged to `main` (branch per issue).
- [ ] CONTEXT.md/ADR already carry the vocabulary — use it; update the Usage
      Guide section (#139) and any docs the behaviour changes.
- [ ] Manual-QA done by a human or exported as a QA handoff (never skipped).
- [ ] When all three land: roadmap **S5** row marked done, **Session Ledger**
      entry appended, **Current Session Prompt** rewritten for the next agent.

## Separate thread (don't lose it — not part of this session)

Single-instance guard **#92** on `feat/single-instance-guard-92` still owes
commit + `/code-review` + PR + the installer "stop the old daemon before swapping
files" upgrade. See `docs/agents/handoffs/single-instance-guard-92.md`.
