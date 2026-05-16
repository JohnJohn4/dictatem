# Trigger Fire types the rewritten text via SendInput, not clipboard + Ctrl+V

A [Trigger Fire](../../CONTEXT.md#trigger-fire) writes the transformed text
into the focused window by sending Unicode keystrokes via Win32
`SendInput` with `KEYEVENTF_UNICODE` — *not* by placing the text on the
clipboard and sending Ctrl+V. The regular dictation path still uses
clipboard + Ctrl+V because its constraints differ.

## Considered Options

- **Clipboard + Ctrl+V** (the regular dictation mechanism, originally also
  used here). Fails in the Trigger Fire path because backspaces queue on
  the target's message pump ahead of Ctrl+V. The target processes the
  backspaces serially before it ever reads the clipboard, and by then the
  daemon's `clipboard.restore()` in the `finally` block has already put
  the user's original clipboard contents back — so the target reads the
  *old* clipboard and pastes the wrong text. See [#23](https://github.com/JohnJohn4/dictatem/issues/23).
- **Clipboard + Ctrl+V + sleep proportional to backspace count.** Works,
  but the latency scales with replacement length (≈ 20 ms × N) — a
  100-char rewrite stalls the daemon for two seconds before the next
  hotkey can be processed. Brittle (per-char delay is a guess that varies
  per target app) and the wrong shape long-term.
- **Clipboard + Ctrl+V + retry on `restore()` `OSError`.** Actively
  *causes* the wrong-text-pasted symptom: retrying guarantees the daemon
  wins the race against the target's paste handler, so the target reads
  the restored old text.
- **Wait for a signal that the backspaces have drained before sending
  Ctrl+V.** No clean Win32 API exists for "wait until target has
  processed my queued input" against an arbitrary foreground app
  (`WaitForInputIdle` only covers a process's own initialisation, not
  message-pump drain). UI Automation polling or hooking the target are
  brittle and complex.

`SendInput`-typing was chosen because it eliminates the race by removing
the clipboard from the trigger-fire critical path entirely. There is no
shared resource for the daemon and the target to contend over: the
keystroke queue is one-way (daemon → target) and the daemon doesn't need
to clean up after itself.

## Consequences

- The [`KeystrokeSender`](../../src/dictatem/interfaces.py) Protocol exposes
  `send_text(text)` alongside `send_paste()` and `send_backspaces(n)`. The
  Win32 implementation encodes to UTF-16 LE so supplementary-plane
  characters (e.g. emoji) become surrogate-pair keystrokes.
- `paste.pipeline.paste()` branches on `replace_chars`. Regular dictation
  (`== 0`) is unchanged — clipboard + Ctrl+V is faster than typing for
  paragraph-length transcriptions and never had the race issue (Ctrl+V
  is alone in the keystroke queue, so the 100 ms settle is enough).
  Trigger Fire (`> 0`) takes the typed path with no clipboard contact and
  no settle delay.
- The user's clipboard is preserved across Trigger Fires for free — the
  typed path never reads or writes it.
- The typed output is "typed" from the target's perspective, not
  "pasted". IDE/editor undo histories treat each character as its own
  edit (or batch typed characters in their own way), distinct from how
  they treat one paste op. Acceptable for the summarize use case where
  undoing a rewrite character-by-character is fine; revisit if a future
  Transform needs single-step undo.
- A small set of apps filter synthetic Unicode `SendInput` (security
  dialogs, some game overlays, the credential prompt for UAC). Same
  constraint AutoHotkey, espanso, and other text-expander tools live
  with; flagged in CONTEXT only if a user reports it.
- The pre-existing `OSError` from `clipboard.restore()` on the regular
  dictation path is now caught + logged as a warning (instead of
  propagating up and ending the dictation cycle with an `ERROR`-level
  traceback). Trade-off: the user's original clipboard isn't restored
  when there's contention. Same root cause as the trigger-fire race but
  much rarer on the dictation path; not worth solving more thoroughly
  right now.
