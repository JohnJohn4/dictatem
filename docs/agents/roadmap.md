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

**Next up: land S9, then Session 10 — macOS QA & polish (#121 #95 #94 #93) — or S11.**

**S9 (Overlay & focus UX) shipped as three open PRs** (AFK, 2026-06-22) — implementing
**ADR-0026** plus **#171**: **PR #173** (#96 retire the Status Dot → pill **colour** carries
phase + #163 the pill **never steals activation**), **PR #174** (#97 focus-drift
**detect-and-hold**, never refocus), **PR #175** (#171 **Win+Alt** chord-release
neutralizing Ctrl tap so a lone Alt-up can't activate the menu bar). All three are
**independent**, cut from `main`, and an octopus merge of all three is **conflict-free**
(combined suite **1112 green**, `ruff`/`pyright` clean). S1–S8 done.

**The immediately-actionable work is to LAND S9, not start fresh:**
1. **Merge #173 / #174 / #175** (any order — disjoint `daemon.py` methods) once reviewed.
2. **Run the S9 Windows QA** — [`qa-handoffs/07-s9-overlay-focus-qa.md`](qa-handoffs/07-s9-overlay-focus-qa.md):
   overlay phase-by-colour + no dot (#96), pill-never-steals-focus (#163), focus-drift hold +
   `paste` recovery (#97), Win+Alt menu-bar non-activation (#171). On PASS, close #96/#97/#163/#171
   and tick the S9 ledger; on FAIL, comment evidence and keep open. You have a Windows box — run it,
   or hand the file to a QA agent.

**Then the next NEW session** is **S10 — macOS QA & polish** (#121 macOS mouse hook, #95
first-run onboarding, #94 QA runbook, #93 paste-not-landing) — but it **needs a real Mac**
(export a QA handoff if none) — **or S11 — signing decision grill** (#91), which **needs the
user's spend call** ($99/yr Apple Developer). Both are gated on external things, so confirm
availability with the user before picking.

**Settled — do not reopen (ADR-0026 is the spec; S9 implemented it):** phase-by-colour
(no dot, no Tap/Hold cue; the warm-LLM "computing" signal is now a **colour**, refining
ADR-0016); detect-and-hold **never refocuses** (anchor `target_id` at record-start, hold in
the Most-recent buffer + a **silent** flash on drift — Dictatem has no sound surface); the
pill **never activates**. **#171:** the neutralizing keystroke is a **generic Ctrl tap**
(maps to `Key.OTHER`, inert), emitted when a key-up **breaks** a held combo while a
side-effect modifier is still down — covers `win+alt` and ctrl-combos; a *single*
side-effect-modifier combo (e.g. `["alt"]`) is the documented uncovered edge.

Skills: `verify`/`run`, `code-review`, `tdd`, `diagnose`. Your role for landing S9:
**merge + manual-QA**; for S10/S11: **manual-QA on a Mac / decisions-needed** (confirm with
the user first).
**QA owed:** **S9** (above, `qa-handoffs/07-…`, PENDING) + carried-over **#126** vocabulary
recognition-lift — `qa-handoffs/02-vocabulary-recognition-qa.md` (real-model run on Windows).

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
| **S4** | CI keystone + install hardening | AFK | M | #81 #90 ~~#92~~ | `code-review`, `diagnose` | done 2026-06-22 (#156/#157 merged) |
| ~~**S5**~~ | ~~Clutter-proof clipboard + last-dictation recovery~~ | AFK | M | ✅ PR #141 (#138) · #142 (#119) · #146 (#139) — merged | `tdd`, `run`/`verify`, `code-review` | done 2026-06-14; Win QA PASS |
| **S6** | Windows mouse hook | AFK | M | #120 | `run`/`verify`, `diagnose`, `code-review` | done 2026-06-22 (PR #159, QA PASS) |
| ~~**S7**~~ | ~~Cold-start latency **design**~~ | Grill | — | ✅ #101 → ADR-0025/0026; spun #161 #162 #163 #164 #165 (#96/#97 re-scoped) | `grill-with-docs` | done 2026-06-22 |
| **S8** | Cold-start latency **implementation** | AFK | M | #161 #162 #164 | `tdd`, `run`/`verify`, `code-review` | done 2026-06-22 (PRs #167/#168/#169 merged; Win QA PASS) |
| **S9** | Overlay & focus UX | AFK | M | #96 #97 #163 #171 | `run`/`verify`, `code-review` | impl 2026-06-22 (PRs #173/#174/#175 open; QA owed) |
| **S10** | macOS QA & polish | Manual-QA + AFK | L | #121 #95 #94 #93 | `verify`/`run`, `tdd`, `diagnose` | S2 (#118), S4 |
| **S11** | Signing decision | Grill | — | #91 | `grill-me` | user spend call |
| **—** | Parked backlog | — | — | #72 #80 #129 #130 #131 | `prototype` (#130 spike) | fresh go-ahead |

**Critical path:** S1 → S2 (#118) → S6 / S10 (mouse hooks). **Slot S4 early** — it
is the CI verification surface that turns most macOS work into machine-checkable
work. **S7 (cold-start design) is done** — it unblocks **S8** (latency) and **S9**
(overlay & focus), which are independent of each other (run in either order or
parallel).

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

**S7 — Cold-start latency design (grill). ✅ Done 2026-06-22.** #101 → **ADR-0025**
(load-on-arm + first-run model fetch) and **ADR-0026** (focus-drift detect-and-hold
+ overlay phase-by-colour). Spun #161 #162 #163 #164 (`ready-for-agent`) + #165
(parked cloud/BYO, `needs-triage`); re-scoped #96/#97 to ADR-0026; CONTEXT.md
updated. The **new docs issue #164** supersedes #67's framing (#67 stays closed).

**S8 — Cold-start latency implementation.** #161 load-on-arm (start the Whisper load
at record-start, overlapping speech; reuse `preload()`), #162 first-run model fetch
(download the tier model to disk on first run, best-effort, lazy-fallback — the
first dictation then works offline) + its honest signalling, #164 docs refresh
(README "Model loading & VRAM" + Usage Guide). Per **ADR-0025**. Keep lifecycle /
gating pure + tested; daemon/install/native wiring thin. *QA:* Windows **offline
first-dictation** (install online → disconnect → first dictation works) +
load-overlaps-speech eyeball.

**S9 — Overlay & focus UX.** #96 remove the dot → pill-colour phase, purely
informational (drop the Tap/Hold cue); #97 polite **detect-and-hold** (anchor
`target_id` at record-start for comparison only; changed target → hold in the
Most-recent buffer + quiet flash, no sound, never refocus); #163 make the pill never
steal activation. Per **ADR-0026**. **Plus #171** (folded in from S8 QA, not in
ADR-0026): a lone Alt-up on a Win+Alt chord release activates the app menu bar /
deactivates the caret — fix via a neutralizing keystroke on modifier release. *QA:*
Windows overlay + focus-drift + the #171 Win+Alt check.

**S10 — macOS QA & polish.** #121 macOS mouse hook (after #118), #95 first-run
onboarding (pure permission mapper is testable; dialog copy + re-prompt-on-use),
#94 finish the QA runbook, #93 diagnose intermittent paste-not-landing. CI (S4)
makes the pure parts machine-checkable; the rest is **real-Mac Manual-QA** — if no
Mac is available, export a QA handoff.

**S11 — Signing decision (grill).** #91 clean TCC identity — a **decision**, not a
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

### S9 — Overlay & focus UX — 2026-06-22
- **Shipped:** three PRs, one per slice, each `/code-review`'d (high, 8 angles) before
  opening. **#96 + #163 overlay** (PR **#173**): retired the **Status Dot** — recording
  **phase is the pill colour** now (`OverlayState.PillColor` + `current_color()`, a pure
  phase→colour map; the Qt pill paints the waveform in the phase hue: blue recording /
  amber transcribing / violet computing / red error-flash, no dot, Tap/Hold mode cue
  dropped). The warm-LLM **"LLM Model Computing" caption became the computing colour**
  (`show_computing()`/`OverlayPhase.COMPUTING`) per ADR-0026 — **refines ADR-0016**
  (noted in it); model loading/downloading stay text captions. #163: the pill gained
  `WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating` so *showing* it can't deactivate
  the user's window/caret. **#97 detect-and-hold** (PR **#174**): anchor the foreground
  `target_id` at record-start, compare at paste via a pure `paste/focus_drift.focus_drifted()`;
  a regular dictation whose foreground changed is **held** in the Most-recent buffer with the
  existing (silent) error flash, **no refocus** — recovered by `paste`/tray. Trigger Fire
  (replace>0) is exempt (its own rail already gates it). **#171 Win+Alt mask** (PR **#175**):
  the pure classifier decides a neutralizing keystroke (`pending_mask`) when a key-up **breaks**
  a held combo while a side-effect modifier (Alt/Meta) is still down; the Windows keyboard hook
  injects a **generic Ctrl tap** (`Win32KeystrokeSender.send_modifier_release_mask`). The
  keyboard handler return type became `bool` across the `KeyboardHook` protocol + both platform
  hooks (macOS ignores it).
- **Decisions (settled in S7 — ADR-0026 is the spec; not reopened):** phase-by-colour +
  detect-and-hold-never-refocus + pill-never-activates. New this session (accepted, from
  `/code-review`): (a) **#96** the warm-computing signal is a colour, not the old caption
  (ADR-0026 §Decision; ADR-0016 refined). (b) **#97** thread one captured `target_id` through
  `pipeline.paste()` so the drift check, the focus restore, and the Last Paste are one source
  of truth (was a paste-time double-`capture()` race). (c) **#171** the injected mask is a
  **generic `VK_CONTROL` (0x11)** → `vk_to_key` → `Key.OTHER` (inert, like the paste rail's
  Ctrl+V), so **no guard against Ctrl-containing combos is needed**; gating on the combo
  *break* (not "any side-effect key still held") both extended the fix to `ctrl+win`/`ctrl+alt`
  and removed a spurious mid-hold Ctrl tap on doubled-modifier release — this dropped
  `_combo_was_armed`/`_ctrl_is_trigger` and simplified the classifier. **No error sound**
  for the drift hold is honest: Dictatem has **no sound surface at all** (grep-verified).
- **Issues:** #96, #97, #163, #171 — **implemented, not yet closed** (close on PR merge + QA).
  Opened: none.
- **PRs:** **#173** (#96+#163 → `main`) · **#174** (#97 → `main`) · **#175** (#171 → `main`).
  All **open**, independent (cut from `main`, not stacked). All three touch `daemon.py` in
  **disjoint methods**; verified locally with an octopus merge of all three into `main` — **no
  conflicts**, combined suite **1112 passed, 4 skipped**, `ruff` clean, `pyright` 0 errors.
  Merge in any order. Each PR's `/code-review` applied fixes (see Decisions); PR #173 also
  hoisted the pill's per-frame QColor map to a module constant + covered `show_computing` in
  `test_interfaces`.
- **QA owed:** **S9 Windows manual-QA — PENDING.** Exported:
  [`qa-handoffs/07-s9-overlay-focus-qa.md`](qa-handoffs/07-s9-overlay-focus-qa.md) — overlay
  phase-by-colour + no dot (#96), pill-never-steals-focus (#163), focus-drift hold + recovery
  (#97), Win+Alt menu-bar non-activation (#171). Run on Windows after the PRs merge (or on a
  scratch branch merging all three). Carried over: **#126** vocabulary recognition-lift —
  `qa-handoffs/02-vocabulary-recognition-qa.md`.
- **Follow-ups / notes:** **Known limitation (#171):** a *single* side-effect-modifier combo
  (e.g. `["alt"]` alone) can't be pre-neutralized this way (no second key to leave held) —
  default `win+alt` and all multi-key combos are covered; documented in the issue + a test.
  The native injection (`send_modifier_release_mask`) and the no-activate window flags are the
  only un-unit-tested bits (manual-QA, per the architecture seam). The S6 "harden both native
  hooks together" follow-up still stands. Next: **S10 — macOS QA & polish** (needs a Mac) or
  **S11 — signing grill** (needs the user's spend call); both are gated on external things, so
  the immediately-actionable work is **merging the three PRs + running the S9 QA handoff**.

### S8 — Cold-start latency implementation — 2026-06-22
- **Shipped:** three PRs implementing **ADR-0025**. **#161 load-on-arm** (PR **#167**):
  `_do_record_start` kicks the existing background `TranscribeLifecycle.preload()`, so
  the Whisper load starts at record-start and overlaps speech (strictly dominates
  lazy-at-transcribe — the load can only ever start *earlier*). Esc leaves the
  in-flight load running (a faster-whisper load can't be cancelled — ADR-0016);
  idle-unload stays the sole reaper. `_background_load` now swallows+logs a load
  failure instead of leaking an unhandled thread exception (the transcribe path still
  surfaces a *persistent* failure and retries a *transient* one within the dictation).
  **#162 first-run fetch** (PR **#168**, stacked on #161): new
  `TranscriberBackend.download_to_disk()` (faster-whisper `download_model` → HF
  snapshot into the same cache the load reads, **no VRAM**) + `prefetch_to_disk()` on
  the lifecycle (`is_downloading`/`last_download_succeeded`, background, best-effort,
  **never raises into startup**); the daemon fetches the resolved tier's weights to
  disk on first run (captured as `not config_path.exists()` **before** `load_config`),
  so the first *dictation* works offline. Signalled via a tray notification, a distinct
  **"Downloading model…"** pill caption, and a **success-only** "ready" notification.
  **#164 docs** (PR **#169**): README "Model loading & VRAM" + Usage Guide rewritten;
  fixed two stale lazy-load-at-transcribe lines; **supersedes #67's framing** (#67 stays
  closed).
- **Decisions (settled in S7 — ADRs are the spec; not reopened):** load-on-arm (not
  preload-on-launch); first-run fetch lives in the **daemon** (only it knows the exact
  tier — ADR-0011 thin install); best-effort + silent lazy-fallback if offline;
  download-to-disk-only. New this session (accepted, low-risk, from `/code-review`):
  (a) `_background_load` now catches+logs (was an unhandled thread exception) — an
  improvement load-on-arm motivated; (b) the first-run start notification makes **no
  per-run offline promise** (honest if offline at first run); (c) `prefetch_to_disk`
  returns whether it kicked, so the "ready" flag can't dangle. A "double-download"
  candidate was **refuted** (HF file locks coordinate the concurrent load-on-arm load —
  the intended overlap).
- **Issues:** #161, #162, #164 — **implemented, not yet closed** (close on PR merge +
  QA). Opened: none. Real download-% via the stubbed `on_download_progress` seam is a
  **noted follow-up** inside #162 (out of scope).
- **PRs:** **#167** (#161 → `main`) · **#168** (#162 → stacked on #167) · **#169** (#164
  → `main`, docs-only). All **open**. **Merge order: #167 → #168 → #169** — #168 is
  stacked, so GitHub retargets it to `main` once #167 merges; if `--delete-branch` on
  #167 auto-closes #168 (the S5 #143 hazard), reopen it — the commits are intact.
  Verified locally: all three merge into `main` with **no conflicts**; combined suite
  **1073 passed, 4 skipped**, `ruff` clean, `pyright` 0 errors. Each PR ran
  `/code-review` (high): #161 applied test-determinism cleanups (a fake load-gate +
  shared `tests/support.wait_until`, replacing fixed sleeps); #162 applied the honesty +
  flag-robustness fixes; #169 fixed two stale README lines a finder caught.
- **QA owed:** **S8 Windows QA — PASS ✅ 2026-06-22** (`qa-handoffs/06-s8-cold-start-qa.md`,
  dev clone on `main` @ `65637ec`, Win 11 + NVIDIA GPU, `large-v3-turbo`): **A** offline-
  after-setup, **B** first-run download + signalling (throwaway `HF_HOME`), **C** load-
  overlaps-speech, **D** offline-first-run lazy fallback — **all pass**; **#161/#162 closed**
  with log evidence. Test **D** simulated an unreachable Hub via `HF_HUB_OFFLINE=1` (a literal
  disconnect would sever the QA agent's own API link; identical model-fetch path). Carried
  over: **#126** vocabulary recognition-lift — `qa-handoffs/02-vocabulary-recognition-qa.md`.
- **Follow-ups / notes:** real download-% via `on_download_progress` (stubbed today) is
  the optional follow-up in #162. The "Downloading model…" pill caption is latched once
  at transcribe-time (cosmetic: it can persist through the brief VRAM-load phase after
  the download finishes) — not worth tick-refresh complexity. The S8 split (#161 latency
  + #162 fetch + #164 docs) shipped as three PRs rather than the roadmap's hinted
  parallel worktrees, because #161/#162 share `daemon.py`/`fake_transcriber.py` hunks —
  stacking #162 on #161 was the lower-conflict path. **QA surfaced two follow-ups:**
  (1) **#171** — a Win+Alt hotkey bug where a lone Alt-up on chord release activates the app
  menu bar and deactivates the caret (S9-focus-adjacent but a distinct root cause from
  #97/#163; `needs-triage`); (2) minor — the offline first-run fetch WARNING logs a full
  chained `exc_info` traceback, noisy for an expected-offline condition (could log without
  the stack trace). Next: **S9 — Overlay & focus UX (#96/#97/#163)** per ADR-0026 — consider
  folding **#171** into that session.

### S7 — Cold-start latency design (grill) — 2026-06-22
- **Shipped:** no code — design decisions. **ADR-0025** (cold-start: the model loads
  on arm, and is fetched on first run) and **ADR-0026** (focus drift holds the
  dictation; the overlay shows phase by colour). **CONTEXT.md** updated: *Overlay
  Pill* (phase-by-colour, informational, "Downloading model…" caption), *Status Dot*
  (**retired** → pill colour), *Most-recent dictation* (now also holds a regular
  dictation when focus drifted between record-start and paste).
- **Decisions (settled — do not reopen; the ADRs are the spec):** (1) **Load-on-arm**
  — start the Whisper load at record-start, overlapping speech (reuse `preload()`);
  Esc lets it finish (a faster-whisper load can't be cancelled — ADR-0016);
  idle-unload (30 min) stays the sole reaper; **not** preload-on-launch by default.
  (2) **First-run fetch** — download the tier model **to disk only** on the daemon's
  first run (which the installer triggers), best-effort, lazy-fallback if offline →
  the first *dictation* works offline; lives in the daemon (only it knows the exact
  tier); signalled via tray notification + Usage Guide + a "Downloading model…" pill
  caption; real % is a follow-up on the existing `on_download_progress` seam.
  (3) **#97 detect-and-hold** — anchor `target_id` at record-start for comparison
  only; changed target → hold in the Most-recent buffer + quiet flash, **no sound,
  never refocus** (sidesteps the Mac `activateWithOptions_` app-granular/soft-
  deprecated fragility; *less* pushy than today's per-paste `restore()`). (4) **#96
  overlay** — remove the dot, pill colour carries phase, purely informational (a
  clickable control would break click-through + reintroduce focus-stealing — the
  ADR-0026 interlock); drop the Tap/Hold cue. **Cloud/BYO (#165) rejected as a
  cold-start fix**, parked as its own future grill.
- **Issues:** opened **#161** (load-on-arm) **#162** (first-run fetch) **#163** (pill
  never steals activation) **#164** (docs refresh — supersedes #67's framing; #67
  stays closed) — all `ready-for-agent`; **#165** (parked cloud/BYO, `needs-triage`).
  Re-scoped + relabelled `ready-for-agent`: **#96** (overlay phase-by-colour) **#97**
  (detect-and-hold). #101 (design parent) left **open** — close on the docs PR merge.
- **PRs:** none yet (design docs on branch `docs/s7-cold-start-design`).
- **QA owed:** none for S7 itself. **S8** carries a Windows **offline first-dictation**
  check; **S9** carries overlay + focus-drift QA. Carried over: **#126** vocabulary
  recognition-lift — `qa-handoffs/02-vocabulary-recognition-qa.md`.
- **Follow-ups / notes:** the latency implementation became its own session — the old
  "Overlay & focus UX" S8 split into **S8 (latency)** + **S9 (overlay/focus)**; macOS
  → **S10**, signing → **S11**. Real download-% via `on_download_progress` (stubbed
  today) is an optional follow-up inside #162. #163 (pill never steals activation) is
  a likely root-cause for the "caret deactivates while talking" drift — fix at source;
  it **complements**, not replaces, #97's detect-and-hold.

### S6 — Windows mouse hook — 2026-06-22
- **Shipped:** the **#120 `WH_MOUSE_LL` adapter** (one PR, **#159**), feeding the
  S2 mouse classifier (#118, ADR-0020) so a mouse side button / wheel click arms
  dictation. **Pure keymap** `hotkey/win32_mouse_keymap.py` (`WM_*` + xbutton →
  `(Key, KeyAction)`: X1=mouse4, X2=mouse5, middle=wheel; left/right/move/wheel →
  `None`). **Live hook** `hotkey/wh_mouse_ll.py` mirrors `wh_keyboard_ll.py` but
  applies the classifier's `HookDecision` **synchronously** (returns non-zero from
  the hook proc to swallow a trigger button — a low-level hook can only suppress
  from its proc on the hook thread). New `install_mouse_hook` on `_PlatformAdapters`,
  wired in `_run_daemon`/`_start_windows_daemon` (macOS = `None`, that's #121).
  Also: `format_hotkey` now renders mouse buttons (a standalone `["mouse4"]` shows
  "Mouse4 to dictate", not a blank chord) + the Usage Guide notes the click-only-
  mice graceful degrade (ADR-0020 consequence).
- **Design (settled — do not reopen):** a mouse button can share one combo with
  keyboard modifiers (`ctrl+mouse4`), so **both hooks feed ONE classifier**, and
  the mouse decision needs current keyboard state. So `_HotkeyBridge` now
  **advances the classifier eagerly under a lock** (on whichever hook thread
  delivered the event) and **defers the state-machine/Qt dispatch to the GUI
  tick** — keyboard dispatch timing is unchanged (the old bridge tests, which
  encode that behaviour, all still pass). The two scary-looking concurrency
  candidates from `/code-review` (spurious HOLD_START at tick; unpaired KEY_DOWN
  when a combo breaks) were traced and **refuted** (`classifier.tick` gates on live
  `combo_held`/`_combo_pressed_at`; the "combo breaks with event=None" reset is the
  pre-existing path and unreachable when a held combo breaks).
- **Issues:** **#120 — implemented + physical-QA PASS; CLOSED on PR #159 merge
  (2026-06-22).** Opened: none. *(S4's #156/#157 merged; #81/#90 closed.)*
- **PRs:** **#159** (#120) — **merged to `main`** 2026-06-22 (all 6 CI legs green,
  win+mac × 3.11–3.13). Full suite **1054 passed, 4 skipped** locally (+29);
  `ruff` clean, `pyright` 0 errors. `/code-review` (high, 5 finder angles) run —
  fixed two cleanups (hoisted the `HotkeyEvent` import out from under the bridge
  lock; deduped `_MOUSE_LABELS` into `_WORD_NAMES`); the native-plumbing
  duplication + latent items were documented as an out-of-scope follow-up.
- **QA owed:** none — **#120 physical click-QA PASSED on real hardware 2026-06-22**
  (Windows 11, Logitech MX Master 3S; run from the dev clone, evidence on #120):
  keyboard regression (tap+hold, no change); default-inert mouse (unconfigured
  buttons do their normal OS action, hook passes through); standalone `["mouse4"]`
  (tray "Mouse4 to dictate", tap+hold arm, back-nav suppressed); combined
  `["ctrl","mouse4"]` (bare press still navigates back, Ctrl+ arms **and**
  suppresses); `["middle"]` (wheel-click arms + suppressed). mouse5 not physically
  clicked — same `WM_XBUTTON` path as mouse4. A **synthetic `SendInput` smoke test
  also PASSED** earlier (the live hook decoded injected middle/X1/X2 to the exact
  `(Key, action)` — confirms the `MSLLHOOKSTRUCT` HIWORD decode against real OS
  event delivery). Checklist: [`qa-handoffs/05-windows-mouse-hook-qa.md`](qa-handoffs/05-windows-mouse-hook-qa.md).
  Carried over: **#126** vocabulary recognition-lift (S2) —
  `qa-handoffs/02-vocabulary-recognition-qa.md`.
- **Follow-ups / notes:** **harden both native hooks together** (the `wh_mouse_ll`
  /`wh_keyboard_ll` shared ctypes plumbing: `SetWindowsHookExW` restype, `uninstall`
  posting `WM_QUIT`, the first-event handle race) — benign today, worth a dedicated
  pass with re-QA on both. The mouse hook installs inside the keyboard-hook-present
  branch (it needs the shared bridge/classifier — correct per ADR-0020's "one
  combo"); revisit only if a mouse-only platform ever appears. Next: **S7 — cold-
  start latency design grill (#101)** (code-free, parallel-safe, unblocks S8); see
  the per-session detail. macOS mouse hook (#121) reuses this session's pure
  classifier path when the macOS QA day comes (S9).

### S4 — CI keystone + install hardening — 2026-06-22
- **Shipped:** two issues, one PR each (independent branches off `main`, file-disjoint). **Key discovery:** the CI matrix #81 describes (`windows-latest` + `macos-latest` × py3.11–3.13; `uv sync --extra runtime` + ruff + pyright + pytest, PR-gated) **already existed** — it landed with the arm64-windows work (PR **#79**, `19dc2b8`) and has been green on every PR since; the roadmap/handoff overstated it as "no CI today," so S4 was much smaller than framed. **#81** (PR **#156**) adds the one missing acceptance criterion: a *positive* import-safety test (`TestNativeAdaptersImport`) that, per platform, glob-discovers every native adapter (`win32_*`/`wh_*` on Windows, `mac_*` + `macapp.activation` on macOS) and imports it, so a broken pywin32/PyObjC binding fails in CI not at runtime — the existing inverse purity guard is kept. **#90** (PR **#157**) pins `--managed-python --python 3.12` on Windows **x64** (x64 previously let uv discover any system Python ≥3.11 — the reproducibility hazard) and **aligns the pin to 3.12 across x64 + ARM + macOS** (ARM was an arbitrary 3.11 with no wheel/arch rationale — **ADR-0017 amendment**); new `tests/test_install_python_pin.py` parses both installers and asserts every pin appears in the CI matrix so they can't drift.
- **Decision (settled — do not reopen):** **3.12 everywhere.** The user chose it after confirming 3.11 was arbitrary on ARM (ADR-0017 carried no version rationale; #78 just copied an example). ARM 3.11→3.12 is CI-tested + reasoned-safe but **not re-verified on real ARM hardware** (no device) — re-run the Snapdragon smoke test when one is available.
- **Issues:** #81, #90 — **implemented, not yet closed** (close on PR merge). Opened: none.
- **PRs:** **#156** (#81) · **#157** (#90) — **both open, all 6 CI legs green**, awaiting review/merge; merge either order. Each: full suite **1025 passed, 4 skipped** locally, ruff clean, pyright 0 errors; `/code-review` (high) run — #157's review hardened the pin parser (an example *comment* could masquerade as a pin and defeat the vacuous-pass guard) and documented the x64 managed-fetch consequence.
- **QA owed:** **none of S4's own** beyond CI green — plus a **real Windows x64 install QA PASS** (2026-06-22): `uv tool install --managed-python --python 3.12 dictatem[runtime]@v0.5.7` into a throwaway tool dir (real install untouched) resolved 42 pkgs, env = Python 3.12.13, dictatem + win32 adapter imported clean. Carried over: **#126** vocabulary recognition-lift (S2) — `qa-handoffs/02-vocabulary-recognition-qa.md`. (**#122/#123 already passed** S3 QA, 2026-06-20.)
- **Follow-ups / notes:** the **x64 managed-fetch is now mandatory** (mirrors macOS; no opt-out to a discovered interpreter) — accepted reproducibility trade-off documented in ADR-0017; an opt-out env var is a possible later follow-up if an air-gapped/strict-proxy x64 box surfaces. Next: **S6 — Windows mouse hook (#120)** recommended (Windows-testable here, user-wanted); **S7 cold-start grill (#101)** is code-free + parallel-safe. See `docs/agents/handoffs/session-06-windows-mouse-hook.md`.

### S3 — Docs & discoverability — 2026-06-20
- **Shipped:** four issues across three independent PRs. **#67** (PR **#151**, docs-only) — a README "Model loading & VRAM" section: lazy-load (model loads on first dictation; the pill shows it's *loading*, not stuck), idle-unload (frees ~3 GB VRAM after `idle_unload_minutes`; the LLM is kept warm for the same window), how to trade VRAM for an instant first response (`[startup] preload_model`, `[model] idle_unload_minutes`, tray Preload/Unload), and the managed-machine AV/EDR first-launch note. The "Loading model…" pill itself already shipped (#74), so this was the item-2/3 docs residual only. **#127** (PR **#152**) — a bundled default `polish.md` Prompt File (aliases `polish`, `cleanup`): a faithful copy-edit (remove filler/false starts, **preserve meaning + voice**, explicitly NOT a summary), bootstrapped like `summarize.md`; the Usage Guide + README document the cleanup-over-last-dictation flow. Reuses the Prompt File mechanism — no new code (ADR-0003/0024). **#122 + #123** (PR **#153**, combined — shared tray/first-run path): **#122** auto-opens the Usage Guide once on first run via a sentinel marker `~/.dictatem/.usage_guide_seen` (pure gate in new `onboarding.py`; written only *on-show*; deferred while a macOS permission flow is pending; never rewrites `config.toml` — ADR-0021/0009/0022); **#123** adds a tray "Open config file…" item (OS-default open, no settings UI) + a "Changing your hotkey" Usage Guide section reflecting the live combo and the curated `[hotkey].modifiers` vocabulary incl. mouse buttons (ADR-0022/0019). New `config.default_config_path()` shared by daemon + tray.
- **Issues:** **all four closed** — #67, #127 on their PRs' merge; **#122**, **#123** closed COMPLETED after the **Windows QA PASS** (2026-06-20), with evidence on each. Opened: none.
- **PRs:** **#151** (#67) · **#152** (#127) · **#153** (#122+#123) — **all merged to `main`** 2026-06-20 (plus the docs PR **#154** and the follow-up **#155** correcting this ledger). Cut **independently from `main`** (no stacking — avoids the #143 base-branch-deletion auto-close hazard); file-disjoint except `usage_guide.py` / `test_usage_guide.py`, where #127 and #123 touched different hunks and merged clean (the established S5 multi-PR pattern). Each branch: full suite green (1007 passed after #127, 1021 after #122/#123; 4 skipped), `ruff` clean, `pyright` 0 errors; `/code-review` run (no findings — #153 got two independent adversarial reviewers over the daemon control-flow + the pure modules).
- **QA owed:** **none** — #122/#123 Windows manual-QA **PASSED 2026-06-20** on real hardware: clean profile (marker absent) → the Usage Guide auto-opened once and `~/.dictatem/.usage_guide_seen` was written (log: `First run — auto-opened the Usage Guide`); a relaunch with the marker present did **not** re-open (auto-open log-line count stayed at 1 across the restart); tray "Open config file…" opened `config.toml`; the Guide's "Changing your hotkey" section showed the live Win+Alt combo + the curated vocabulary. Checklist: [`qa-handoffs/04-docs-discoverability-qa.md`](qa-handoffs/04-docs-discoverability-qa.md). Carried over: **#126** vocabulary recognition-lift (S2) still pending a user run — `qa-handoffs/02-vocabulary-recognition-qa.md`.
- **Follow-ups / notes:** #67's framing stays deliberately factual (no over-promising) until the **#101 cold-start design (S7)** lands. The bundled `polish` trigger only fires once the Transform/Ollama is set up (Transform is on by default, but Ollama stays user-managed — ADR-0008). Next: **S4 — CI keystone + install hardening (#81 + #90)** — `.github/workflows/ci.yml` already exists on `main`; the S4 agent must inspect it before adding the matrix. See `docs/agents/handoffs/session-04-ci-install-hardening.md`.

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
