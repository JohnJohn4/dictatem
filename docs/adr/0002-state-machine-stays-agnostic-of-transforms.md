# State machine stays agnostic of Transforms

The [Transform](../../CONTEXT.md#transform) step is handled entirely inside
`DaemonCore`. The hotkey state machine (`state.py`) has no
`TRANSFORMING` state and no transform-specific events.

When a transcription result comes back, `DaemonCore.check_transcription_result`
runs trigger detection synchronously. If a [Trigger Word](../../CONTEXT.md#trigger-word)
is detected and the safety rails pass, the daemon defers the
`TRANSCRIPTION_DONE` event, kicks off a second worker thread (Ollama call),
and only fires `TRANSCRIPTION_DONE` (with the rewritten text) once the
transform completes. From the state machine's point of view, "transcription"
just took longer this time.

## Considered Options

- **Add a `TRANSFORMING` state plus `TRANSFORM_DONE` / `TRANSFORM_FAILED`
  events.** More explicit for a reader of `state.py`, but adds new state
  transitions and tests for a concern (LLM rewriting) that the state
  machine doesn't otherwise care about.
- **Pre-paste pipeline of `TextTransformer` protocols.** Generalises every
  paste through a list of transformers, one of which is the trigger
  detector. Over-engineered until there is more than one transformer in
  the pipeline.

## Consequences

- ESC during the Ollama call cancels for free: the state machine is still
  in `TRANSCRIBING`, and the existing `(TRANSCRIBING, ESC) → CANCEL`
  handler does the right thing.
- The "transcribing" overlay stays up across both Whisper and Ollama —
  the user just sees a longer "thinking" indicator. No new overlay state.
- Trigger detection lives in `DaemonCore` (not in
  `TranscribeLifecycle`) so the transcribe layer remains a pure speech-to-text
  concern.
