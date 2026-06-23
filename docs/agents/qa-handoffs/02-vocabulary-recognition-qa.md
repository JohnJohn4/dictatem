# QA Handoff — Session 2: Vocabulary recognition lift (#126)

**STATUS: PASS — 2026-06-23** (Windows 11 + NVIDIA GPU, `large-v3-turbo`, dev clone on `main`
run with `uv run --extra runtime-gpu python -m dictatem`). Part A: model load logged
`Vocabulary: 3 term(s) fed to faster-whisper via hotwords` (preferred path, faster-whisper
1.2.1); the empty-vocab baseline correctly logged no `Vocabulary:` line. Part B A/B (identical
2-clause script, same delivery, vocab OFF→ON) corrected **3/3** terms with no regression on
surrounding words:

| term | baseline (vocab OFF) | with vocab (ON) |
|---|---|---|
| Dictatem | Dictatum | Dictatem ✅ |
| _private term 1 (redacted)_ | mis-heard | corrected ✅ |
| _private term 2 (redacted)_ | mis-heard (split into two words) | corrected ✅ |

**Owed:** close #126 + post this table via `gh` (not installed on the QA box). **Gotcha:** on a
CUDA box launch with **`--extra runtime-gpu`** (pulls `nvidia-cublas-cu12` + `nvidia-cudnn-cu12`),
not `--extra runtime` — a plain `runtime` venv loads the model but fails the first GPU op with
`cublas64_12.dll is not found`.

---

**Device required:** Windows, with a real Whisper model and your usual microphone.
**Build under test:** `main` @ commit `4588f5d` or later (PR #134 merged). Run from
the **dev clone**, not the installed `dictatem` — the installed tool is pinned to
tag **v0.5.6** and does not contain #134 until a new tag is cut.
**Why this is manual:** the recognition-quality lift from faster-whisper `hotwords`
can't be unit-tested — it needs a real model plus a human judging transcription
accuracy. The wiring (pure parser, hint selection, pipeline) is already
machine-tested; this confirms the *behaviour*.

## Prerequisites
- Run the merged code from the clone (use **`runtime-gpu`** on a CUDA box — see Gotcha above):
  ```
  cd C:\Code\dictatem
  uv run --extra runtime-gpu python -m dictatem   # or --extra runtime on a CPU-only box
  ```
- Vocabulary file: **`C:\Users\johnc\.dictatem\vocabulary.md`** — bootstrapped with
  a commented example on first run after the merge.
- Log: tray **"Open log"**, or **`%APPDATA%\Dictatem\logs\daemon.log`**.
- **Restart Dictatem after every edit to the file** — it is read at daemon startup
  and the hint is baked in when the model loads. Editing without a restart does
  nothing. The first dictation after a restart cold-loads the model with the hint.

## Checklist (run on the Windows machine)

### Part A — confirm the `hotwords` path is taken (~1 min)
- [ ] Add 2–3 real terms you dictate that get mis-heard (one per line, uncommented)
      to `vocabulary.md` → fully quit + relaunch Dictatem → do one dictation → open
      the log. **Expect:** a line `Vocabulary: N term(s) fed to faster-whisper via
      hotwords`. `via hotwords` = preferred path live (faster-whisper 1.2.1).
      `via initial_prompt` would mean the older-version fallback. · **Issue:** #126

### Part B — confirm recognition actually improves (A/B, ~10 min)
- [ ] Pick **3–5 single-word terms** the model reliably mis-hears (proper nouns,
      brands, acronyms, non-English words). Write a fixed 2–3 sentence script that
      uses each naturally. Use the **same** script and speak it the **same way** in
      both runs.
- [ ] **Baseline:** comment out all terms in `vocabulary.md` → restart → dictate the
      script 2–3× → record exactly how each target term transcribes. **Expect:** the
      known mis-hearings. · **Issue:** #126
- [ ] **With vocab:** uncomment the same terms → restart → one warm-up dictation →
      dictate the identical script 2–3×. **Expect:** previously-mis-heard terms now
      correct or closer, with **no regression** on the surrounding words. · **Issue:** #126

## What to capture
- The exact log line (`hotwords` vs `initial_prompt`).
- A small before/after table: `term | baseline output | with-vocab output`.

## Gotchas
- Restart after every edit. Keep the list **short** — the file itself warns an
  over-long list *degrades* recognition; add only the handful that keep failing.
- Single-word terms are the reliable case. **Multi-word terms** (e.g. "machine
  learning") are space-joined with fuzzy boundaries — a known limitation flagged in
  PR #134; test those separately and treat as best-effort.
- Recognition is probabilistic — judge across the repetitions, not one utterance.

## On result
- **PASS** (log shows `hotwords` **and** a clear majority of terms improve, no
  regressions) → comment the before/after table on **#126** and mark the QA done in
  the roadmap **S2 ledger** entry (`docs/agents/roadmap.md`).
- **FAIL** (`hotwords` doesn't visibly help, or it unexpectedly logs
  `initial_prompt`) → comment the evidence on **#126** and open a follow-up issue.
  Candidates: the multi-word-delimiter decision flagged in PR #134, or a
  hotwords-weight / list-size tuning pass. Don't silently drop it.
