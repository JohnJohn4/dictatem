# Handoff — Dictatem launch coordinator (2026-11-01)

> **Superseded 2026-11-04** by [`2026-11-04-coordinator.md`](2026-11-04-coordinator.md) (v0.8.0–v0.8.3 shipped).

You are the **coordinator** for getting Dictatem out to the public, stable and
working well. You orchestrate: delegate builds to worktree agents or
`implement-spec` sessions, merge what's verified, keep the tracker honest, and
walk the owner through the QA only they can do. **Lead with a recommendation**
on every decision; the owner wants to make calls quickly.

Read first: `CLAUDE.md`, then this file. Skip `docs/agents/roadmap.md`: the
docs map (#214) is retiring it, and **no new ledger entries** should be added.

## Where things stand

- **`main` = the owner-tested launch integration** (PR #268 merged
  2026-11-01). It contains the launch PRs, specs #225 (reliability), #226
  (Trigger Words) and #224 (Apple-GPU), plus today's QA fixes:
  - #270: race-free Win/Alt menu mask, signed injected keys, held-modifier
    wait, "Dictatem" toast identity
  - #271: self-diagnosing `Paste diag` log line
  - #274: English by default, plus `language` / `languages` / `"auto"` with
    sure-or-fall-back
  - #276: paced Trigger Fire typing
- **Windows QA: PASSED** on the owner's PC (GPU tier, Win+Alt). The checklist
  is `docs/agents/qa-handoffs/10-windows-rc-morning-qa.md` on the
  `rc/2026-11-01` branch.
- **Release v0.7.0 is in PR #279** (version pins, macOS Apple-GPU made
  **opt-in** via `DICTATEM_APPLE_GPU=1`, README *Known issues*). Draft
  release notes: `docs/agents/handoffs/release-notes-v0.7.0.md`.

## Do next, in order

1. **Ship v0.7.0 (Windows public, macOS beta).**
   1. Wait for the owner to merge PR #279.
   2. Then tag and publish the release:
      `git fetch origin && git tag v0.7.0 origin/main && git push origin v0.7.0 && gh release create v0.7.0 --title "v0.7.0 - Launch release" --notes-file docs/agents/handoffs/release-notes-v0.7.0.md`
   3. Smoke-test the public one-liner on Windows; the README one-liner now
      points at v0.7.0.
   4. Confirm the tray **Check for updates…** offers v0.7.0 to an older install.
2. **macOS QA round 2: tracking issue #281.** The owner's Mac tester (Apple
   Silicon) is available. Rewrite the beta tester guide for v0.7.0 using the
   checklist in #281, send it, triage the results, fix, and release patches.
   When the Apple-GPU checks pass, make the extra default-on again.
3. **Windows bugs:**
   - **#278:** Trigger Fire mangled in Windows 11 Notepad. Pacing didn't fix
     it. The likely route is select-and-paste, which reverses ADR-0004/#23,
     so it needs an owner decision and a re-check of the #23 race.
   - **#269:** rare residual paste failure in Notepad++. The `Paste diag` line
     now explains the next occurrence; ask the owner to report the time.
   - **#280:** config toast truncated (small).
4. **Signing (spec #227):**
   - The owner is enrolling as an **Organization: MATAVEX PTY LTD** (ACN 703
     599 562). Apple support case **103014763435** is open for a **new
     D-U-N-S**.
   - **Do not use 775047641**: that number is the owner's *sole-trader*
     record (JOHN MATTHEW WARD).
   - After approval, the owner runs `scripts/wizards/macos-signing-setup.sh`
     (Windows Git Bash; it sets the `release` environment secrets whose
     names are pinned in #258) and posts the Team ID on #253.
   - Decision PR **#264** (ADR-0014 amendment: signed spawn-not-exec App
     Launcher) is waiting for owner review.
   - **#254**'s real-Mac TCC gate needs no Apple account and is the go/no-go
     for the whole approach. Run it with the Mac tester early.
5. **Docs overhaul: wayfinder map #214** (8 tickets, after launch). #215 and
   #219 are agent-doable. Note: #219's findings now live in the closed spec
   #225.
6. **Parked or backlog** (only with the owner's go-ahead):
   - #277: "original" Trigger Word to restore the original dictation
   - #272: auto-translate (en↔zh)
   - #184: WASAPI
   - #182: Windows-on-ARM 3.11 pin
   - #72: PyPI
   - #121: macOS mouse hook
   - #165, #129, #130, #131

## Owner decisions already made (don't reopen)

- Windows launches first; **macOS stays beta** until #281 passes and signing ships.
- English is the default language; per-user pins, sets and auto are supported.
- `paste` re-pastes the **original** dictation, never the Trigger Fire output.
- The six-colour pill (white/amber/violet/coral/mint/sky) is accepted.
- Every "decision to sanity-check" in PRs #262, #263 and #265 is accepted.
- The config-rewrite tension (ADR-0009 vs ADR-0012 / `[trigger_words]`) is
  settled in docs map ticket #221, not ad hoc.

## How to work (hard-won today)

- **Never switch branches in `C:\Code\dictatem`.** Parallel sessions share
  it; use worktrees. A branch switch mid-run caused a cross-session collision.
- **Install a branch build on the owner's PC.** `install.ps1` has no ref
  option. Download the branch's `install.ps1`, replace the `$source`
  `…/refs/tags/vX.tar.gz` URL with `…/archive/<commit-sha>.tar.gz`, and run it
  with `Invoke-Expression`.
  - Use the SHA, not the branch name: uv caches by URL.
  - **Don't** append `2>&1`. It turns uv's progress into terminating errors
    after the old daemon has already been stopped.
  - The installer stops the old daemon itself.
- **Logs:** `%APPDATA%\Dictatem\logs\daemon.log`. Dictated text is never logged.
- **pytest:** run with `-p no:cacheprovider --basetemp=<unique dir>` when
  other agents may be running.
- **CI:** runs only on PRs into `main`. Retargeting a PR doesn't trigger it;
  close and reopen the PR.
- **Live keyboard/focus debugging:** a background Python recorder
  (GetAsyncKeyState, GetGUIThreadInfo, clipboard sequence/owner/formats)
  writing to a file worked well. Start it before asking the owner to act.
- **Never paste test text into the owner's windows** without confirming the
  target. One probe once landed in a log-file tab.
- **Owner's personal setup:**
  - a custom `caveman` Prompt File in `~/.dictatem/prompts/`
  - `paste_aliases = ["pasta"]`
  - a config backup at `~/.dictatem-backup-2026-11-01`
  - The owner may want `caveman` shipped as a built-in; ask.
- **Cleanup:** stale agent worktrees under `.claude/worktrees/` (their
  branches are all merged) and branches `beta/mac-2026-10-31` /
  `rc/2026-11-01` can go once v0.7.0 is tagged.
