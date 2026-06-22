# Cold-start: the model loads when dictation is armed, and is fetched on first run

The first dictation of a session pays a cold model load. Until now that load was
**lazy at transcription time**: `TranscribeLifecycle.transcribe()` calls
`_ensure_loaded()` only once the user has *stopped* speaking, so the entire
cold-load wait lands in the dead air *after* the utterance, right before the
paste. On a capable desktop that is 3–4 s; on a weak laptop it has been observed
in the tens of seconds to minutes — long enough that the user clicks away and the
paste misfires (see
[ADR-0026](0026-focus-drift-holds-the-dictation-overlay-shows-phase-by-colour.md)).

Worse, the *first-ever* load on a machine also pays a **model-weights download**
from HuggingFace: the install scripts deliberately do **not** fetch a model
(`install.ps1` / `install.sh` — "lazy on first dictation"), so the weights are
downloaded the first time `WhisperModel(...)` is constructed. That means the
**first dictation currently needs the network** — breaking the local-first
promise at the worst moment (install, then dictate offline → failure) — and the
multi-GB download sits *inside* the dictation latency path.

The fix keeps the valued idle-unload behaviour (no model held in VRAM/RAM when
unused) while removing the felt wait. Three moves, none of which preloads on
launch by default.

## Decision

1. **Load on arm.** The Whisper load starts the instant dictation is *armed*
   (record-start), not lazily when transcription begins. It reuses the existing
   background `TranscribeLifecycle.preload()`, kicked from the daemon's
   record-start path, so the load overlaps the seconds the user spends *talking*.
   A short utterance hides a 3–4 s load entirely; a long laptop load is shortened
   by however long the user spoke. The load can only ever start *earlier* than
   today, never later, so this strictly dominates the status quo. A cancel (Esc)
   **leaves the load running to completion**: faster-whisper's load cannot be
   cancelled mid-flight (it is a blocking CTranslate2 call —
   [ADR-0016](0016-overlay-pill-model-loading-state.md)), and a finished load only
   helps the likely-next attempt. The
   [idle-unload](../../CONTEXT.md#hardware-tier) window (`idle_unload_minutes`,
   default 30) remains the **sole** reaper — no extra VRAM is held when idle.

2. **Fetch the model on first run.** The model weights are downloaded **once**, on
   the daemon's **first run** — which the installer itself triggers (`install.ps1`
   launches the daemon as its last step) — right after the
   [Hardware Tier](../../CONTEXT.md#hardware-tier) is resolved
   ([ADR-0007](0007-hardware-tier-resolved-on-first-run.md)) and while the
   just-installed machine still has the network. The fetch is **download-to-disk
   only**: the weights enter the on-disk model cache but are **not** loaded into
   VRAM, so the machine becomes offline-ready *without* holding a model resident.
   It is **best-effort** — if the machine is offline at first run, it silently
   falls back to today's lazy-download-on-first-dictation. It lives in the daemon,
   **not** the install scripts, because only the daemon resolves the *exact* tier
   (the scripts know only GPU-vs-CPU); replicating the
   [tier resolver](0007-hardware-tier-resolved-on-first-run.md) in PowerShell *and*
   bash would duplicate exactly what
   [ADR-0011](0011-install-via-thin-uv-tool-script.md)'s thin install keeps out of
   the scripts. This makes "offline after setup" **true** — the first *dictation*
   no longer needs the network — and lifts the multi-GB download out of the
   dictation latency path, leaving only the unavoidable AV-scan + disk-read +
   VRAM-transfer for load-on-arm to hide behind speech.

3. **Signal the fetch honestly.** A background first-run download must not look
   like nothing is happening (the install console returns while the daemon keeps
   downloading detached). When the user is *not* dictating, a
   [Tray Icon](../../CONTEXT.md#tray-icon) notification announces the one-time
   download and the [Usage Guide](../../CONTEXT.md#usage-guide) — which auto-opens
   on first run ([ADR-0021](0021-usage-guide-auto-opens-on-first-run.md)) —
   explains "first use downloads the model, then it runs offline." If the user
   *does* try to dictate while the download is in flight, the
   [Overlay Pill](../../CONTEXT.md#overlay-pill) shows a distinct **"Downloading
   model…"** loading caption, separate from "Loading Dict. Model"
   ([ADR-0016](0016-overlay-pill-model-loading-state.md) family).

## Considered options

- **Load on arm + first-run fetch (chosen).** Overlaps the load with speech and
  moves the download to the one moment setup is expected, with no model held idle.
- **Preload on launch by default.** Holds a model in VRAM from every launch —
  exactly the idle hogging the user explicitly does *not* want, and the valued
  idle-unload makes it pointless after the first window anyway. The opt-in
  `[startup] preload_model` (default `false`) remains for users who *do* want an
  instant first response and will trade the VRAM. Rejected as a default.
- **Keep lazy-load-at-transcribe (status quo).** The load lands entirely after the
  utterance, in dead air, overlapping nothing. Rejected.
- **Pre-download in the install script.** The script knows only GPU-vs-CPU, not
  the VRAM-resolved tier, so it cannot pick the *right* model without
  reimplementing the resolver in two shell languages — against the thin-install
  principle ([ADR-0011](0011-install-via-thin-uv-tool-script.md)). The daemon's
  first run, which the installer already triggers, resolves the tier for free.
  Rejected in favour of the first-run fetch.
- **Cloud / BYO-API for transcription (or the Transform LLM) to dodge the local
  load.** Spends the durable local-first stance ("no cloud anything, ever") to
  paper over a *once-per-machine* event that load-on-arm + the first-run fetch
  already shrink. Rejected **as a cold-start fix**. The separate question — whether
  some users would *prefer* a cloud endpoint, especially for the Transform LLM — is
  a deliberate, principle-spending decision of its own and is **parked** as a
  future design issue, not folded in here.
- **Adaptive idle-unload** (shorten or lengthen the 30-minute window by usage
  cadence). A real tuning lever, but orthogonal to the felt cold-start pain, which
  the three moves above already address. Not taken now; revisit if idle behaviour
  itself becomes a complaint.

## Consequences

- The daemon's record-start path triggers the background `preload()`. Because the
  load can only start earlier, this never regresses latency. The one cost is a
  record-then-immediately-cancel that loads for nothing — bounded by idle-unload
  and rare (arming is a strong intent signal); accepted.
- First run gains a one-time, best-effort, **download-to-disk** model fetch
  following tier resolution. Internet is needed at install **and** first run (both
  already accepted); the first *dictation* is offline. This sits alongside
  [ADR-0007](0007-hardware-tier-resolved-on-first-run.md) — tier resolution still
  happens once on first run; the fetch is a new step *after* it — so ADR-0007 is
  unchanged.
- The [Overlay Pill](../../CONTEXT.md#overlay-pill) gains a **"Downloading model…"**
  loading sub-state distinct from "Loading Dict. Model"; a tray notification marks
  the fetch start (and optionally completion); the auto-opened Usage Guide frames
  the one-time download. The `on_download_progress` /
  `set_progress_callback` seam already exists on the lifecycle/backend (currently
  stubbed — stored, never fired) and can later carry a **real percentage**; wiring
  it to HuggingFace's download progress is a **noted follow-up**, not required here.
- The README "Model loading & VRAM" section (shipped by #67, kept deliberately
  factual pending this design) now needs a refresh to describe load-on-arm and
  offline-after-setup. Tracked as a **new docs issue** — **not** a reopen of #67
  (closed in S3).
- The opt-in `[startup] preload_model` is unchanged for users who want a model
  resident from launch (it trades VRAM for an instant first response, the inverse
  of the default).
