# Handoff — Session 4: CI keystone + install hardening

**You are the next agent in the roadmap.** This doc onboards you to one session.
It does not replace the issues or ADRs — it tells you where you are, what to do,
and **how to hand off when you're done** (post-S4 sequencing at the bottom).

## How the roadmap works (read this first)

1. **`docs/agents/roadmap.md` is ground truth.** Read it now, top to bottom. Its
   **▶ Current Session Prompt** should already point you here.
2. The roadmap defines the **working principles**, the **session list (S1–S10)**,
   the **Definition of Done**, and the **handoff protocol**. Operate inside that
   frame — don't re-plan the backlog.
3. The backlog lives in GitHub Issues (`JohnJohn4/dictatem`, via `gh`). Read each
   issue before coding (#81, #90).
4. When you finish, run the **handoff protocol**: append a ledger entry, rewrite
   the Current Session Prompt, and flag/export any manual QA.

## Your role this session

Autonomous AFK implementer. This is infrastructure: a CI workflow + a pinned
toolchain. The user reviews and merges your PRs. **No manual QA of your own**
beyond CI going green — but two QA tails are **carried over** from earlier
sessions (see below); surface their results if they land.

**Skills:** `code-review` before each PR, `diagnose` if CI behaves oddly. Branch
per issue; PRs to `main`.

## Where the project is (what landed before you)

- **S3 — docs & discoverability** shipped as **three PRs that may still be open**
  when you start: **#151** (#67 model-loading docs), **#152** (#127 default
  `polish` prompt), **#153** (#122 first-run Usage Guide auto-open + #123 config
  discoverability). If they're not merged yet, that's fine — they're file-disjoint
  from S4. **#122/#123 owe a Windows manual-QA** — see
  [`../qa-handoffs/04-docs-discoverability-qa.md`](../qa-handoffs/04-docs-discoverability-qa.md);
  don't close them on unverified work.
- Earlier: S5 clutter-proof clipboard + recovery (v0.5.7), the single-instance
  guard (#92), and the #145 clipboard-contention fix all merged. **S4 is now just
  #81 + #90** (#92 is done).

Nothing above is yours to redo. If you spot a contradiction with an ADR, surface
it (per `docs/agents/domain.md`) rather than silently overriding.

## Session 4 scope (2 issues)

Read each issue (`gh issue view <n>`) before touching anything.

| Issue | What | First look | Gotcha |
|---|---|---|---|
| **#81** | GitHub Actions CI matrix: `macos-latest` + `windows-latest`, py3.11–3.13; ruff + pyright + pytest + an import-safety check | **`.github/workflows/ci.yml`** (already on `main`) | **It already exists** — a `ci/bump-actions-node24` commit touched it. **Read it first**: is it a real workflow or a stub? Extend/fix it; don't add a second workflow. There is currently no PR-gating CI in practice, so confirm what actually runs. |
| **#90** | Pin a uv-managed CPython on Windows x64 (mirror `install.sh`'s pin) + a test asserting the pinned versions show up in the CI matrix | `install.ps1` / `install.sh` (how the toolchain is selected today), `pyproject.toml` (`requires-python`) | Pairs with #81 — the test couples the pin to the matrix so they can't drift. Don't pin a version the matrix doesn't test. |

**Suggested order:** **#81 first** (stand up / verify the matrix), then **#90**
(pin + the matrix-assertion test that depends on #81's matrix existing). They can
be one PR each, or stacked — but the repo's convention is **independent branches
off `main`** (a stacked PR was auto-closed once when its base branch was deleted
on merge, #143). If you stack, warn the user to merge in order.

## Definition of Done (this session)

- #81: CI runs ruff + pyright + pytest + import-safety on the full matrix and is
  **green**; it triggers on PRs to `main`. #90: the CPython pin is in place and a
  test asserts the pinned versions appear in the matrix; `pytest` / `pyright` /
  `ruff` green locally too.
- `/code-review` run per PR.
- Docs updated where behaviour changed (e.g. a README "CI" or contributing note if
  warranted; `requires-python` consistency).
- **Manual-QA:** none of your own beyond CI green. **Carry forward** the open QA:
  #122/#123 (`qa-handoffs/04-docs-discoverability-qa.md`) and #126
  (`qa-handoffs/02-vocabulary-recognition-qa.md`). Surface either if it lands.
- Roadmap **ledger** appended + **Current Session Prompt** rewritten.

## Post-S4 sequencing — how to hand off when you're done

Run the roadmap's **Handoff protocol**: append a Session Ledger entry, rewrite the
**▶ Current Session Prompt**, and (optionally) write the next session's handoff
doc. **Lead the next prompt with a recommendation.** The two strong candidates:

1. **S6 — Windows mouse hook (#120) — recommended next.** A `WH_MOUSE_LL` adapter
   feeding the S2 classifier core (#118, already merged) so a mouse side-button
   can trigger dictation — **a feature the user wants** (see the mouse-button
   memory) and end-to-end **Windows-testable here**. *QA:* physically click
   mouse4 / mouse5 / middle.
2. **S7 — Cold-start latency design grill (#101).** Code-free, parallel-safe, and
   the **deepest real-user complaint** (the long first-transcribe wait + paste
   misfiring as focus drifts during the load). Produces a short ADR + spun-out
   issues; it decides #97's approach and frames #96 / #67. Use
   `grill-with-docs` / `prototype`. Unblocks **S8** (#96, #97).

The **macOS track** (S9: #93/#94/#95/#121; S10 signing #91) waits for a real-Mac
QA day — export QA handoffs; **never claim Mac QA without the device.** With CI
(S4) in place, the pure parts of the macOS track become machine-checkable, which
is exactly why S4 comes first. **Parked** (no build without a fresh go-ahead):
#72, #80, #129, #130 (speech-helper spike — use `prototype`), #131.

If the user gives no steer, recommend **S6** next (high-value + Windows-testable),
with **S7** runnable any time in parallel (code-free).
