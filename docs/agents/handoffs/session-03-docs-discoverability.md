# Handoff — Session 3: Docs & discoverability

**You are the next agent in the roadmap.** This doc onboards you to one session.
It does not replace the issues or ADRs — it tells you where you are, what to do,
and **how to hand off when you're done** (post-S3 sequencing at the bottom).

## How the roadmap works (read this first)

1. **`docs/agents/roadmap.md` is ground truth.** Read it now, top to bottom. Its
   **▶ Current Session Prompt** should already point you here.
2. The roadmap defines the **working principles**, the **session list (S1–S10)**,
   the **Definition of Done**, and the **handoff protocol**. You operate inside
   that frame — don't re-plan the backlog.
3. The backlog lives in GitHub Issues (`JohnJohn4/dictatem`, via `gh`). Read each
   issue + its named ADR before coding — the ADR is the spec; **don't re-decide a
   settled ADR.**
4. When you finish, run the **handoff protocol** (the roadmap's + the post-S3
   notes below): append a ledger entry, rewrite the Current Session Prompt, and
   flag/export any manual QA.

## Your role this session

Autonomous AFK implementer. These are small, low-risk docs + thin-wiring items.
The user reviews and merges your PRs. One light **Windows manual-QA** tail exists
(tray + first-run) — you can't fully self-verify the Qt/tray behaviour, so prepare
it for the user or export a QA handoff (see below).

**Skills:** `run` / `verify` (drive the app to eyeball the tray items + first-run),
`code-review` before each PR. Branch per issue; PRs to `main`.

## Where the project is (what landed before you)

- **S5 — clutter-proof clipboard + last-dictation recovery** (v0.5.7, ADR-0023):
  regular dictation no longer pollutes Win+V history/cloud (#138); a Most-recent
  dictation buffer + tray "Copy last dictation" (#119); a built-in **`paste`**
  Trigger Word recovers a dictation that landed nowhere (#139). Settled — don't
  re-grill (the #124 auto-dump / #128 hotkey were considered and rejected).
- **Cleanup + reliability pass (2026-06-19):** tracker/branch hygiene (closed
  #137 as superseded; pruned dead branches; retired the stale `feat/macos-track`),
  the **single-instance guard #92** (PR #148 — `QLockFile`, best-effort degrade),
  and the **#145 clipboard-contention fix** (PR #149 — the win32 adapter now
  translates `pywintypes.error` → `OSError` so the paste retry/swallow engages;
  relates to #93). Both merged; suite green.
- Net: **S4 is now just #81 + #90** (#92 done). **20 issues open.**

Nothing above is yours to redo. If you spot a contradiction with an ADR, surface
it (per `docs/agents/domain.md`) rather than silently overriding.

## Session 3 scope (4 issues)

Read each issue (`gh issue view <n>`) and its ADR before touching code.

| Issue | What | ADR | First look | Gotcha |
|---|---|---|---|---|
| **#67** | Docs: lazy-load / idle-unload model + managed-machine AV/EDR first-launch note | ADR-0016 | README + first-run docs | **Docs-only now** — the loading pill already shipped (#74). Don't re-implement UI. |
| **#127** | Default Polish prompt + manual-cleanup docs | ADR-0003 | `src/dictatem/transform/prompts.py` (first-run prompt bootstrap) | Bootstrap a default Polish prompt; document it. Ties to ADR-0024's "clean only if you ask" stance. |
| **#122** | Auto-open Usage Guide on first run | ADR-0021 | `src/dictatem/tray/usage_guide.py`, daemon first-run sequencing | Use a **sentinel marker**, NOT a config flag — `config.toml` is never app-rewritten (ADR-0009/0022). |
| **#123** | Config discoverability: tray "Open config…" + Guide "Changing your hotkey" section | ADR-0022, ADR-0019 | `tray/qt_tray.py` (reuse the open-default pattern), `tray/usage_guide.py` | The Guide section must reflect the **live** Hotkey Combo (reuse `format_hotkey()`); list the curated vocab incl. `mouse4/mouse5/middle` from #118. |

Suggested order: **#67 → #127** (pure docs/bootstrap, fully AFK, no QA) then
**#122 → #123** (tray/first-run wiring with a Windows QA tail). #122 and #123 both
touch the tray/first-run path — do them in sequence (or one PR) to avoid
self-conflict.

## Definition of Done (this session)

- Each issue's acceptance criteria met; `pytest` / `pyright` / `ruff` green.
- Any pure logic (e.g. the sentinel-marker gate for #122) is unit-tested; tray /
  first-run wiring stays thin (the architecture seam).
- `/code-review` run per PR; `CONTEXT.md` updated where vocabulary changed.
- **Manual-QA handled** (see below) — never claimed-passed without a human.
- Roadmap **ledger** appended + **Current Session Prompt** rewritten (see post-S3
  sequencing for what to point at).

## Manual-QA for this session

Light Windows-only checks you cannot fully self-verify:
- **#122** — on a clean profile (no sentinel marker), first daemon run auto-opens
  the Usage Guide exactly once; second run does not.
- **#123** — tray shows "Open config…" and it opens `config.toml` in the default
  editor; the Guide's "Changing your hotkey" section shows the live combo.

If the user is at a Windows machine, give them this as an in-chat checklist. If
not, **export a QA handoff** to `docs/agents/qa-handoffs/03-docs-discoverability-qa.md`
(template in the roadmap) and leave #122/#123 open until a human verifies.

> Carried over: **#126 vocabulary recognition lift** (S2) still needs a real model
> on Windows — procedure at
> [`../qa-handoffs/02-vocabulary-recognition-qa.md`](../qa-handoffs/02-vocabulary-recognition-qa.md).
> Surface its result if it lands during your session.

## Post-S3 sequencing — how to hand off when you're done

Run the roadmap's **Handoff protocol**: append a Session Ledger entry, rewrite the
**▶ Current Session Prompt**, and (optionally) write the next session's handoff
doc. **Lead the next prompt with a recommendation.** Point the next agent at
whichever of these the user picks:

1. **S4 — CI keystone + install hardening (#81, #90) — recommended next, "do
   early".** #81 adds the GitHub Actions matrix (`macos-latest` + `windows-latest`,
   py3.11–3.13; ruff/pyright/pytest + import-safety) — **there is no real CI
   today**, and it is the verification surface that makes the whole macOS track
   machine-checkable. #90 pins a uv-managed CPython on Windows x64 (mirroring
   `install.sh`) + a test asserting the pinned versions appear in the CI matrix.
   *Heads-up:* a `ci/bump-actions-node24` commit is on `main` — confirm whether a
   real workflow exists or only a stub. *QA:* none beyond CI going green.
2. **S6 — Windows mouse hook (#120).** A `WH_MOUSE_LL` adapter feeding the S2
   classifier core (#118, already merged) so a mouse side-button can trigger
   dictation — **a feature the user wants**, and Windows-testable end-to-end here.
   *QA:* physically click mouse4 / mouse5 / middle.
3. **S7 — Cold-start latency design grill (#101).** Code-free, parallel-safe, and
   the **deepest real-user complaint** ("wait minutes for the first transcribe",
   plus the paste misfiring because focus drifts during the long load). Produces a
   short ADR + spun-out issues; it decides #97's approach (anchor-the-target vs
   detect-and-warn) and frames #96 / #67. Use `grill-with-docs` / `prototype`.
   Unblocks **S8** (#96, #97).

The **macOS track** (S9: #93/#94/#95/#121; S10 signing: #91) waits for a real-Mac
QA day — export QA handoffs; **never claim Mac QA without the device**. **Parked**
(no build without a fresh user go-ahead): #72, #80, #129, #130 (speech-helper
spike — use `prototype`), #131.

If the user gives no steer, recommend **S4** next (it unblocks the most macOS
work), then **S6** (high-value + Windows-testable), with **S7** runnable any time
in parallel.
