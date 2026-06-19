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

**Next up: Session 3 — Docs & discoverability.** Since S5 (v0.5.7) a cleanup +
reliability pass landed (2026-06-19): tracker/branch **hygiene** (closed #137 as
superseded by ADR-0023; pruned ~21 merged branches; retired the stale
`feat/macos-track`), the **single-instance guard #92** (PR **#148** — `QLockFile`,
best-effort degrade), and the **#145 clipboard-contention fix** (PR **#149** — the
win32 adapter now translates `pywintypes.error` → `OSError` so the paste
retry/swallow finally engages; relates to #93). Both merged, suite green, no QA
owed. **S4 is now just #81 + #90** (#92 done). Don't re-grill any settled ADR.

This session is small docs + thin discoverability wiring: **#67** (lazy-load/
idle-unload docs — docs-only now), **#127** (default Polish prompt + cleanup
docs), **#122** (auto-open Usage Guide on first run — **sentinel marker, never
rewrite config.toml**), **#123** (tray "Open config…" + Guide "Changing your
hotkey" section). Do **#67 → #127** first (pure docs/bootstrap, no QA), then
**#122 → #123** in sequence (shared tray/first-run path, light Windows QA tail).
Full handoff:
[`docs/agents/handoffs/session-03-docs-discoverability.md`](handoffs/session-03-docs-discoverability.md)
— read it first; it carries the **post-S3 sequencing** for your own handoff.

Skills: `run`/`verify`, `code-review`. Your role: autonomous; the user reviews/
merges the PRs and runs any light Windows QA.

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
| **S4** | CI keystone + install hardening | AFK | M | #81 #90 ~~#92~~ | `code-review`, `diagnose` | — *(do early)* |
| ~~**S5**~~ | ~~Clutter-proof clipboard + last-dictation recovery~~ | AFK | M | ✅ PR #141 (#138) · #142 (#119) · #146 (#139) — merged | `tdd`, `run`/`verify`, `code-review` | done 2026-06-14; Win QA PASS |
| **S6** | Windows mouse hook | AFK | M | #120 | `run`/`verify`, `diagnose`, `code-review` | S2 (#118) |
| **S7** | Cold-start latency **design** | Grill | — | #101 (frames #97 #96 #67) | `grill-with-docs`, `prototype` | — *(parallel-safe)* |
| **S8** | Overlay & focus UX | AFK | M | #96 #97 | `run`/`verify`, `code-review` | S7 |
| **S9** | macOS QA & polish | Manual-QA + AFK | L | #121 #95 #94 #93 | `verify`/`run`, `tdd`, `diagnose` | S2 (#118), S4 |
| **S10** | Signing decision | Grill | — | #91 | `grill-me` | user spend call |
| **—** | Parked backlog | — | — | #72 #80 #129 #130 #131 | `prototype` (#130 spike) | fresh go-ahead |

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

**S5 — Clutter-proof clipboard + last-dictation recovery.** Fully specced by the
**ADR-0023 amendment (2026-06-14)**. #138 clutter-proof clipboard write
(history/cloud exclusion markers on the win32 adapter's `set_text` + `restore`);
#119 Most-recent dictation buffer + tray "Copy last dictation"; #139 built-in
`paste` Trigger Word that re-pastes the buffer (blocked by #119). Keep the buffer
+ detection logic pure and tested; thin win32/tray wiring. **Do not re-grill** —
the no-target auto-dump (#124) and the paste-last hotkey (#128) were considered
and rejected (see ADR-0023; both closed). *QA:* Windows — Win+V stays clean, tray
copy, and "paste" recovery.

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

**Parked — do not build without a fresh go-ahead:** #129
auto-cleanup-every-dictation, #131 tracking issue, #72 PyPI publish, #80 native
Windows-ARM. #130 speech-helper is a **spike** — when picked up, use `prototype`
(ties to the speech-helper direction memory). (#128 paste-last hotkey was closed
as superseded by the ADR-0023 amendment / #139.)

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

- Don't build **parked** issues (#72 #80 #129 #130 #131) without a fresh
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

### Cleanup + reliability — hygiene, single-instance guard (#92), clipboard contention (#145) — 2026-06-19
- **Shipped:** (1) **Hygiene/triage** — closed **#137** as superseded by ADR-0023's clutter-proof markers (the SendInput-for-dictation direction it proposed is the one ADR-0004 rejects; residual contention → #145); pruned ~6 local + ~15 stale remote branches; **retired `feat/macos-track`** (locked worktree + branch — confirmed superseded: its 2026-05-24 work re-landed and evolved on `main` in a different layout, no `macos/` package on main; recovery SHA `2e031a7`). (2) **#92 single-instance guard** (PR **#148**) — its branch was cut **pre-S5**, so it was first **rebased onto `main`** (merging as-was would have reverted all of S5); `QLockFile` at `~/.dictatem/daemon.lock` acquired before hooks/audio/tray; `/code-review` (high) added a **best-effort degrade** so a lock that can't be *established* (unwritable/offline home) logs and starts anyway rather than #92 newly causing a silent "already running" exit; the installer stop-daemon companion was already shipped (#98). (3) **#145 clipboard contention** (PR **#149**) — a `_contention_as_oserror` context manager in `win32_clipboard` translates `pywintypes.error` → `OSError` on **every** clipboard op, so the pure pipeline's `except OSError` retry (open) / swallow (deferred restore) finally engages against the real adapter; a new Windows-only `test_win32_clipboard_contention.py` drives the real pywin32 type; relates to #93.
- **Issues:** closed **#137** (superseded), **#92** (PR #148), **#145** (PR #149). Opened: none. Open count **23 → 20**.
- **PRs:** **#148** (#92) · **#149** (#145) — both **merged to `main`** 2026-06-19 (`1c9a65a`). Branch suites green (1001 / 999, 4 skipped); `pyright` 0 errors, `ruff` clean. `/code-review` run on each (high on #92, medium on #145 — no correctness findings).
- **QA owed:** none — the guard's degrade path and the contention translation are unit-tested against the **real** QLockFile / pywin32 types (which run, not skip, on Windows). Carried over: **#126** vocabulary recognition-lift (S2) still pending a user run — `qa-handoffs/02-vocabulary-recognition-qa.md`.
- **Follow-ups / notes:** **S4 is now just #81 (CI matrix) + #90 (pin CPython)** — #92 done. #92's accepted limitation — QLockFile refuses a fresh start if a crashed daemon's PID is reused by a *live* process — is documented in its docstring; rare (the installer stops the old daemon first), not worth defeating with QLockFile. Next: **S3 — docs & discoverability** (#67/#127/#122/#123); see `docs/agents/handoffs/session-03-docs-discoverability.md` for the **post-S3 sequencing** (S4 recommended next, then S6 mouse hook / S7 cold-start grill).

### S5 — Clutter-proof clipboard + last-dictation recovery — 2026-06-14
- **Shipped:** three feature slices implemented per amended **ADR-0023**, each its own branch/PR with `/code-review` run before opening. **#138** — clutter-proof clipboard write: a pure `paste/clipboard_markers.py` (which exclusion formats + DWORD-0 payload) wired into `win32_clipboard.set_text`/`restore`, applied **best-effort** (a marker failure logs and degrades; the text write already succeeded). **#119** — a new persistent `DaemonCore._most_recent_dictation` field (the last *regular* dictation, normalised + Replacements applied), set in `_do_paste` only when `replace == 0` so a Trigger Fire never overwrites it; a new `ClipboardIO.copy` (a NORMAL copy, no markers) + a tray **"Copy last dictation"** item gated by `TrayState.has_last_dictation`. **#139** — a built-in **`paste`** Trigger Word: pure `match_builtin_action`/`shadowed_builtin_aliases` in `transform.detector`, intercepted in `check_transcription_result` before the Transform alias map (so it runs regardless of `[transform].enabled` and with no Last Paste), reading the Most-recent dictation buffer; empty buffer → existing error flash, never types "paste"; re-paste becomes the new Last Paste; built-in actions dispatched via a `{word: handler}` table (lookup, not equality, so a future word fails loudly). Usage Guide gained a "Recovering a lost dictation" section.
- **Issues:** #138, #119, #139 implemented and **closed** (merged + Windows QA PASS, evidence on each). Opened: **#145** (clipboard retry-gap, see below). Rescoped: none.
- **PRs:** **#141** (#138) · **#142** (#119) · **#146** (#139) — all **merged to `main`** 2026-06-14. (#139 originally opened as the stacked PR #143, which GitHub auto-closed when `--delete-branch` on #142 removed its base branch; reopened as #146 → `main`, same commits.) Merged suite **995 passed, 4 skipped**; `pyright` 0 errors, `ruff` clean.
- **QA owed:** none — **Windows live-QA PASSed on real hardware 2026-06-14** (integration build of all three): Win+V showed no new entry after dictation (#138), tray "Copy last dictation" disabled→enabled + copied + survived a paste (#119), and saying "paste" recovered a dictation that landed nowhere (#139). Log evidence (`Copied 26-char Most-recent dictation…`, `` `paste` action: re-pasting… ``) on the closed issues. The exported checklist [`qa-handoffs/03-s5-clipboard-recovery-qa.md`](qa-handoffs/03-s5-clipboard-recovery-qa.md) remains for a fuller pass (cloud-clipboard sync, shadowed-alias warning) if ever wanted.
- **Follow-ups / notes:** Flagged decisions (accepted, reversible): the tray "Copy last dictation" is a *normal* copy (appears in Win+V) per ADR-0023 — flip to a clutter-proof write if surprising. **Pre-existing observation surfaced during #138 review (not a bug introduced here, left untouched per "ride the paste flow unchanged"):** `pipeline._open_with_retry` and the deferred `_restore` catch `OSError`, but `win32clipboard.OpenClipboard` raises `pywintypes.error`, which is **not** an `OSError` subclass — so real clipboard contention on the production open/restore is not actually retried/swallowed. Filed as **#145** (relates to #93 paste-not-landing); suggested fix is to translate `pywintypes.error` → `OSError` in the win32 adapter so the pure pipeline's retry/swallow works unchanged. **Separate thread still owed:** single-instance guard **#92** on `feat/single-instance-guard-92` (commit + `/code-review` + PR + installer "stop old daemon" upgrade) — see `docs/agents/handoffs/single-instance-guard-92.md`; not part of this session.

### Clipboard clutter + last-dictation recovery (design grill) — 2026-06-14
- **Shipped:** no code — design decisions. Amended **ADR-0023**: corrected the false "regular dictation never touches the clipboard" premise (it pastes via clipboard + Ctrl+V, ADR-0004); recorded the clutter-proof history/cloud exclusion markers, the Most-recent dictation buffer, and the built-in `paste` recovery; recorded #124 auto-dump and #128 hotkey as rejected options. Updated **CONTEXT.md**: added *Most-recent dictation* and *Clutter-proof clipboard write*, broadened *Trigger Word* to cover built-in actions, removed the now-wrong *Clipboard Fallback* term.
- **Issues:** opened **#138** (clutter-proof clipboard write) + **#139** (`paste` built-in action Trigger Word, blocked by #119) · rescoped **#119** (Most-recent dictation buffer + tray "Copy last dictation") · closed **#124** + **#128** (superseded / not planned).
- **PRs:** none (design session; docs committed to branch `docs/clipboard-clutter-backup-paste`).
- **QA owed:** none yet — S5 implementation (#138 / #119 / #139) carries the Windows manual-QA (Win+V stays clean, tray copy, "paste" recovery).
- **Follow-ups / notes:** HARD CONSTRAINT preserved — regular dictation stays clipboard + Ctrl+V (typed `SendInput` was rejected for it; ADR-0004 untouched). Built-in `paste` is decoupled from `[transform].enabled`. Flagged (easily reversible): the tray "Copy last dictation" is a *normal* copy (appears in Win+V) — flip to a clutter-proof write if surprising. **Separate thread still owed:** single-instance guard **#92** on `feat/single-instance-guard-92` (commit + `/code-review` + PR + the installer "stop old daemon" upgrade) — see `docs/agents/handoffs/single-instance-guard-92.md`; not part of this session.

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
