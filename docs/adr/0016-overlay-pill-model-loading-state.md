# The Overlay Pill shows a Model-Loading state while a model loads

The first dictation of a session pays a cold model load — Whisper into VRAM
(seconds) and, on the first [Trigger Word](../../CONTEXT.md#trigger-word), the
Ollama [Transform](../../CONTEXT.md#transform) model (a large tag like the former
`gemma4:e4b` default is ~50 s to load on a 4080). Until now that wait showed either the static amber
"transcribing" dot or nothing, and the Transform's default 30 s request timeout
was *below* the cold-load time — so the first Trigger Word failed outright (the
bug that prompted this, #74).

**Decision:** the [Overlay Pill](../../CONTEXT.md#overlay-pill) gains a
**Model-Loading** state — a caption naming what is loading ("Loading Dict.
Model", "Loading LLM Model", or "Preloading Models") with dots cycling 1→2→3→1 —
shown whenever a model is loading: the first-tap Whisper load, the first Trigger
Word's LLM load, and tray **Preload**. It is a new `OverlayPhase.LOADING` on the
pure `OverlayState`; the daemon flips it to the
[Status Dot](../../CONTEXT.md#status-dot) once the model is resident, or hides it
when Preload finishes.

This refines the Overlay Pill's role rather than contradicting it: the pill
already carried recording **state** via the Status Dot (ADR-0006). Loading is
another piece of recording-adjacent state the user needs *at the moment they
act*, so it belongs on the same surface — not the
[Tray Icon](../../CONTEXT.md#tray-icon), which stays static brand identity.

Supporting decisions that ship with it (#74):

- **One shared model timeout.** `[behaviour].model_timeout_s` (default 120 s)
  replaces `[transform].timeout_s` (30 s). It is the Ollama request timeout *and*
  the threshold past which transcription is "still loading"; faster-whisper load
  cannot be cancelled mid-flight, so for transcription it only drives the pill,
  never an abort. An upgraded config carrying the old `[transform].timeout_s` is
  logged-and-ignored and the new default applies.
- **Keep the LLM warm.** Dictatem sends Ollama `keep_alive` equal to Whisper's
  idle-unload window (`[model].idle_unload_minutes`), and tray Preload warms the
  LLM too (when present) — so the ~50 s cold load is paid at most once per idle
  window, not per Trigger Word.
- **A CPU-friendly default Transform model.** All Hardware Tiers default to the
  small `gemma4:e2b` tag (previously `gemma4:e4b` on capable tiers): it runs on
  CPU-only laptops (a little slow but fine) and co-resides with any Whisper tier
  on a modest GPU, so the headline Trigger Word feature works out of the box
  everywhere. Capable-GPU users can pin a larger tag in config (see ADR-0007).

## Considered options

- **Loading state on the pill (chosen).** Reuses the one surface the user is
  already watching; the pure state machine stays unit-testable; no new window.
- **A tray balloon notification.** Already used for earned tips (#41), but a
  balloon is transient, easy to miss at the exact moment of a cold load, and
  can't animate to read as "still working".
- **Do nothing, just raise the timeout.** Fixes the failure but leaves the user
  staring at a frozen amber dot for ~50 s with no sign of progress.

## Consequences

- `OverlayState` gains `LOADING` + `show_loading()` + `current_loading_text()`;
  the Qt widget renders the caption (manual-QA only). `OverlayRenderer` gains
  `show_loading()`.
- The daemon shows the pill on the cold transcribe path and the Trigger Fire
  path and dismisses it after Preload; a fast-tick poll flips loading→transcribing.
- The LLM warm (`OllamaBackend.warm()` / `is_model_available()`) is strictly
  best-effort: if Ollama is absent, the Transform is disabled, or a future Ollama
  drops the `keep_alive` / no-prompt-load semantics, it logs and continues —
  Whisper preload and the daemon are never affected. This keeps ADR-0008's "we
  only ever talk to Ollama, never manage it" stance intact.
