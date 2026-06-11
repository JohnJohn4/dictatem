# Architectural Roadmap & Session Protocol

This document is the **ground truth** for agents working the Dictatem backlog. It
exists so any fresh agent can open a session, read one block, and know exactly
*where it is, what to do, when it's done, and how to hand off* — without
re-deriving the whole plan.

**How to use it**
1. Read **▶ Current Session Prompt** below — it tells you which session to run and
   why it matters in the bigger picture.
2. Read **Working principles** and your session's row in **The roadmap**.
3. Do the work. Honour the **Definition of Done**.
4. Before you stop, run the **Handoff protocol**: update the ledger, rewrite the
   Current Session Prompt for the next agent, and flag/export any manual QA.

The backlog itself lives in GitHub Issues (`JohnJohn4/dictatem`). This doc
*orchestrates* those issues; it does not replace them. Issue bodies + the
named ADR remain the per-feature spec.

---

## ▶ Current Session Prompt

> _The closing agent of each session rewrites this block using the template in
> the Handoff protocol. It is the first thing the next agent reads._

**Next up: Session 3 — Docs & discoverability.**

➡️ **Full handoff: [`docs/agents/handoffs/session-03-docs-discoverability.md`](handoffs/session-03-docs-discoverability.md)** — read it first.

Session 2 shipped the pure-logic cores: **PR #133** (#118 mouse-button classifier)
and **PR #134** (#125 Replacements + #126 Vocabulary, ADR-0024) — both reviewed,
pure-logic-tested, 924 tests green. This session is small docs + thin
discoverability wiring: **#67** (lazy-load/idle-unload docs — docs-only now),
**#127** (default Polish prompt + cleanup docs), **#122** (auto-open Usage Guide on
first run — **sentinel marker, never rewrite config.toml**), **#123** (tray "Open
config…" + Guide "Changing your hotkey" section reflecting the live combo, incl.
the new `mouse4/mouse5/middle` vocab). Do #122/#123 in sequence — they share the
tray/first-run path. There is a light **Windows manual-QA** tail (first-run
auto-open; tray open-config) — give the user a checklist or export a QA handoff;
don't claim it passed without a human. When done, point the prompt at **Session 4 —
CI keystone + install hardening** (pull it early — it's the macOS verification
surface).

Skills: `run`/`verify`, `code-review`. Your role: autonomous; the user reviews and
merges the PRs and runs the Windows QA.

---

## Working principles

These are durable. They override convenience; don't relitigate them mid-session.

- **The architecture seam: pure logic is unit-tested; Qt + native adapters are
  manual-QA.** Keep every new *decision* (classifiers, parsers, reconcile/marker
  gates, no-target decisions, permission mappers) pure and tested. Keep the OS
  hook / tray / pill / install wiring thin. This split is *why* features are
  sliced into pure-core vs adapter issues — preserve it in new work.
- **Local-first.** No cloud anything, ever.
- **Thin uv-tool install; no settings UI.** Config is a hand-edited
  `~/.dictatem/config.toml` made *discoverable* (ADR-0022), never a config-editing
  window. `config.toml` is **never rewritten by the app** (ADR-0009); per-feature
  state uses sentinel markers, not config flags.
- **Windows-first for native hooks; macOS is a labelled follow-up.** Mac-only work
  carries `needs-real-mac-qa` and follows the Manual-QA handoff.
- **ADRs are the spec.** Read the ADR named in an issue before coding. Do **not**
  re-grill or reverse a settled ADR; if your work contradicts one, surface it
  (per `docs/agents/domain.md`) rather than silently overriding.
- **Use the glossary's vocabulary** (`CONTEXT.md`) in issue titles, tests, commits.
- **Branch per issue. Commit before spawning worktree agents** (worktrees branch
  from committed HEAD; uncommitted work gets recreated by parallel agents). Run
  `/code-review` before each PR. PRs target `main`.
- **Lead with a recommendation** when reporting options to the user.

## Roles

| | The agent (you) | The user (HITL) |
|---|---|---|
| **AFK sessions** | Implement end-to-end, write tests, run `/code-review`, open the PR | Review & merge the PR |
| **Grill / design sessions** | Ask, challenge, draft the ADR + spun-out issues | Make the calls; the decisions are theirs |
| **Manual-QA** | Prepare the build & checklist; QA yourself if you have the device; else **export a QA handoff** | Run the checklist on real Windows/Mac hardware, or kick off a fresh QA agent from the handoff |
| **Spend / accounts** | Lay out the trade-off | Owns the decision (e.g. Apple Developer $99/yr) |

The user is **not** expected to babysit AFK sessions. They *are* expected to:
make decisions in grill sessions, run (or delegate) manual QA, approve PRs, and
own anything that costs money or needs their identity.

## Session types

- **AFK** — autonomous code. Agent runs the whole loop; user reviews the PR. May
  still produce a *Manual-QA* tail (see below).
- **Grill / Design (HITL)** — interactive, code-free. Produces an **ADR** + a set
  of spun-out implementation issues. User makes the decisions. Uses the
  grill-session handoff.
- **Manual-QA** — needs a human on real hardware (Windows for hooks/tray/overlay,
  a Mac for the macOS track). The agent prepares; if the user can't QA now (or
  lacks the device), the agent **exports a QA handoff file** so a fresh agent can
  drive it later. **Never report manual-QA as passed without a human having run it.**

---

## The roadmap

Ordered so cheap / high-value / independent work comes first, dependencies are
respected, and each session is one coherent skill mode. Sizes: **S** ≈ part of a
session · **M** ≈ one focused session · **L** ≈ may span more than one.

| # | Session | Type | Size | Issues | Skills | Depends on |
|---|---|---|---|---|---|---|
| ~~**S1**~~ | ~~Triage & close-out~~ | AFK | S | ✅ #82 #83 #34 #51 — closed | `triage` | done 2026-06-11 |
| ~~**S2**~~ | ~~Pure-logic feature cores~~ | AFK | M | ✅ PR #133 (#118) · PR #134 (#125 #126) | `tdd`, `code-review` | done 2026-06-11 |
| **S3** | Docs & discoverability | AFK | S–M | #67 #127 #122 #123 | `run`/`verify`, `code-review` | — |
| **S4** | CI keystone + install hardening | AFK | M | #81 #90 #92 | `code-review`, `diagnose` | — *(do early)* |
| **S5** | Clipboard last-dictation rail | AFK | M | #119 → #124 | `tdd`, `run`/`verify`, `code-review` | — |
| **S6** | Windows mouse hook | AFK | M | #120 | `run`/`verify`, `diagnose`, `code-review` | S2 (#118) |
| **S7** | Cold-start latency **design** | Grill | — | #101 (frames #97 #96 #67) | `grill-with-docs`, `prototype` | — *(parallel-safe)* |
| **S8** | Overlay & focus UX | AFK | M | #96 #97 | `run`/`verify`, `code-review` | S7 |
| **S9** | macOS QA & polish | Manual-QA + AFK | L | #121 #95 #94 #93 | `verify`/`run`, `tdd`, `diagnose` | S2 (#118), S4 |
| **S10** | Signing decision | Grill | — | #91 | `grill-me` | user spend call |
| **—** | Parked backlog | — | — | #72 #80 #128 #129 #130 #131 | `prototype` (#130 spike) | fresh go-ahead |

**Critical path:** S1 → S2 (#118) → S6 / S9 (mouse hooks). **Slot S4 early** — it
is the CI verification surface that turns most macOS work into machine-checkable
work. **S7 is code-free and parallel-safe** — run it any time; it unblocks S8.

### Per-session detail

**S1 — Triage & close-out.** Close #82 and #83 (verified shipped). Audit #34 and
#51 slice-by-slice against their ADRs (0006/0007/0008/0009 and 0011–0018); post a
residual checklist on each; close fully-shipped slices, rescope the rest, and
spin out genuinely-untracked residual as focused issues. *DoD:* tracker reflects
only real remaining work; ledger + prompt updated. *No QA.*

**S2 — Pure-logic feature cores (TDD).** #118 mouse-button classifier core
(ADR-0020), #125 Replacements parser (ADR-0024), #126 custom Vocabulary →
faster-whisper hints (ADR-0024). All pure, fully unit-testable. Independent →
candidate for three parallel worktree agents (commit first). #118 unblocks
#120/#121. *DoD:* modules + tests green, pyright clean, PR per issue. *No QA.*

**S3 — Docs & discoverability.** #67 lazy-load/idle-unload docs (docs-only now),
#127 default Polish prompt + cleanup docs, #122 auto-open Usage Guide on first run
(sentinel marker, ADR-0021), #123 config discoverability (tray "Open config…" +
Guide section, ADR-0022). *QA:* light Windows eyeball of tray + first-run — flag
to user or export a QA handoff.

**S4 — CI keystone + install hardening.** #81 GitHub Actions matrix
(`macos-latest` + `windows-latest`, py3.11–3.13; ruff/pyright/pytest +
import-safety) — there is **no CI today**; this is the verification surface for
the whole macOS track. #90 pin a uv-managed CPython on Windows x64 + a test
asserting pinned versions appear in the matrix (pairs with #81). #92
cross-platform single-instance guard (`QLockFile`). *QA:* Windows boot smoke for
#92.

**S5 — Clipboard last-dictation rail.** #119 tray "Copy last dictation"
(ADR-0023), then #124 no-target fallback to clipboard + overlay notice (ADR-0023,
blocked by #119). Keep the no-target *decision* pure and tested; thin tray/overlay
wiring. *QA:* Windows tray + overlay.

**S6 — Windows mouse hook.** #120 `WH_MOUSE_LL` adapter feeding the S2 classifier
(ADR-0020). *QA:* Windows — physically click mouse4/mouse5/middle.

**S7 — Cold-start latency design (grill).** #101 grilling session → a short ADR +
spun-out implementation issues; decide #97's approach (anchor-target-at-record-
start vs detect-and-warn) and frame #96's overlay states + #67's docs. Code-free.
Follows the **grill-session handoff**.

**S8 — Overlay & focus UX.** #96 remove the non-interactive red dot → encode state
via waveform colour; #97 anchor the paste target (per S7's decision). *QA:*
Windows overlay.

**S9 — macOS QA & polish.** #121 macOS mouse hook (after #118), #95 first-run
onboarding (pure permission mapper is testable; dialog copy + re-prompt-on-use),
#94 finish the QA runbook, #93 diagnose intermittent paste-not-landing. CI (S4)
makes the pure parts machine-checkable; the rest is **real-Mac Manual-QA** — if no
Mac is available, export a QA handoff.

**S10 — Signing decision (grill).** #91 clean TCC identity — a **decision**, not a
ticket: pay for a Developer-ID + notarization pipeline vs. accept the `python3.12`
label (ADR-0014 amendment). Needs the user's spend call.

**Parked — do not build without a fresh go-ahead:** #128 paste-last hotkey, #129
auto-cleanup-every-dictation, #131 tracking issue, #72 PyPI publish, #80 native
Windows-ARM. #130 speech-helper is a **spike** — when picked up, use `prototype`
(ties to the speech-helper direction memory).

---

## Definition of Done (every session)

Before you run the handoff, confirm:

- [ ] The session's issues are implemented to their acceptance criteria, or the
      grill produced its ADR + spun-out issues.
- [ ] Pure logic has unit tests; `pytest` + `pyright` + `ruff` are green.
- [ ] `/code-review` was run on the diff (for code sessions).
- [ ] Docs/ADRs/CONTEXT.md updated where the work changed behaviour or vocabulary.
- [ ] **Manual-QA is either done by a human, or exported as a QA handoff** — and
      never silently skipped or claimed-passed.
- [ ] **Session Ledger** appended; **Current Session Prompt** rewritten for the
      next agent.
- [ ] Branch/PR conventions followed (branch per issue, PR to `main`).

---

## Handoff protocol

### Generic (end of every session)

1. Append a **Session Ledger** entry (template below): what shipped, PRs, issues
   closed/opened, follow-ups, and any QA still owed.
2. Rewrite **▶ Current Session Prompt** using the template below so the next agent
   has context + their starting point.
3. Commit the doc change. Report to the user: what landed, any PRs to review, and
   **any manual QA they (or a QA agent) need to run**.

### Grill / design-session handoff

A grill session's output is *decisions*, not a PR. It is done when:

- The **ADR** is written in `docs/adr/` (next free number) and records the
  decision, the considered-and-rejected options, and the consequences — in the
  house style (see existing ADRs).
- **CONTEXT.md** terms are added/updated for any new vocabulary the decision
  introduces.
- **Implementation issues are spun out** (`gh issue create`), each naming its ADR
  as the spec and carrying acceptance criteria + any Blocked-by, labelled
  `ready-for-agent`.
- The Current Session Prompt points implementers at the new ADR + issues and
  **states the decision plainly so the next agent does not re-grill it.**

### Manual-QA handoff

If a session has a manual-QA tail and the user can run it now (right device on
hand), give them a tight in-chat checklist and let them confirm. **If they can't**
(no Windows / no Mac, or deferring), write a QA handoff file so a fresh agent can
drive it later:

- Path: `docs/agents/qa-handoffs/<NN>-<slug>.md` (e.g. `09-macos-v0.5-qa.md`).
  Create the `qa-handoffs/` directory lazily on first use.
- Use the **QA Handoff template** below.
- Tell the user the file path and that they can start a fresh agent with:
  *"Run the QA handoff at `docs/agents/qa-handoffs/<NN>-<slug>.md`."*
- Leave the relevant issues open with a note that QA is pending; do **not** close
  them on unverified work.

### Next-Session-Prompt template

```
**Next up: Session <N> — <title>.**

<2–4 sentences: what just landed and why it matters; what this session must do;
any decision the previous session settled that this one should NOT reopen;
where to look first (ADR / files / ledger entry).>

Skills: <list>. Your role: <autonomous / decisions-needed / manual-QA on <device>>.
<If a QA handoff is owed: "QA pending — see docs/agents/qa-handoffs/<file>.">
```

### QA Handoff template

```
# QA Handoff — Session <N>: <title>

**Device required:** <Windows 11 / macOS arm64 (+Intel if possible)>
**Build under test:** <branch / tag / commit> · install: <one-liner or steps>
**Why this is manual:** <native adapter / Qt / TCC — not machine-verifiable>

## Prerequisites
- <Ollama + `ollama pull …`, GPU, permissions granted, etc.>

## Checklist (tick on a real device)
- [ ] <Step> → **Expect:** <observable result> · **Issue:** #<n>
- [ ] …

## What to capture
- <screenshots / log lines / the exact failure text>

## On result
- PASS → comment the evidence on each issue and close it.
- FAIL → comment the captured evidence; reopen/keep the issue; note the hypothesis.
```

---

## Guardrails (do-not)

- Don't build **parked** issues (#72 #80 #128 #129 #130 #131) without a fresh
  user go-ahead.
- Don't **re-grill or reverse a settled ADR.** Surface conflicts instead.
- Don't **rewrite `config.toml`** from the app — use sentinel markers.
- Don't **claim manual QA passed** without a human running it on the device.
- Don't **add a settings UI** — discoverability over configurability (ADR-0022).

---

## Session Ledger

> Append-only. Newest entry on top. One block per completed session.

### Template
```
### S<N> — <title> — <YYYY-MM-DD>
- **Shipped:** <what landed>
- **Issues:** closed #… · opened #… · rescoped #…
- **PRs:** #…
- **QA owed:** <none / handoff file / who's running it>
- **Follow-ups / notes:** <anything the next agents need>
```

<!-- entries below -->

### S2 — Pure-logic feature cores — 2026-06-11
- **Shipped:** three feature cores via two parallel worktree agents + TDD. Both PRs merged to `main` (#133, #134); suite green at 950 passed post-merge.
- **Issues:** PR **#133** closes #118 (mouse buttons in `HotkeyClassifier` — `Key.MOUSE_4/5/MIDDLE`, curated allow-list `{…, mouse4, mouse5, middle}`, conditional down/up-paired suppression; pure, unblocks #120/#121). PR **#134** closes #125 + #126 (ADR-0024 — pure `transcribe/replacements.py` + `transcribe/vocabulary.py`; replacements apply to **regular dictation only**, after trigger detection; vocabulary → `hotwords`/`initial_prompt`; both `~/.dictatem/*.md` bootstrapped opt-in).
- **PRs:** #133 (`feat/mouse-trigger-classifier`), #134 (`feat/vocabulary-replacements`). Both reviewed (diff + checks); #134's own `/code-review` caught + fixed a whole-word boundary bug.
- **Tests:** full suite **924 passed, 4 skipped** (baseline 863; +26 from #118, +61 from #125/126). `pyright` 0 new errors, `ruff` clean.
- **QA owed:** #126 vocabulary recognition-lift — exported as [`qa-handoffs/02-vocabulary-recognition-qa.md`](qa-handoffs/02-vocabulary-recognition-qa.md) (real model on Windows; run from the dev clone). **Pending user run.**
- **Follow-ups / notes:** #133 & #134 touch disjoint files → merge in any order, no rebase. Flagged decisions (both non-blocking, accepted): #118 uses a `set` for down/up pairing (fine for real single-down hooks) + unconfigured buttons pass through; #126 joins multi-word vocab terms with spaces (boundary ambiguity acceptable for the focused opt-in list). Next: **S3 — docs & discoverability** (#67/#127/#122/#123).

### S1 — Triage & close-out — 2026-06-11
- **Shipped:** no code; tracker triage. Verified four issues already-shipped (in-code evidence) and closed them. Authored this roadmap doc.
- **Issues:** closed #82 (Key identities — `classifier.py` + `win32_keymap`/`mac_keymap`, `meta`/`win` alias), #83 (`hwnd→target_id` — whole paste rail + `mac_foreground.py`), #34 (all 5 hardware/icon slices DONE + tested), #51 (cross-platform install functionally complete; 3 pure cores tested). Opened: none. Rescoped: none.
- **PRs:** none (tracker-only). Roadmap doc on branch `docs/architectural-roadmap`.
- **QA owed:** none.
- **Follow-ups / notes:** Backlog 32 → 27 open. #34 has **no** residual. #51's residual is fully covered by #90–#95 (do not reopen #51 — work those). #34/#51 audits were evidence-backed (file:line); reopen only if a gap surfaces. Next: **S2 — pure-logic cores (#118/#125/#126)**.
