# Trigger Fire replaces the Last Paste via backspaces + paste

A [Trigger Fire](../../CONTEXT.md#trigger-fire) replaces the previously
pasted text in the focused window by sending N backspaces (N = char length
of the Last Paste post-normalisation) followed by a normal paste of the
transformed text.

## Considered Options

- **Ctrl+Z + paste** — semantically the cleanest "undo the previous paste,
  then paste the new thing", but depends on the target app supporting undo
  in a way that maps one Ctrl+Z to one previous paste action. Many chat
  inputs, terminals, and web textareas violate this assumption.
- **Append the summary after the original** — never destructive, but leaves
  two versions of the text in the document and defeats the point of
  "summarize" as a one-shot transform.
- **Sentinel character (e.g. trailing zero-width space)** — detect whether
  the cursor is still at the end of our previous paste. Most robust, but
  pollutes pasted text with non-printable characters and breaks in apps
  that filter them.
- **Just paste at the current cursor, leave original** — simplest, but
  forces the user to manually delete the original.

Backspace-and-paste was chosen because it works in every text field
(no app-specific behaviour), keeps the surface ASCII (no sentinel chars
to break web inputs), and lets a user "undo" the trigger fire with Ctrl+Z
in most apps (each backspace and each paste is its own undo unit, so
recovery is awkward — see Consequences).

## Consequences

- The [Last Paste](../../CONTEXT.md#last-paste) must remember the exact
  character count of the post-normalisation text (the `_normalize`
  function in `paste/pipeline.py` adds a trailing space), not the
  pre-paste transcription length.
- Safety rails are essential: if the user has typed or clicked between
  the dictation paste and the trigger utterance, the backspaces will eat
  whatever is under the cursor. We gate the Trigger Fire on a foreground
  HWND match and a Last Paste age TTL (default 5 min, configurable). The
  TTL is an imperfect proxy for "the document hasn't changed" — it can't
  detect typing in the same window — but it bounds the stale-paste case
  where the user has long moved on. On rail failure we abort with an
  error flash and keep the document untouched.
- Recovery (Ctrl+Z) is multi-step in most apps because each backspace is
  its own undo unit. Acceptable for now; revisit if it becomes a paper cut.
