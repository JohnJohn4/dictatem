# Handoff — Session 3: Docs & discoverability

**You are the next agent in the roadmap.** This doc onboards you to one session.
It does not replace the issues or ADRs — it tells you where you are, what to do,
and how to hand off.

## How the roadmap works (read this first)

1. **`docs/agents/roadmap.md` is ground truth.** Read it now, top to bottom. Its
   **▶ Current Session Prompt** should already point you here.
2. The roadmap defines the **working principles**, the **session list (S1–S10)**,
   the **Definition of Done**, and the **handoff protocol**. You operate inside
   that frame — don't re-plan the backlog.
3. The backlog lives in GitHub Issues (`JohnJohn4/dictatem`, via `gh`). Read each
   issue + its named ADR before coding — the ADR is the spec; **don't re-decide a
   settled ADR.**
4. When you finish, run the **handoff protocol** (below): append a ledger entry,
   rewrite the Current Session Prompt, and flag/export any manual QA.

## Your role this session

Autonomous AFK implementer. These are small, low-risk docs + thin-wiring items.
The user reviews and merges your PRs. One light **Windows manual-QA** tail exists
(tray + first-run) — you can't fully self-verify the Qt/tray behaviour, so prepare
it for the user or export a QA handoff (see below).

**Skills:** `run` / `verify` (drive the app to eyeball the tray items + first-run),
`code-review` before each PR. Branch per issue; PRs to `main`.

## What just landed (Session 2 — context)

Two PRs are open (likely merged by the time you read this — check):
- **PR #133** (#118) — mouse buttons as trigger inputs in the pure
  `HotkeyClassifier` (`Key.MOUSE_4/5/MIDDLE`, curated allow-list, conditional
  suppression). Pure-logic; unblocks the Windows/macOS mouse hooks (#120/#121).
- **PR #134** (#125 + #126, ADR-0024) — Vocabulary + Replacements: pure parsers in
  `src/dictatem/transcribe/{replacements,vocabulary}.py`, replacements applied to
  **regular dictation only** (after trigger detection), vocabulary fed as
  `hotwords`/`initial_prompt`. Two `~/.dictatem/*.md` files bootstrapped opt-in.

If either is still open, **do not rebuild it** — just proceed; your work doesn't
touch those files.

## Session 3 scope (4 issues)

Read each issue (`gh issue view <n>`) and its ADR before touching code.

| Issue | What | ADR | First look | Gotcha |
|---|---|---|---|---|
| **#67** | Docs: lazy-load / idle-unload model + managed-machine AV/EDR first-launch note | ADR-0016 | README + first-run docs | **Docs-only now** — the loading pill already shipped (#74). Don't re-implement UI. |
| **#127** | Default Polish prompt + manual-cleanup docs | ADR-0003 (prompts as frontmatter md) | `src/dictatem/transform/prompts.py` (first-run prompt bootstrap) | Bootstrap a default Polish prompt; document it. Ties to ADR-0024's "clean if you ask" stance. |
| **#122** | Auto-open Usage Guide on first run | ADR-0021 | `src/dictatem/tray/usage_guide.py`, daemon first-run sequencing | Use a **sentinel marker**, NOT a config flag — `config.toml` is never app-rewritten (ADR-0009/0022). |
| **#123** | Config discoverability: tray "Open config…" item + Guide "Changing your hotkey" section | ADR-0022, ADR-0019 | `tray/qt_tray.py` `_open_log`/`_open_usage_guide` (reuse the open-default pattern), `tray/usage_guide.py` | The Guide section must reflect the **live** Hotkey Combo (reuse `format_hotkey()`); list the curated vocab incl. the new `mouse4/mouse5/middle` from #118. |

Suggested order: **#67 → #127** (pure docs/bootstrap, fully AFK) then **#122 → #123**
(tray/first-run wiring with a Windows QA tail). #122 and #123 both touch the
tray/first-run path — do them in sequence (or one PR) to avoid self-conflict.

## Definition of Done (this session)

- Each issue's acceptance criteria met; `pytest` / `pyright` / `ruff` green.
- Any pure logic (e.g. the sentinel-marker gate for #122) is unit-tested; tray /
  first-run wiring stays thin.
- `/code-review` run per PR; docs/CONTEXT updated where vocabulary changed.
- **Manual-QA handled** (see below) — never claimed-passed without a human.
- Roadmap **ledger** appended + **Current Session Prompt** rewritten to **Session 4
  — CI keystone + install hardening** (worth pulling early; it's the verification
  surface for the macOS track).

## Manual-QA for this session

Light Windows-only checks you cannot fully self-verify:
- **#122** — on a clean profile (no sentinel marker), first daemon run auto-opens
  the Usage Guide exactly once; second run does not.
- **#123** — tray shows "Open config…" and it opens `config.toml` in the default
  editor; the Guide's "Changing your hotkey" section shows the live combo.

If the user is at a Windows machine, give them this as an in-chat checklist. If
not, **export a QA handoff** to `docs/agents/qa-handoffs/03-docs-discoverability-qa.md`
(template in the roadmap) and leave #122/#123 open until a human verifies.

> Note: Session 2 left one small manual-QA item — **#126 vocabulary recognition
> lift** needs a real model on Windows to confirm `hotwords` actually improves
> recognition. The procedure is already written up at
> [`../qa-handoffs/02-vocabulary-recognition-qa.md`](../qa-handoffs/02-vocabulary-recognition-qa.md) —
> the user has it queued; surface its result if it lands during your session.

## When done — hand off

Follow the roadmap's **Handoff protocol**: ledger entry, rewrite the Current
Session Prompt (point at Session 4), and create the next handoff doc if it helps
the following agent. Commit the doc updates.
