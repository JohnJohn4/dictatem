# Dictation is never lost — clipboard fallback without focus detection

> Relates to [ADR-0004](0004-trigger-fire-types-via-sendinput-not-clipboard.md)
> (Dictatem types via `SendInput`, not the clipboard) and the
> [Last Paste](../../CONTEXT.md#last-paste) safety rails.

Wispr Flow, when it cannot paste into a focused field, preserves the dictation
on the clipboard and offers a Scratchpad / "Paste Last Transcript" recovery. The
competitor scan surfaced the underlying want: a dictation should **never be
silently lost** when there is nowhere to type it. This ADR records how Dictatem
honours that want without abandoning the design that makes it universal.

## Decision

Because Dictatem types via `SendInput` (ADR-0004), it types **blind** — there is
no "did the text land?" signal, unlike a clipboard paste. Rather than try to
recover that signal, Dictatem keeps the blind-typing model (it is what lets
Dictatem work in every app without per-app knowledge) and guarantees
never-lost via two cheap mechanisms — the [Clipboard Fallback](../../CONTEXT.md#clipboard-fallback):

- **A "no foreground target" guard.** When there is no foreground window to type
  into, Dictatem places the transcribed text on the **clipboard** and flashes a
  brief notice on the [Overlay Pill](../../CONTEXT.md#overlay-pill) (reusing the
  pill's existing caption / error-flash path, ADR-0016) instead of typing into
  the void.
- **An on-demand "Copy last dictation" tray item.** Copies the most recent
  dictation text to the clipboard whenever the user asks — the recovery for the
  case the cheap guard cannot see ("a window is focused, but the focused control
  is not a text field").

A focus-preserving **"Paste last dictation" hotkey** (re-type into the current
field) is the natural follow-up but is **deferred**: it needs a *second* trigger
binding, and the classifier handles one combo today — it is better designed
alongside that work.

## Considered options

- **Detection-based auto-fallback.** Detect editable focus (e.g. UI Automation
  "is this a text control?") before typing; auto-copy when it is not. Closest to
  Wispr's behaviour, but UI Automation is unreliable across Electron, games, and
  custom controls — it would reintroduce the per-app failure surface that
  blind typing exists to avoid, and silently mis-fire. Rejected.
- **Always-also-copy every dictation** (with save/restore to avoid clobbering the
  clipboard). Never loses text and needs no detection, but it reverses ADR-0004's
  deliberate clipboard-avoidance, re-introduces clipboard juggling, and changes a
  property users rely on (their clipboard staying put). Rejected.
- **A Scratchpad window** (editable, with a Copy button) for the no-target case.
  An editable surface fights Dictatem's thin/minimal philosophy and the read-only
  in-app stance (ADR-0019); the overlay notice + clipboard already deliver
  "your text is safe". Rejected.
- **Copy-last only, no guard.** Simplest, but a dictation typed into the void is
  only recoverable if the user thinks to open the tray — a weaker guarantee.
  Rejected in favour of the automatic guard for the obvious case.

## Consequences

- "Most recent dictation" is a distinct notion from
  [Last Paste](../../CONTEXT.md#last-paste): a no-target dictation produces text to
  copy even though nothing landed in a window and no `target_id` was captured, so
  it does not arm [Trigger Words](../../CONTEXT.md#trigger-word). Implementations
  must hold the transcription independently of a successful paste.
- Clipboard preservation (Wispr's save/restore-around-paste feature) is **moot**
  for Dictatem: regular dictation and Trigger Fire never touch the clipboard, so
  the user's clipboard is only ever written in the explicit fallback/copy cases.
- The guard is intentionally partial (no-foreground-window only). The Usage Guide
  should frame the on-demand copy as the catch-all rather than implying every
  failed paste is auto-recovered.
