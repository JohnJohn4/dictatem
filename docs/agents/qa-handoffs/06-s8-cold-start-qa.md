# QA Handoff — Session S8: Cold-start latency (#161 load-on-arm, #162 first-run fetch)

> **STATUS: PASS ✅ (2026-06-22)** — ran on Windows 11 + NVIDIA GPU (16 GB),
> model `large-v3-turbo`, from the dev clone on `main` @ `65637ec`. All four
> sections passed: **A** offline-after-setup · **B** first-run download +
> signalling · **C** load-overlaps-speech · **D** offline-first-run lazy
> fallback. #161 and #162 closed with the log evidence. Test **D** used
> `HF_HUB_OFFLINE=1` to simulate an unreachable Hub (a literal disconnect would
> sever the QA agent's own API link; identical model-fetch code path). A
> separate Win+Alt menu-activation focus bug surfaced during QA (see the S8
> ledger follow-ups).

**Device required:** Windows 11, a real Whisper model + your usual microphone,
and a way to **toggle the network off** (unplug Ethernet / turn off Wi-Fi /
airplane mode). A GPU is ideal (load-on-arm is most visible there); a CPU-only
box works too (slower loads make the overlap *more* visible).
**Build under test:** **`main` after PR #167 (#161) and #168 (#162) merge** — the
two features must both be present (load-on-arm fires the load that #162's pill
captions describe). If they haven't merged yet, check out a scratch branch that
merges both: `git checkout main && git merge feat/load-on-arm-161 feat/first-run-fetch-162`.
Run from the **dev clone**, not the installed `dictatem` tool (the installed tool
is pinned to an older tag).
**Why this is manual:** whether a *real* multi-GB faster-whisper load actually
overlaps speech, whether the first dictation truly works with the network
physically off, and whether the tray notification + pill captions render, can't
be machine-verified. The pure lifecycle/gating logic (load-on-arm guard,
prefetch best-effort + no-VRAM, caption selection, completion signalling) is
fully unit-tested (1073 passing) — this confirms the rest on real hardware.

## Prerequisites
- **Stop the installed daemon first.** The dev clone and any installed build share
  the single-instance lock (`~/.dictatem/daemon.lock`, #92), so kill the installed
  daemon (Task Manager → `pythonw.exe`, or the installed tray's **Quit**) before
  launching the clone, or the clone just logs "Another Dictatem instance is already
  running" and exits. (See the dev-double-daemon note.)
- Launch the clone:
  ```
  cd C:\Code\dictatem
  uv run python -m dictatem
  ```
  Config is read **once at startup** and never rewritten by the app (ADR-0009) —
  restart after any `config.toml` edit.
- Log: tray **"Open log"**, or `%APPDATA%\Dictatem\logs\daemon.log`.
- **Don't disturb your real model cache.** Tests B and D force a *real* first-run
  download into a **throwaway** HuggingFace cache by setting `HF_HOME` to a temp
  dir, so your normal cache is untouched. In the launching shell:
  ```
  $env:HF_HOME = "$env:TEMP\dictatem-qa-hf"      # PowerShell
  ```
  Delete that dir when done. Tests A and C use your real (already-downloaded) model.

## Checklist (run on the Windows machine)

### A — Offline-after-setup, model already on disk (~4 min) · the headline #162 guarantee
With your model already downloaded from normal use (real cache, **no** `HF_HOME`
override):
- [ ] Start the daemon online, then **fully disconnect the network** (unplug / Wi-Fi
      off / airplane mode). · **Issue:** #162
- [ ] If the model is resident, free it first: tray **Unload Model** (so the next
      dictation is a real cold load from disk). · **Issue:** #162
- [ ] Dictate normally (arm, speak, stop). **Expect:** it transcribes and pastes
      with the network **off** — the load comes off the local disk, no network is
      touched. No "Model Unavailable" / download error. · **Issue:** #162
- [ ] Reconnect the network when done.

### B — First-run download + honest signalling, throwaway cache (~10 min, online) · full #162 end-to-end
Forces a *genuine* first-run download into a temp cache so you can see the
download path. **Online** for this section.
- [ ] Set `$env:HF_HOME = "$env:TEMP\dictatem-qa-hf"` and **move your config aside**
      so this is a first run: `Rename-Item ~/.dictatem/config.toml config.toml.bak`.
      · **Issue:** #162
- [ ] Launch the daemon (online). Within a few seconds, **Expect:** a tray
      notification **"Dictatem — one-time setup … Downloading the speech model…"**.
      The log shows `First run — fetching the model to disk (one-time)` then
      `Fetching model weights to disk …`. · **Issue:** #162
- [ ] **While the download is still running**, arm + speak a dictation. **Expect:**
      the overlay pill caption reads **"Downloading model…"** (not "Loading Dict.
      Model…"); when the download + load finish it transcribes and pastes the audio
      you already spoke. · **Issue:** #162
- [ ] When the download completes, **Expect:** a tray notification **"Dictatem —
      ready … Speech model downloaded. Dictation now works offline."** (log:
      `Model fetched to disk in …`). · **Issue:** #162
- [ ] Now **disconnect the network** and dictate again. **Expect:** works offline
      (model is in the temp cache). · **Issue:** #162
- [ ] **Clean up:** stop the daemon, `Remove-Item -Recurse $env:TEMP\dictatem-qa-hf`,
      restore config (`Rename-Item ~/.dictatem/config.toml.bak config.toml`), and
      open a fresh shell (to drop the `HF_HOME` override).

### C — Load overlaps speech (~4 min) · #161
Model **not** resident (tray **Unload Model**, or right after a fresh start),
real cache, no `HF_HOME` override:
- [ ] Arm a dictation and **speak for ~6–8 seconds** before stopping. **Expect:**
      after you stop, it goes (almost) straight to transcribing — **no**, or only a
      brief, "Loading Dict. Model…" pill, because the load happened *while you were
      talking*. (On a fast GPU the load is ~3–4 s, fully hidden; on a slow
      CPU/laptop you may still see a shorter residual than before.) · **Issue:** #161
- [ ] Unload again, then arm and say a **very short** word (~1 s) and stop
      immediately. **Expect:** now you *do* see the "Loading Dict. Model…" pill for
      the residual load, which then transcribes + pastes automatically (you don't
      re-press). This is the short-utterance fallback. · **Issue:** #161
- [ ] Unload again, arm, start speaking, then press **Esc** mid-load to cancel.
      **Expect:** the dictation cancels (pill hides), and the model still finishes
      loading in the background — your **next** dictation is warm (no loading pill).
      Log shows the load completing after the cancel. · **Issue:** #161

### D — Offline at first run → silent lazy fallback (~5 min) · #162 best-effort
Proves an offline first run never breaks startup.
- [ ] Set `$env:HF_HOME` to a **fresh** temp dir and move config aside (as in B),
      but **start offline** (network already disconnected). · **Issue:** #162
- [ ] Launch the daemon. **Expect:** it starts normally (tray icon appears, no
      crash). The log shows the fetch was attempted and failed
      (`First-run model fetch failed (offline?) … will download on the first
      dictation instead`); **no** "ready" notification fires. · **Issue:** #162
- [ ] **Reconnect** the network, then dictate. **Expect:** the model downloads
      lazily on this first dictation (you'll see the load pill longer) and then
      pastes — i.e. it degraded to the old behaviour, not a hard failure. · **Issue:** #162
- [ ] Clean up the temp `HF_HOME` and restore config (as in B).

## What to capture
- Screenshots/notes of the two tray notifications ("one-time setup", "ready") and
  the two distinct pill captions ("Downloading model…" vs "Loading Dict. Model…").
- For C: roughly how much loading-pill time you saw for a long vs short utterance
  (the overlap working = little/no pill on the long one).
- `daemon.log` lines: `First run — fetching the model to disk`, `Fetching model
  weights to disk …` / `Model fetched to disk in …`, and (test D) the
  `First-run model fetch failed (offline?)` warning.
- Any failure: the exact step, observed vs expected, GPU/CPU, and the model tag
  (`[model].name` in config).

## Gotchas
- **Stop the installed daemon first** (single-instance lock) or the clone exits.
- A cold faster-whisper load **cannot be cancelled** mid-flight (ADR-0016) — that's
  why Esc in test C leaves the load running. Not a bug.
- The model-load timeout is `[behaviour].model_timeout_s` (default 120 s) and for
  *transcription* only drives the pill, never an abort — a slow cold load just
  shows the pill longer (relevant on weak CPU boxes; see the cold-load-timeout note).
- `HF_HOME` must be set in the **same shell** that launches the daemon, and a real
  first run needs `config.toml` absent — both are easy to forget. Open a clean shell
  afterward so the override doesn't leak into later runs.
- On a managed/work machine the very first launch can also lag while AV/EDR scans
  the new files — orthogonal to the model download (README "Model loading & VRAM").

## On result
- **PASS** → comment the evidence on **#161** and **#162** and close them; mark QA
  done in the **S8 ledger** entry in `docs/agents/roadmap.md`.
- **FAIL** → comment the captured evidence on the relevant issue, keep it open, note
  the hypothesis. Likely suspects: a model tag whose repo name→cache mapping differs
  (test B offline-after fails — check the load reads the same cache the prefetch
  wrote); the pill caption not flipping (overlay/tick wiring); or a slow box where
  "load overlaps speech" is only partial (expected on CPU — not a fail if the pill
  is merely *shorter* than a post-utterance load would be). Don't silently drop.
