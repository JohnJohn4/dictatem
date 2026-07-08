# Dictatem — Pre-launch Deep Review

**Date:** 2026-07-08 · **Version reviewed:** v0.6.4 (`main` @ `372b4a5`)
**Context:** the owner intends to launch publicly (LinkedIn) targeting Windows +
macOS users, positioned against paid tools (Wispr Flow, Superwhisper) with the
differentiators: everything local/private, no silent auto-cleanup of your
speech, Trigger Words, and a long-term "improve your speaking" philosophy.

**Method:** four parallel deep-dives — (1) architecture & decision review of all
27 ADRs + the full source tree, (2) security & privacy audit of the code,
install and update chains, (3) a sweep of all 105 GitHub issues (14 open, 91
closed) and 82 PRs, (4) web research on the 2025–26 dictation market, local STT
models, and single-word command recognition — plus a first-hand read of the
trigger-word code path. All code claims carry `file:line` references against
v0.6.4.

---

## 1. Executive summary

**The engineering is genuinely strong — above typical solo-project quality, and
above a lot of small-team quality.** The pure-core/adapter seam is enforced (not
aspirational), ~1,139 unit tests cover essentially all decision logic, CI runs
both platforms × three Python versions, concurrency discipline is deliberate,
and the ADR/ledger record — including honestly-documented wrong turns like the
v0.6.2-rc1 misdiagnosis — is the best part of the repo.

**The privacy claim is substantially true and defensible.** No telemetry, no
phone-home, no network listener, no audio or transcript ever transmitted, no
disk-persisted audio, safe local-file parsers, and the global hooks classify VK
codes without logging keystroke content. Four caveats need honest disclosure
(§4.2) and one default needs fixing before launch: **dictated text is currently
written to the local log file** (§4, F-2).

**Windows x64 is launch-ready. macOS is functional but not public-polish.**
One open issue is launch-blocking for a public Mac audience (#95 — silent
first-run permission failures); three more should follow fast (#91 signing,
#94 refreshed QA runbook, #93 paste drops); and macOS has **no update path**
(tray updater is Windows-only — flagged twice in the ledger, never filed).

**The trigger-word mishearing problem is real, explainable, and fixable** —
mostly with cheap, deterministic techniques that fit the project's philosophy
(§6). The current exact-match design structurally cannot recover "haste" or
"some of us", and three low-cost layers (recognition biasing, phonetic fuzzy
matching, confidence gating) would fix the bulk of it.

**The market positioning is stronger than the owner may realize** (§7). Wispr
Flow is cloud-only, had a 2025 privacy scandal (screenshotting users' windows to
its servers), and holds a 2.7/5 Trustpilot; the local-first counter-position is
now a recognized market segment — crowded on macOS, **almost empty on Windows**.
Dictatem's honest-transcription + coaching philosophy is occupied by no one.

---

## 2. What was built, and whether the decisions were right

### Architecture in one paragraph

OS hooks translate native key/mouse events into platform-neutral identities and
feed one pure `HotkeyClassifier`; a 5-state pure state machine drives
`DaemonCore`, which runs everything user-visible on the Qt main thread via a
50 ms tick and pushes slow work (Whisper transcribe, Ollama transform, model
loads/downloads) to worker threads that only enqueue results. Dictation pastes
via clipboard save → clutter-proof write → Ctrl+V → deferred restore; Trigger
Fires type via SendInput (backspaces + text). Every OS surface sits behind a
Protocol in `interfaces.py` with fakes for tests; native adapters are thin and
manual-QA'd. Platform assembly is one dataclass built per-OS.

### Decision scorecard (the ten most consequential)

| Decision (ADR) | Verdict |
|---|---|
| Thin uv-tool install from pinned tag tarball (0011/0015/0017) | ✅ Sound; honest trust story. PyPI (#72) correctly parked but revisit at launch for discoverability. |
| Clipboard+Ctrl+V for dictation, SendInput for Trigger Fire (0004) | ✅ Sound; the race analysis behind it (#23/#66) is textbook. |
| Backspace-count replacement for Trigger Fire (0001) | ⚠️ Most fragile load-bearing mechanism. Rails mitigate, but see F-1 (gate placement) and F-5 (grapheme counting). |
| Hardware tier baked on first run; config never rewritten (0007/0009) | ✅ Sound. Soft spots: no re-tier when moving config to a smaller GPU; the autostart toggle actually does rewrite config (F-8). |
| Dictation-never-lost buffer + built-in `paste` (0023) | ✅ Great design; implementation undercuts it in two places (F-2 arch, F-3 arch) — fix before marketing the guarantee. |
| Load-on-arm + first-run model fetch (0025) | ✅ Correct ("strictly dominates" reasoning holds); exposed the PortAudio deadlock, which was then root-caused properly. |
| Focus-drift detect-and-hold, never refocus (0026) | ✅ Safer than competitors. Gap: the "hold" shows the generic red *error* flash (F-13). |
| Native AVAudioEngine capture on macOS (0027) | ✅ Right call — deletes the deadlock class; the pure CI-tested resampler is genuinely good DSP. |
| State machine agnostic of Transforms (0002) | ⚠️ Challenge it *now*: `DaemonCore` grew ~6 ad-hoc booleans forming an implicit second state machine with no epoch concept — the root of F-6. Refactor before the next async feature. |
| No settings UI, discoverable TOML (0022) + curated hotkey list (0010/0020) | ✅ Coherent. But config *is* the settings surface, and validation is presence-only (F-11). |

### The issue tracker's story (105 issues, 82 PRs, ~8 weeks of sessions)

The tracker is unusually healthy: issue bodies carry root-cause analysis and
acceptance criteria, closures carry QA evidence from real hardware, and the
roadmap ledger cross-references accurately. The bug history clusters into five
classes, which are also the launch-risk map:

1. **Install/upgrade fragility** (~15 issues) — every new platform/OS-version
   combination broke install a new way (git prerequisite, CUDA DLLs, upgrade
   over a running daemon, ARM Python regression, the macOS 12/13 `av` wheel
   floor found *days ago* on one fresh machine). Lesson: QA on one machine does
   not cover the matrix. Expect week-one install reports from configurations
   nobody owns (Intel Macs, managed/DLP Windows, older drivers) and staff for
   fast patch releases — the v0.6.1→0.6.4 cadence proves the muscle exists.
2. **Clipboard/paste races** (~10 issues) — all fixed with defense-in-depth,
   but this class is where public users' app diversity (Word autocorrect,
   terminals, Electron, IMEs, RDP) differs most from the two QA'd machines.
3. **Hotkey/OS side-effect collisions** — largely resolved (#171); #177 is a
   fine-to-defer edge case that by its own criteria could be closed.
4. **Cold-start latency & model lifecycle** — resolved by ADR-0025/0026/0027.
5. **macOS platform integration** — the deepest, least-CI-verifiable area, and
   where all four remaining launch risks live (#95, #94, #93, #91).

Tracker hygiene nits: `needs-triage` is being used as "parked pending a
session" (7 of 14 open issues, four sitting ~a month); #182 is unlabeled; and
**four ledger follow-ups were never filed as issues**, most importantly the
**macOS in-app-updater gap** (also: `config.audio.device` on macOS, off-main-
thread AVAudioEngine `stop()`, "harden both native hooks together").

---

## 3. Correctness findings (architecture review)

Ordered by severity. Each is a placement bug in an architecture that makes the
fix cheap — typically a few lines in `daemon.py` plus a pure test.

**F-1 · HIGH — Trigger Fire's safety rail runs *before* the LLM call; the
destructive backspaces run unguarded *after* it.**
`rails_ok` is checked at `daemon.py:839-856`, then Ollama may run for up to
120 s (`model_timeout_s`; a cold LLM load is ~50 s). On completion `_do_paste`
explicitly exempts `replace > 0` from the drift check (`daemon.py:986-995` —
the comment says re-checking would "double-guard", but the two checks bracket
*different intervals*), and `pipeline.paste()` fires backspaces after a bare
unchecked `SetForegroundWindow` (`paste/win32_foreground.py:12-14`). Alt-tab
during a slow generation → N backspaces eat text in the newly-focused window,
then the transform output is typed there. This is the one genuinely dangerous
bug. **Fix:** re-compare the current `target_id` to `last_paste.target_id`
inside `_do_paste` when `replace > 0`; on mismatch, hold to the Most-recent
buffer like the drift path. One int compare.

**F-2 · HIGH — The "never lost" guarantee has a hole: the recovery buffer is
updated only *after* a successful paste.** `_most_recent_dictation` is set at
`daemon.py:1036-1038` after `paste()` returns; a `ClipboardContentionError`
after 5 retries (`pipeline.py:52-59`) or a `save()` failure propagates to the
catch at `daemon.py:765-767` → `_recover_to_idle` → the dictation is
irrecoverable, contradicting ADR-0023. **Fix:** populate the buffer (and
`set_has_last_dictation`) *before* attempting the paste.

**F-3 · MEDIUM — Silence timeout in toggle mode *discards* the recording.**
`(TOGGLE_REC, SILENCE_TIMEOUT) → CANCEL` (`state.py:139,143`) with no
notification. A user who taps, dictates three paragraphs, and gets interrupted
for 60 s loses everything silently — and the README implies pause-to-stop
transcribes ("auto-stops after a stretch of silence", README:82-88). **Fix:**
transcribe-and-hold on silence timeout (or at minimum notify + route to the
recovery buffer).

**F-4 · MEDIUM — Non-text clipboard content is destroyed by every dictation.**
`save()` reads only text formats (`win32_clipboard.py:54-63`,
`mac_clipboard.py:39-45`); `restore(None)` empties the clipboard. Screenshot →
dictate → screenshot gone. README's "saves and restores your clipboard"
(README:126) overclaims. Common flow (Win+Shift+S then dictate) — expect
reports. **Fix (interim):** correct the README; **fix (real):** preserve
non-text formats or skip restore when the saved content wasn't text.

**F-5 · MEDIUM — Backspace count is code points; apps delete graphemes.**
`char_count = len(normalized)` (`daemon.py:1027-1032`). Combining sequences and
emoji ZWJ clusters (which LLM "polish" output can emit, and transform output
becomes the next Last Paste) make the count over-delete or leave residue.
**Fix:** count what `send_text` sends per backspace-equivalent — segment by
grapheme cluster for counting; long-term consider select-and-replace instead of
backspacing where the platform allows.

**F-6 · MEDIUM — No epoch/generation on worker result queues → stale results
can paste.** ESC only clears `_transcription_active` (`daemon.py:1051-1065`); a
new dictation re-sets it while a slow cancelled worker still runs; its stale
result is indistinguishable (`daemon.py:674-697`). Same shape for the transform
queue. Plausible on CPU-tier machines. **Fix:** tag queue items with a
generation counter bumped on `_do_transcribe`/`_do_cancel`; drop stale.

**F-7 · MEDIUM — Idle unload races an in-flight transcription.**
`unload()` nulls the model + `empty_cache()` (`lifecycle.py:120-136`) with no
lock against a worker mid-`transcribe` (`faster_whisper_backend.py:143-149`;
`_last_activity` refreshes only after transcribe returns). Rare; native-crash
class. **Fix:** guard unload with an in-flight flag/lock.

**F-8 · MEDIUM — Config rewrite contradicts stated principles and the README.**
Tray "Start at login" calls `write_config` (`daemon.py:1902-1906`) via a
serializer that emits no comments (`config.py:293-305`) — so ADR-0009's "never
rewritten" and the roadmap's flat statement disagree with ADR-0012's sanctioned
write, user comments are destroyed, and the README's "commented,
self-documented config" claim (README:137-140) is false today. **Fix now:**
correct the README. **Fix later:** comment-preserving write or a sentinel.

**F-9 to F-15 (LOW, summarized):**
- **F-9** O(recording-length) `np.concatenate` on every 50 ms tick
  (`audio/buffer.py:56-85`) — ~380 MB/s churn at max duration on exactly the
  weakest machines. Walk chunks from the tail.
- **F-10** Dead/broken `Event.OOM` path would re-stop a closed capture and
  transcribe empty audio (`daemon.py:610-614`). Delete or fix.
- **F-11** Config values aren't type-validated (`config.py:258-290`) —
  `tap_threshold_ms = "fast"` explodes at runtime per-keypress; a corrupted
  TOML silently reverts everything to defaults. The config file is the entire
  settings surface; typos are first-class input.
- **F-12** `audio.sample_rate ≠ 16000` yields garbage transcriptions silently
  (`daemon.py:640-645` divides by the constant). Validate or resample.
- **F-13** The focus-drift "hold" shows the generic red *error* flash
  (`daemon.py:1010`) — ADR-0026 promised a "saved — say paste" signal; new
  users will read "error" and not know the text is recoverable. Best
  UX-per-line fix available.
- **F-14** Hotkey is dead while TRANSCRIBING (no `(TRANSCRIBING, KEY_DOWN)`
  handler) — reads as "frozen" on slow hardware. Add a pill cue.
- **F-15** `SetWindowsHookExW` result never checked
  (`wh_keyboard_ll.py:138-140`) — hook failure is silent: no hotkey, no log.
  Part of the already-ledgered "harden both native hooks" pass.

**Maintainability:** `daemon.py` (2,296 lines) is four modules in one file;
`DaemonCore`'s flag soup is F-6's root cause — extract a "dictation session"
object with an epoch. `_recover_to_idle` reaches into `self._sm._state`
(`daemon.py:1262`) — give the SM a `reset()`. Log the app version at startup
(`daemon.py:2156`) — the single most useful line for triaging user reports.
Classify model-*load* failures like the exemplary Ollama failure classifier
("Model unavailable; check log" will otherwise be the message for the most
common diverse-hardware failure).

---

## 4. Security & privacy findings

### 4.1 Findings

**S-1 · MEDIUM — Install & update chains execute remotely-fetched code with no
signature/hash verification.** The README one-liners are the standard
`curl|sh` trust model (acceptable, disclosed, script-readable); but the tray
updater re-downloads and executes `install.ps1` via `irm {url} | iex`
(`upgrade/win32_upgrader.py:37-49`) **automatically once an update is found**,
with no confirmation and no checksum. Mitigations already present: TLS
everywhere, hard-coded repo (`upgrade/core.py:24`), strict tag validation
(`upgrade/core.py:27-43`). **Fix:** add an explicit "Install update?"
confirmation before `spawn_upgrade`; publish SHA256 (or Sigstore) per release
and verify before install; pin the uv installer version+hash.

**S-2 · MEDIUM — Dictated text is written to `daemon.log` by default.**
`daemon.py:755-759` logs the first 80 chars of every dictation at INFO;
retained ~7 days in a plaintext rotating log (`logpaths.py:38-44`). Local-only,
but it contradicts the privacy positioning (and the transform path already
logs only counts — this is an inconsistency, not a design need). **Fix:** log
`len(text)` only, or gate the snippet behind DEBUG. One line. *Do this before
posting publicly.*

**S-3 · MEDIUM — `[transform].base_url` is unvalidated — the one config that
can silently void the privacy promise.** Dictated Last-Paste text is POSTed to
it (`ollama_backend.py:40-57`); a remote URL sends dictation off-machine in
cleartext with no warning (`config.py:110-116`). **Fix:** document that Trigger
Words send text to `base_url` and it must stay local; warn on non-loopback.

**S-4 · MEDIUM — Typed output strips only `\n`/`\r\n`, not other control
characters.** `normalize_pasted_text` (`paste/pipeline.py:37-46`) lets a lone
`\r`, tab, or ESC survive; the Trigger-Fire path *types* LLM output as
synthetic keystrokes (`win32_keystroke.py:144-170`), bypassing terminal
bracketed-paste protection. A bare `\r` typed into a focused shell is Enter.
This is the novel dictation-app risk class and exactly what a security-minded
audience will probe. **Fix:** strip all C0 controls (+ `U+2028/9`).

**S-5 · LOW — Unsigned, user-writable macOS app shim** (`macapp/bundle.py:
92-119`): any user-level process could rewrite it and inherit the TCC grants
(Accessibility + Input Monitoring) at next launch. No privilege escalation, but
no integrity guarantee either. Known (ADR-0014/#91); Developer-ID signing fixes
this *and* the "python3.12" trust problem. Positive note: the bundle is built
locally so there are **no Gatekeeper-bypass instructions anywhere in the docs**.

**S-6 · LOW/INFO — Runtime deps are floor-pinned and `uv tool install` doesn't
consume `uv.lock`** — each install resolves fresh from PyPI without hash
verification. Standard exposure; publish a hash-pinned constraints file for the
runtime extras when convenient.

### 4.2 The privacy claim, verified

Complete outbound-call inventory (verified by grep + read of every call site):
uv/CPython/PyPI/GitHub fetches at install; `api.github.com` **only when the
user clicks "Check for Updates"** (no timer — verified `daemon.py:1988`);
Hugging Face for the one-time model download; and Ollama at
`localhost:11434` (dictated text — stays on-device by default). **No
telemetry, no listener, no audio/transcript transmission, ever.** Audio and
all recovery buffers are memory-only (no tempfiles — grep-verified). Hooks
classify VK codes; no keystroke content is logged. Clipboard exclusion markers
are correctly implemented on Windows (`clipboard_markers.py:28-52`); macOS has
no equivalent (dictation sits on the pasteboard ~1.5 s before restore) — worth
a doc note.

**Honest phrasing for launch:** "Your voice and your words never leave your
machine. Dictatem downloads its model once from Hugging Face at setup; update
checks (manual, Windows) ask GitHub for the latest version number; Trigger
Words send text to *your own* local Ollama. That's the complete list." — This
is true today *except* for S-2 (the log line), so fix S-2 first.

---

## 5. Launch readiness

### Windows x64 — ready
Battle-hardened by repeated real-hardware QA; install hardening iterated
through five+ bug cycles; the race classes each fixed with tests. Residual
risk: managed/DLP machines and app diversity (F-4/F-5 class), plus audio-device
diversity under MME (#184 WASAPI pending).

### macOS — functional, not public-polish
A new public Mac user's most likely first experience, per the tracker:

1. **#95 (launch-blocking):** install "succeeds" → ~20 s of silence before the
   tray appears → hotkey pressed too early does nothing → missing permission
   grants fail *silently* thereafter. This is the churn point. Re-prompt-on-use
   is the issue's own "most-requested fix".
2. **#91:** the permission dialogs ask users to grant keystroke access to
   **"python3.12"**, not "Dictatem" — a trust problem at public scale. The S11
   signing decision ($99/yr Developer ID) should be made *before* launch.
   Recommendation: **pay it.** It fixes TCC identity, the Dock anomaly, S-5,
   and the credibility gap in one move; $99 is cheap against launch impressions.
3. **No macOS updater (unfiled):** tray "Check for Updates…" is Windows-only.
   Post-launch Mac fixes won't reach users unless they re-run the installer.
   At minimum: file the issue + add a README "Updating on macOS" note; better:
   a tray item that re-runs `install.sh`.
4. **#94:** the QA runbook is written against v0.4.0 (pre-audio-rewrite);
   uninstall, login persistence, and Esc-cancel have never been human-verified
   at the current version. Refresh + run it as the pre-launch gate.
5. **#93:** intermittent paste-not-landing right after daemon relaunch —
   uncharacterized; low frequency, self-healing, recovery exists. Characterize
   soon after launch.
6. **Matrix blind spots:** #187 proved the pattern days ago — one fresh Mac on
   a different OS version broke a QA-passed release. No Intel-Mac evidence
   exists anywhere in the tracker. Consider stating supported configs
   explicitly (Apple Silicon, macOS 12+) and let Intel be "best effort".

### Consolidated pre-launch checklist (ordered)

1. **S-2** — stop logging dictated text (one line). *Before the LinkedIn post.*
2. **F-1** — re-check the target rail in `_do_paste` for Trigger Fire.
3. **F-2** — populate the recovery buffer before the paste attempt.
4. **F-3** — silence-timeout: transcribe-and-hold (or notify), don't discard.
5. **README truth pass** — commented-config claim, clipboard-restore scope,
   pause-to-stop wording (F-8, F-4, F-3), plus the privacy-caveat list (§4.2)
   and a macOS "known limitations" note (python3.12 label, updating, no
   clipboard-history exclusion).
6. **S-4** — strip control chars in `normalize_pasted_text`.
7. **S-1 (soft part)** — confirmation dialog before the updater executes;
   version line at startup logging (with F-16/arch note).
8. **macOS:** decide S11 signing (recommend: pay), fix #95 onboarding, file +
   at least document the updater gap, refresh + run #94's runbook on a real Mac.
9. **S-3** — document the `base_url` caveat (one README paragraph + a
   non-loopback warning log).
10. Soon after: F-6 (queue epochs), F-13 (drift-hold caption), F-4 (real
    clipboard-format preservation), F-9 (tick perf), #184 (WASAPI).

---

## 6. The Trigger Word recognition problem

### Why "paste" becomes "haste" — the diagnosis, confirmed

Your intuition is correct, and it decomposes into three compounding causes:

1. **No language-model context.** Whisper is a seq2seq model trained on ~30 s
   sentence-like segments; its decoder is an implicit LM. Inside a sentence,
   "paste" is disambiguated by context; alone, the decoder falls back on priors
   over *all* plausible English words. "Haste" is a perfectly good word, and
   "some of us" is a high-prior segmentation of the same phoneme stream as
   "summarise". This failure mode is well-documented in the field
   (openai/whisper discussion #1455; whisper.cpp's command-tool thread #190
   reports exactly this class and mitigates with correction dictionaries).
   VoiceInk — a competitor — has the same complaint pattern on short utterances.
2. **Acoustic ambiguity at the onset.** /p/ is an unvoiced plosive; if the
   first ~50-150 ms of the utterance is soft or clipped, "paste" and "haste"
   are nearly identical signals. Users pressing the hotkey and speaking
   immediately routinely clip the first phoneme.
3. **VAD trimming.** `vad_filter=True` (`faster_whisper_backend.py:81`) can
   shave the quiet onset of a very short utterance, aggravating (2). Worth
   testing short-utterance behaviour with `vad_parameters` (e.g. more
   `speech_pad_ms`) or bypassing VAD when the recording is < ~2 s.

### What the current code structurally cannot do

- **Exact match only** (`transform/detector.py:65-78`): "haste" simply isn't in
  the alias map. No fuzzy tolerance, by design.
- **Multi-token utterances are rejected outright** (`detector.py:73`): "some of
  us" can never match — *and can never be fixed by adding an alias*, because
  aliases are single-token too.
- **Built-in `paste` has no alias mechanism at all** (`detector.py:21-22` — a
  frozenset): you can't even manually map "haste" to it today.
- **Trigger aliases are not fed to the recognizer.** `vocabulary.md` terms go
  to faster-whisper as `hotwords`, but "paste"/"summarise"/"polish" never bias
  the decoder — the words you most need heard correctly get no help.
- **Confidence is discarded.** The backend joins segment texts and drops
  `avg_logprob`/`no_speech_prob` (`faster_whisper_backend.py:143-149`), so
  nothing downstream can know the model was unsure.
- **Recording duration is available but unused** at the decision point
  (`daemon.py:645`) — the natural gate for a "this was probably a command"
  heuristic.

### The fix plan, ranked (field-evidenced)

**Layer 1 — Fuzzy + phonetic matching, duration-gated (do first).**
When the recording is short (< ~2.5 s) and the transcription is ≤ 3 tokens:
normalize, *join the tokens* ("some of us" → "someofus"), and score against the
alias lexicon with (a) RapidFuzz normalized edit distance and (b) Double
Metaphone equality (jellyfish). Accept on a conservative threshold.
`metaphone("someofus")` ≈ `metaphone("summarise")` — this catches both of your
examples. This is the de-facto standard in hobbyist voice-command stacks (Home
Assistant shipped a trained fuzzy matcher in 2025.9 for exactly this reason;
whisper.cpp command users keep correction dictionaries). It's deterministic
(fits the no-LLM-magic philosophy), pure, unit-testable, ~half a day. False-
positive control: the duration gate + small lexicon + threshold; add built-in
alias support for `paste` at the same time.
*Slots in cleanly:* extend `match_builtin_action`/`TriggerDetector.match` with
a fuzzy tier, threaded with `audio_duration_s` from `check_transcription_result`.

**Layer 2 — Confidence gating (same PR).** Expose `avg_logprob` /
`no_speech_prob` from the backend. Use bands: clean fuzzy match + decent
confidence → fire; borderline → flash a distinct pill colour and require the
user to say it again (or show "heard 'haste' — say again to paste"). Note the
caveat: whisper hallucinations can be *high*-confidence, so confidence is a
guardrail for the fuzzy matcher, not a standalone detector.

**Layer 3 — Bias the recognizer (one line, modest effect).** Append the trigger
lexicon to the `hotwords` hint (or, phrased as sentence-like context,
`initial_prompt="Voice commands: paste, summarise, polish."`). Evidence says
prompt biasing cuts rare-word errors substantially but is a nudge, not a fix,
and can slightly perturb normal dictation — keep the list short. A smarter
variant: **two-pass** — only when a short utterance fails to match, re-run
transcription on the same audio with command-biased context; the audio is
short, so the second pass is ~100 ms.

**Layer 4 — Trigger-word design guidance (zero code).** Talon's accumulated
wisdom: prefer multi-syllable, phonetically distinct command words; when a
user's custom alias collides phonetically with common words, warn at load time
(a pure metaphone check in `prompts.py` loading). "Summarise" is a good
trigger; bare "paste" is intrinsically bad — which is *why* it needs layers 1–3.
Document this in the Usage Guide.

**Layer 5 — Constrained side-recognizer (when 1–4 plateau).** A dedicated
command path for short recordings: sherpa-onnx open-vocabulary keyword spotting
(3.3 M-param model, keywords are a text file with per-keyword thresholds — no
retraining) or Vosk grammar mode (decoding restricted to your phrase list).
This is the architecture Home Assistant converged on (Speech-to-Phrase, 2025):
closed-set recognition for commands, open recognition for dictation. A day or
two of work, one small extra model. faster-whisper/CTranslate2 exposes no
grammar hook, so a side-recognizer is cheaper than constrained whisper decoding.

**Rejected/later:** Picovoice Rhino (licensing clashes with open-source
local-first); per-word openWakeWord training (friction); LLM intent
classification of ambiguous utterances via the already-optional Ollama (viable
"Command Mode" evolution — see §8, but don't lead with it: deterministic first).

---

## 7. Market position (mid-2026)

### The landscape in brief

- **Wispr Flow** — the funded leader ($55 M+ raised, ~$2 B valuation reports,
  $15/mo): cloud-only, **no offline mode**. Its 2025 scandal — the app was
  screenshotting active windows to its servers for "context awareness", and
  the Reddit user who surfaced it was banned before the CTO apologized — plus a
  **2.7/5 Trustpilot** (reliability complaints post-trial) makes it the perfect
  foil for a local-first pitch. Its Command Mode (separate hotkey, free-form
  LLM instruction on selected text) is the feature to watch.
- **Superwhisper** — the local-capable Mac incumbent ($8.49/mo / $250
  lifetime): local Whisper *and Parakeet*, per-app "Modes", optional local
  Ollama. Complaints: setup complexity, saves audio recordings by default.
  Windows version exists but lags.
- **Handy** — your closest philosophical competitor: free, MIT, ~20 k GitHub
  stars, Windows+Mac+Linux, fully offline (Whisper/Parakeet v3/Moonshine).
  HN loves the speed; complaints: minimal formatting intelligence, no
  commands/vocabulary/LLM features in stable. **Handy proves the demand for
  exactly Dictatem's architecture — and leaves Dictatem's feature ground
  (Trigger Words, vocabulary, replacements, coaching) unoccupied.**
- **VoiceInk** ($25–49, GPL, Mac-only), **MacWhisper** (€59, Mac, files-first),
  **Aqua Voice** (cloud, own "Avalon" model), **Willow** ($15/mo cloud),
  plus a long 2025–26 tail (Typeless, Monologue, Spokenly, VoiceTypr, Dictato,
  Amical, Ito…). Free built-ins improved: Windows Voice Access got on-device
  "Fluid Dictation" (Copilot+ only); Apple's new SpeechAnalyzer API is ~2.2×
  faster than whisper-large-v3-turbo on-device and third-party Mac apps
  already ship it.

### What this means for Dictatem

1. **The local-first + lifetime/free counter-position is now a recognized
   segment — crowded on macOS, nearly empty on Windows.** Local-first Windows
   options are basically Handy and a Superwhisper beta. Dictatem's Windows-first
   GPU-tier polish is the beachhead; lead with Windows in the launch, treat
   macOS as "early, improving fast" until §5's items land.
2. **Nobody occupies "we don't silently rewrite you — we help you improve".**
   Every competitor's pitch is invisible AI cleanup. ADR-0024's opt-in
   philosophy + the parked #130 coaching spike is a genuinely differentiated
   story — and it's honest, which the Wispr contrast amplifies.
3. **Privacy claims are under real scrutiny in this category** (Wispr scandal,
   Typeless AWS-routing analysis, Superwhisper's default audio retention).
   Dictatem's verifiable open-source no-network story (§4.2) is a launch asset
   — publish the outbound-call inventory as a PRIVACY.md; it's rare and
   credible. But fix S-2 first, and don't overclaim (§4.2 phrasing).
4. **Parakeet v3 has become table stakes** across the local-first cohort
   (Handy, Superwhisper, Spokenly, Dictato all ship it). See §8.

---

## 8. The future — where Dictatem could go

### Near term (weeks): launch + credibility
- §5 checklist; PRIVACY.md; a demo GIF/video in the README (the overlay pill +
  trigger-word flow demos beautifully); GitHub Discussions or an issue template
  for install reports (the #1 predicted inbound), including a "paste your
  daemon.log tail" ask — hence the version-at-startup log line.

### v0.7–v0.8: the trigger-word overhaul + model tier evolution
- Trigger-word layers 1–4 (§6) — this converts the flagship differentiator from
  "sometimes fires" to "reliably fires", which matters more than any new feature.
- **Add a Parakeet TDT 0.6B v3 backend** via `onnx-asr` (pip, no
  PyTorch/FFmpeg, runs CUDA/TensorRT/**DirectML**/CoreML) or sherpa-onnx,
  behind the existing `TranscriberBackend` protocol — the seam built for
  ADR-0027 makes this a contained change. Wins: ~1.4 WER points *better* than
  large-v3-turbo on English, ~10–40× faster, ~2 GB footprint, and **DirectML
  opens AMD/Intel-GPU Windows machines** the CUDA-only tier currently leaves on
  CPU. Keep faster-whisper for the 99-language tier. Interim zero-code win:
  swap the English tier to `distil-large-v3.5-ct2` (~1.5× faster, slightly
  better short-form WER, same API).
- Windows WASAPI capture (#184) — pairs naturally with the audio work.

### v0.9–v1.0: the differentiator nobody else has
- **The speech-improvement loop (#130, currently parked).** Local-only,
  opt-in: per-dictation stats (filler counts, WPM, most-corrected words, most
  misheard trigger words) accumulated in `~/.dictatem/`; a tray "Your speaking
  this month" view; gentle trends, not nagging. Pairs with Replacements
  (deterministic, user-chosen) and the polish Transform (explicit, on-demand).
  This is the "as good as Wispr but different" story made concrete: *their
  product hides your disfluencies; yours retires them.* No cloud tool can match
  it credibly, because the data must stay local to be acceptable.
- **Command Mode, Dictatem-style:** a free-form instruction path ("make this
  more formal") via the already-local Ollama, on a separate gesture (e.g. hold
  the combo + speak) — the LLM interprets intent, sidestepping single-word
  fragility entirely for power users, while Trigger Words stay the fast
  deterministic path. Wispr/Superwhisper validated the UX; Dictatem can do it
  without the cloud.
- macOS parity: signing + notarization (S11 — pay the $99), updater, #121
  mouse hook, onboarding polish; then PyPI (#72) + winget/brew for
  discoverability.

### Watch list (don't act yet)
- **Qwen3-ASR** (Apache-2.0, 52 languages, *native hotword biasing*, streaming
  + offline in one model) — could eventually serve both dictation and
  better-biased trigger recognition once Windows tooling matures.
- **Voxtral Realtime 4B** (Apache-2.0 true streaming); **Kyutai semantic-VAD**
  (knows when you've *finished speaking* — a path to push-free endpointing that
  would also fix F-3's UX); **Apple SpeechAnalyzer** as a Mac-native tier.
- Streaming/live-preview dictation as the eventual UX ceiling: the pill showing
  words as you speak. Big lift; the model watch list above is what makes it
  feasible later.

---

## 9. Overall verdict

This project is ready to be public, with a short list of honest caveats. The
codebase is disciplined, the decision record is exceptional, the privacy story
is real and verifiable, and the differentiation thesis (local + honest + makes
you better) is both true to the code and genuinely unoccupied market ground.
The gap between "ready to post" and "posted" is roughly: one privacy log line,
two high-severity guard placements, a README truth pass, and a decision about
how boldly to include macOS on day one. The trigger-word problem — the thing
that prompted the most doubt — is the *most* tractable item on the list: three
cheap deterministic layers away from reliable.

Launch it. Lead with Windows, frame macOS as early access until #95/S11 land,
publish the privacy inventory, and make the trigger-word overhaul the first
post-launch release — it's the feature the launch story rests on.
