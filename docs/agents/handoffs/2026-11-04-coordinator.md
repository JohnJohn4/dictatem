# Handoff: Dictatem coordinator (2026-11-04)

Supersedes [`2026-11-01-launch-coordinator.md`](2026-11-01-launch-coordinator.md).
Read `CLAUDE.md`, then this file. Skip `docs/agents/roadmap.md` (retiring via
#214; no ledger entries). **Lead with a recommendation** on every decision; the
owner decides quickly and tests on real machines.

## Where things stand

**Latest release: v0.8.3** (Windows public; macOS beta). Since v0.7.0:

| Release | What | PRs | Decision records |
|---|---|---|---|
| v0.8.0 | Install/launch **Engine Prewarm**, NVML-first GPU probe, cache-first model load (offline after install), PySide6-Essentials (−440 MB), mic re-scan + tray Microphone menu, hotkey-first tray, startup/load/hotkey diagnostics; **Resident Engine** + PySide import-hook fix; installer exit-code fix | #296, #299 (replaced #297), #298 | ADR-0029, ADR-0030 §1, ADR-0031 |
| v0.8.1 | Native Windows tray menu (left-click; the flyout stays open; an outside click closes it) | #301 | ADR-0030 §2 |
| v0.8.2 | **Alt+Enter / lone Alt no longer starts a dictation** after Win+L or over admin windows | #303 | ADR-0032 |
| v0.8.3 | "Dictatem" Start-menu shortcut (start again after Quit) | #305 | ADR-0030 §3 |

The full measurement story, dead ends included, is in
[`2026-11-02-slimming-work-laptop.md`](2026-11-02-slimming-work-laptop.md),
with the home-PC smoke test at its end. Release notes:
`release-notes-v0.8.{0,1,2,3}.md`. New glossary terms: *Engine Prewarm*,
*Resident Engine* (`CONTEXT.md`).

Results on the MDE work laptop:
- first dictation after install: ~2 min 14 s → ~27 s;
- first dictation after a break: ~13 s → ~1.5 s;
- tray after a fresh install: 37 s → ~16 s;
- hotkey → pill: 1–1.9 s → 0.45–0.8 s on the built-in mic, ~0.05 s on a
  headset.

Home PC: no regressions.

## Do next (recommendations)

1. **macOS smoke test of v0.8.x.** None of the v0.8 changes has run on a Mac.
   CI is green on macOS, but the tray (Qt path), import-hook patch and config
   keys are untested by hand. Fold it into #281's round.
2. **Open questions from the owner's colleague's work-device install:**
   - Did the first-run Usage Guide not appear at all, or did it open behind
     other windows? If it opened behind, bring it to the front (Windows
     foreground lock).
   - What did `Speech engine ready (N s)` say? It's a second data point for
     the 20 s threshold.
3. **#269** (first dictations after a fresh install didn't paste) may have been
   the load stall that the prewarm and resident engine removed (H4 in the
   slimming handoff). Ask the owner whether it has recurred since v0.8.0
   before closing it.
4. **#184 WASAPI:** the remaining record-start time is mostly MME opening the
   built-in mic (450–780 ms). WASAPI might cut it. The mic must never be held
   open (ADR-0031 §4).
5. Carried over, all still open: #281 macOS QA round 2; #278 Trigger Fire in
   Notepad (needs an owner decision on select-and-paste); #280 truncated
   toast; signing #227 / #253 / #254 / #258 and decision PR #264 (details in
   the 2026-11-01 brief); docs map #214 / #215 / #219 / #221; parked items
   #277, #272, #182, #72, #121.

## Owner decisions already made (don't reopen)

- Everything in the 2026-11-01 brief's list still stands.
- CPU does not become the default; NVIDIA DLLs are not pruned; `onnxruntime`
  and `av` stay.
- Load-on-arm stays. The model is not loaded at launch by default; the Engine
  Prewarm and Resident Engine hold **no model and no VRAM**.
- **The microphone is never held open between dictations** (privacy, and
  other apps need it).
- Tray: no Preload; Start/Stop only without a hotkey; Unload stays;
  native menu on Windows.
- Slow-scan threshold is **20 s** (normal PC 6–8 s; MDE cold scans 45–212 s).
- Fixes ship as small `vX.Y.Z` releases; users update via **Check for
  updates…**.

## How to work (hard-won)

- **Release process** (v0.8.0–v0.8.3):
  1. Feature PR into `main`; CI green; squash-merge with a `(#N)` title.
  2. Release PR `chore(release): vX.Y.Z` bumping `install.ps1` (one-liner,
     two comments, `$source`), `install.sh` (one-liner, comment,
     `DICTATEM_TAG`), the README one-liners, `pyproject.toml`, the `dictatem`
     entry in `uv.lock`, plus `docs/agents/handoffs/release-notes-vX.Y.Z.md`.
  3. Annotated tag `vX.Y.Z - <title>`, then a GitHub release with those
     notes.
  4. Verify the raw `install.ps1` at the tag, the tarball (HEAD 200) and
     `fetch_latest_tag()`.
- **Stacked PRs through the API:** retarget the child to `main` *before*
  deleting the merged base branch. An API ref delete closes the child (that
  is how #297 got replaced by #299).
- **On the work laptop:**
  - `gh` isn't installed. Use the REST API with the token from
    `git credential fill` (never print it).
  - Launch the daemon detached with `Invoke-CimMethod Win32_Process Create`.
    `Start-Process` children die with the agent session.
  - A local-checkout install needs `--reinstall-package dictatem
    --refresh-package dictatem` (uv reuses cached builds of the same version).
- **Profiling:** `uvx py-spy record -p <child interpreter PID>`, not
  `Scripts\pythonw.exe` (that's a redirector). Never time with `--native`:
  it distorts timings 10–15×.
- **Diagnostics in `daemon.log`:**
  - `Startup timing`, `Model load breakdown … (resolve, construct)`,
    `Transcribe call took`;
  - `Hotkey <EVENT>: <state> -> <state> [...] lag, handled in` and
    `Hotkey: ignored stale held key(s)`;
  - `Engine prewarm finished in`, `Engine kept resident`.

  Dictated text is never logged.
- The owner's work laptop has a hand-written
  `~/.dictatem/.slow_engine_load` (its slow prewarms predate the code).
  That's correct for that machine.
- Never inject the hotkey or paste unattended. Ask the owner to act and read
  the log.
