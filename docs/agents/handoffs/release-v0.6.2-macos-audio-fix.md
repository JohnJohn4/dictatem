# Release handoff — v0.6.2 (macOS audio fix, #161)

**Status:** the #161 fix (option-D native AVAudioEngine capture) is **built,
`/code-review`'d, CI-green on PR #185, and real-Mac-QA PASSED (2026-07-05)**. All
that remains is the outward-facing release. This doc is the exact, copy-paste
runbook — plus drafted release notes and the #161 close comment.

## Why v0.6.2

A **patch** bump (0.6.1 → 0.6.2): this is a macOS bug fix (the first-dictation
freeze), behind the existing `AudioCapture` protocol, no user-facing feature
change. It **supersedes the misdiagnosed `v0.6.2-rc1`** (which blamed ctranslate2
and shipped a warm-up that only worsened the real PortAudio race). No final
`v0.6.2` was ever tagged, so this is the real v0.6.2. If you'd rather divorce it
entirely from the rc1 mistake, `v0.7.0` also works — but v0.6.2 is the natural,
convention-matching choice.

## QA evidence (for the #161 comment / release notes)

Real-Mac QA on the **exact repro device** — Apple M3 / macOS 26.5 (build 25F71) /
arm64 — option-D build installed as the **real launchd daemon + generated
`Dictatem.app`** via `DICTATEM_REF`. Full evidence in `docs/diagnostics/dictatem-161-qa/`
(kept local — tester home paths) and `qa-handoffs/09-*` (STATUS: PASS).

| Check | Result |
|---|---|
| 1 — No freeze, cold first dictation under load ×5 (**the crux**) | **PASS** — 5/5, daemon log shows `Model loaded → Processing audio → Transcription complete → Paste: sent` every round; the post-"Model loaded" silence (the deadlock signature) never appears |
| 2 — Records → transcribes → pastes | **PASS** — "the quick brown fox…" typed exactly |
| 3 — Mic off between dictations | **PASS** — orange mic indicator only while holding the hotkey |
| 4 — TCC Microphone under `.app`/launchd identity | **PASS (capture)** — works under the packaged identity; prompt not freshly re-observed (pre-granted from the Jul-3 run) |
| 5 — Back-to-back + long dictation | **PASS** — 5 shorts + a 41 s dictation → 329 chars, no hang |

Honest caveats (both non-blocking): Round 1 had a one-time **11.5 s cold-disk
model-load hitch** (recovered and typed cleanly — the expected first-load hitch,
not a freeze); the TCC prompt was **not freshly re-observed** (already granted). QA
ran on **ctranslate2 4.8.1** and passed → the superseded `<4.8` pin is confirmed
unneeded (not applied).

## Release steps

### 1. Merge the fix

```sh
gh pr merge 185 --squash --delete-branch   # or --merge, per your preference
git checkout main && git pull
```

### 2. `chore(release): v0.6.2` — bump the version + install pins together

Bump the tag in the two installers + the README, and the version in
`pyproject.toml` + `uv.lock`. The tag appears only as the current pin in those
three files, so a scoped replace is safe (it must NOT touch the historical
`v0.6.1` in `docs/adr/0017-*` or the instruction text in the roadmap/handoffs):

```sh
# installers + README: v0.6.1 -> v0.6.2 (comments, DICTATEM_TAG, $source, one-liners)
sed -i 's/v0\.6\.1/v0.6.2/g' install.sh install.ps1 README.md
# package version
sed -i 's/^version = "0.6.1"/version = "0.6.2"/' pyproject.toml
uv lock                       # regenerates the dictatem==0.6.2 entry in uv.lock
```

Verify nothing else drifted and the pin-guard test still passes, then commit:

```sh
git grep -n "v0\.6\.1" -- install.sh install.ps1 README.md   # expect: no matches
uv run pytest tests/test_install_python_pin.py -q            # guards the 3.12 pin
git add install.sh install.ps1 README.md pyproject.toml uv.lock
git commit -m "chore(release): v0.6.2 - macOS audio fix (native AVAudioEngine, deletes the PortAudio stop deadlock)"
```

### 3. Tag + push

```sh
git tag v0.6.2
git push origin main --tags
```

### 4. GitHub release

```sh
gh release create v0.6.2 --title "v0.6.2 — macOS audio fix (native AVAudioEngine)" --notes-file - <<'NOTES'
## macOS first-dictation freeze — fixed for good (#161)

The macOS "first-dictation freeze" was a **PortAudio ↔ CoreAudio HAL deadlock** in
the microphone `stop()` on hotkey-release, triggered when the model loads during
recording. This release **replaces PortAudio on macOS with Apple's AVAudioEngine**
(behind the existing capture protocol), so the deadlock class is **deleted, not
merely avoided**. It also restores per-dictation mic release (the mic turns off
between dictations). **Windows is unchanged** (still sounddevice).

Verified on the exact repro device (Apple M3 / macOS 26.5): 5/5
cold-first-dictation-under-load with no freeze, records/transcribes/pastes,
mic-off between dictations, and a 41 s dictation, all clean.

This **supersedes the misdiagnosed `v0.6.2-rc1`** (which blamed the ctranslate2
layer). See ADR-0027 for the full decision and evidence.

**Install / upgrade:** re-run the one-liner in the README (macOS `install.sh`,
Windows `install.ps1`) — now pinned to `v0.6.2`.
NOTES
```

### 5. Close #161 with the evidence

```sh
gh issue comment 161 --body-file - <<'BODY'
Fixed in **v0.6.2** via **option D — native AVAudioEngine capture** (ADR-0027): PortAudio is replaced on macOS by Apple's `AVAudioEngine`, so the `Pa_StopStream` HAL deadlock class is deleted, not avoided. Windows is unchanged.

**Real-Mac QA — PASS (2026-07-05)**, on the exact repro device (Apple M3 / macOS 26.5 / 25F71), installed as the real launchd daemon + generated `Dictatem.app`:

- **No freeze on the cold first dictation under load — 5/5.** The daemon log shows `Model loaded → Processing audio → Transcription complete → Paste: sent` every round; the post-"Model loaded" silence that characterized the deadlock never appears.
- Records → transcribes → pastes exactly; mic turns off between dictations; Microphone capture works under the packaged `.app`/launchd identity; a 41 s dictation → 329 chars, no hang.
- Honest caveats (non-blocking): Round 1 had a one-time 11.5 s cold-disk model-load hitch (recovered and typed — expected, not a freeze); the TCC prompt was pre-granted so not freshly re-observed.

Closing on this evidence. Shipped in v0.6.2, superseding the misdiagnosed `v0.6.2-rc1`.
BODY
gh issue close 161
```

## After the release — recommended cleanup (outward-facing, your call)

```sh
# the superseded, misdiagnosed work (ADR-0027 annotates it) — never on main:
git push origin --delete fix/macos-coldstart-deadlock-161
git push origin --delete v0.6.2-rc1        # the only rc that was tagged; no final v0.6.2 existed
git tag -d v0.6.2-rc1                        # local copy too
```

Local, untracked diagnostics under `docs/diagnostics/` (the `20260630-193659/`
capture incl. a full source-tree copy + daemon logs + `config.toml`,
`dictatem-161-spike-*`, `dictatem-161-qa/` QA evidence, and the untracked
`FIX-PACKAGE` artifacts) carry home paths — they were deliberately **left local,
not committed** (public repo). Delete them or keep them for reference; either is fine.

## Follow-ups (tracked, not part of this release)

- **#184** — Windows WASAPI switch; reuses this release's pure resampler.
- `config.audio.device` selection on macOS (the native backend warns + uses the
  default input today — ADR-0027 known limitation).
- Off-main-thread `stop()` teardown (option ii/iii) — only if the one-time
  first-dictation cold-load hitch proves annoying in the field.
