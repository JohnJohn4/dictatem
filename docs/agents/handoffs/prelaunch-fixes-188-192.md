# Handoff — Pre-launch fixes: issues #188–#192

**Written:** 2026-07-08 · **Base:** `main` @ `372b4a5` (v0.6.4)
**Goal:** land the five pre-launch must-fixes from the deep review so the user
can post the public launch (LinkedIn). The user is waiting on these before
announcing.

> Note: the invoking user explicitly asked for this handoff to live in the
> repo's docs folder (normally handoffs of this kind go to a temp dir); it
> follows the repo's existing `docs/agents/handoffs/` convention.

## Context you need (read in this order)

1. `docs/reviews/2026-07-08-prelaunch-review.md` — the full review. §3
   (correctness findings F-1…F-15), §4 (security S-1…S-6), §5 (launch
   checklist). The five issues below are items 1–5 of §5's checklist.
2. `docs/agents/roadmap.md` — **Working principles** and **Definition of
   Done** apply to this session like any other: pure logic unit-tested, thin
   adapters, branch per issue, `/code-review` before each PR, PRs to `main`,
   no `Co-Authored-By`/generated-with trailers, append a Session Ledger entry
   and rewrite the Current Session Prompt when you finish.
3. The five issues — **each contains its full step-by-step spec and
   acceptance criteria; the decisions are already made, do not redesign**:
   - [#188](https://github.com/JohnJohn4/dictatem/issues/188) fix(privacy): stop logging dictated text (review S-2)
   - [#189](https://github.com/JohnJohn4/dictatem/issues/189) fix(transform): paste-time same-target re-check before Trigger Fire backspaces (review F-1)
   - [#190](https://github.com/JohnJohn4/dictatem/issues/190) fix(paste): populate the recovery buffer before the paste attempt (review F-2)
   - [#191](https://github.com/JohnJohn4/dictatem/issues/191) fix(hotkey): silence timeout stops-and-transcribes (review F-3)
   - [#192](https://github.com/JohnJohn4/dictatem/issues/192) docs(readme): truth pass + Privacy section + macOS notes (review F-8/F-4 wording, §4.2)

## Sequencing (matters — two pairs touch the same code/wording)

- **#190 before #189**, or stacked: both modify `DaemonCore._do_paste` in
  `src/dictatem/daemon.py` (#190 moves the buffer write that sits at the top
  of the success path; #189 adds a guard in the `replace > 0` branch). Doing
  #190 first keeps #189's diff clean. Separate branches/PRs per repo
  convention; if you stack, remember the `--delete-branch` auto-close hazard
  (see the S5/#143 note in the roadmap ledger).
- **#191 before #192**: #192's silence-wording step depends on whether #191
  has landed. #188 is independent — do it first, it's the smallest.
- Suggested order: **#188 → #190 → #189 → #191 → #192.**

## Facts established in the review session (save you re-deriving)

- The transform path already logs counts-only (`daemon.py:907-911`) — #188
  copies that pattern to the dictation path.
- `paste/focus_drift.py` has the pure `focus_drifted()` comparison #189
  should reuse; the daemon computes `audio_duration_s` at `daemon.py:645`
  (not needed for these fixes, but relevant to review §6 if scope creeps —
  resist that; the trigger-word overhaul is a separate post-launch release).
- For #191: `(TOGGLE_REC, MAX_DURATION) → _toggle_key_down` at
  `src/dictatem/state.py:140` is the exact pattern to mirror; the all-silence
  case falls through to the existing `EMPTY_RESULT → FLASH_ERROR` path.
- The privacy inventory for #192's Privacy section is fully written in review
  §4.2 — transcribe it, don't re-audit.
- `main` is clean and CI (win+mac × py3.11–3.13) is green as of v0.6.4.

## Manual-QA tail

None of the five requires real-hardware QA to merge (all pure/daemon logic
with fakes, plus docs). Flag one **optional** Windows eyeball for the user:
after #189/#190, alt-tab away during a Trigger Word generation → expect error
flash + nothing typed in the new window; kill the clipboard mid-paste is not
practically testable by hand — the unit tests cover it. If you can't run it,
note it in the ledger rather than exporting a formal QA handoff — it is
defense-in-depth verification, not gating.

## Definition of done for this session

- Five PRs merged (or open awaiting user review) with suite green,
  `ruff` clean, `pyright` 0 errors, `/code-review` run on each.
- Issues closed on merge with evidence, per repo convention.
- Roadmap ledger entry appended + Current Session Prompt rewritten (next up
  after this: the macOS launch gates — #95, #94, #93, S11/#91, #193 — see
  review §5).

## Suggested skills

- `tdd` — #189/#190/#191 are red-green naturals (write the failing daemon /
  state-machine test from the issue's Tests section first).
- `code-review` — run on each diff before opening its PR (repo DoD).
- `verify` — after #191, drive the silence-timeout flow if a runtime is
  available; otherwise rely on the daemon-level tests.
