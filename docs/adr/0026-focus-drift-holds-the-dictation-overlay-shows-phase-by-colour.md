# Focus drift holds the dictation rather than mispasting; the overlay shows phase by colour

> Builds on [ADR-0025](0025-cold-start-load-on-arm-fetch-on-first-run.md)
> (load-on-arm cuts the wait that *causes* most drift) and refines the recording-
> state half of [ADR-0006](0006-tray-icon-is-static-brand-not-state.md) (the tray
> stays static brand; recording state moves off the Status Dot onto the pill).

Two user-reported problems share one surface — the
[Overlay Pill](../../CONTEXT.md#overlay-pill) — and one root cause, the wait
before a paste:

- **Focus drifts during the wait, so the paste misfires.** Today the regular-
  dictation paste captures the foreground **at paste time** (`paste/pipeline.py`),
  so the text lands in whatever window has focus when transcription *finishes*.
  During a long load (or any dictation the user talks through while alt-tabbed)
  that is often not where they started — the paste lands in the wrong window, which
  is occasionally embarrassing (private text into a chat) and occasionally
  **dangerous** (dictation landing in a terminal can run as a command).
- **The red Status Dot looks like a stop button but isn't.** A user instinctively
  clicked it to stop recording; nothing happened. The dot reads as an affordance it
  does not have, and it competes with the waveform to convey state.

## Decision

**Detect-and-hold, never refocus.** Capture the foreground identity
(`target_id`) at **record-start** as an *anchor*, used purely for comparison — the
same primitive the [Trigger Fire](../../CONTEXT.md#trigger-fire) safety rail
already compares. At paste time:

- foreground **equals** the anchor → paste normally;
- foreground **changed** → **do not paste**. Retain the text in the
  [Most-recent dictation](../../CONTEXT.md#most-recent-dictation) buffer (which
  already exists and survives a landing-nowhere paste — ADR-0023) and show a quiet
  flash ("saved — say *paste*"), with **no error sound**. The user recovers it by
  focusing the right window and saying "paste" (or via the tray "Copy last
  dictation").

Dictatem **never programmatically restores or steals focus** on the regular-
dictation path. The anchor is a comparison token, not a command to move windows.

**The overlay encodes phase by colour, and stays informational.** Remove the
[Status Dot](../../CONTEXT.md#status-dot). The **pill colour** carries recording
phase: the live waveform in the accent colour while recording, a tinted processing
indicator while transcribing and while a [Transform](../../CONTEXT.md#transform)
computes, and the existing **text caption** while a model loads or downloads
([ADR-0016](0016-overlay-pill-model-loading-state.md) /
[ADR-0025](0025-cold-start-load-on-arm-fetch-on-first-run.md)). The pill exposes
**no interactive control** — it stays click-through.

**The two interlock.** The overlay stays informational *because* the paste guard
forbids focus-stealing. A genuinely clickable stop control would have to accept
mouse input, which makes the overlay focus-takeable — reintroducing exactly the
drift the detect-and-hold guard exists to prevent. [Esc](../../CONTEXT.md#hold)
cancels and a toggle [Tap](../../CONTEXT.md#tap) stops, so no click affordance is
needed; the dot's only real job was *state*, which the pill colour now carries.

## Considered options

- **Detect-and-hold, never refocus + pill-colour phase (chosen).** Reuses the
  cross-platform `target_id` rail, steals no focus, and turns a wrong-window
  misfire into a recoverable no-op.
- **Anchor and *restore* focus** — capture the target at record-start and
  `SetForegroundWindow` / `activateWithOptions_` it back before pasting. Rejected.
  `SetForegroundWindow` cannot reliably steal focus on Windows (it often just
  flashes the taskbar), and on macOS `restore` is **app-granular** and uses the
  **soft-deprecated** `activateWithOptions_(…IgnoringOtherApps)`
  ([ADR-0018](0018-cross-platform-input-and-foreground-neutral-identities.md)) —
  fragile and pushy on both platforms. Yanking the user's windows around reads as
  buggy; detection needs none of it (it only compares two ints).
- **Do nothing (status quo).** A wrong-window paste still happens before any
  recovery; the terminal hazard remains. Rejected.
- **Detect, warn, but paste anyway.** Still dumps text into the wrong window — the
  warning does not undo it. Rejected.
- **Play the error sound on a drift-hold.** Rejected (user call): a quiet flash is
  enough; a drift is not an error the user caused, so it should not sound like one.
- **A genuinely interactive stop button on the pill.** Breaks the click-through
  overlay and reintroduces focus-stealing (see the interlock); Esc/Tap already
  stop. Rejected.
- **Keep the Status Dot, just make it non-clickable.** The dot's only job was
  state, now carried by colour; keeping a dot that *looks* like a button invites
  the same dead click. Rejected.

## Consequences

- The paste pipeline gains a **record-start anchor** compared at paste time; the
  changed-target branch routes to the Most-recent dictation buffer + flash instead
  of pasting. The comparison is pure (unit-testable); the capture is the existing
  `ForegroundTracker` adapter. It catches **cross-window/app drift only** —
  *same-window caret loss* (anchor unchanged, but the caret moved on within the
  same window) is **out of scope** here; that is #93, and the buffer + "paste"
  recovery is its backstop.
- Cross-platform with **no Mac focus-restoration**: detection is window-granular on
  Windows (HWND) and app-granular on macOS (PID) — identical to the existing
  [Last Paste](../../CONTEXT.md#last-paste) / Trigger Fire rail.
- The [Overlay Pill](../../CONTEXT.md#overlay-pill) is redefined: phase by colour,
  **no Status Dot, no interactive control**. The Status Dot term is **retired**.
  This refines [ADR-0006](0006-tray-icon-is-static-brand-not-state.md) — the tray
  stays static brand (unchanged); recording state now lives in the pill colour, not
  a dot.
- The Tap/Hold **mode** cue the dot also carried (outline vs filled) is **dropped**:
  the user knows the gesture they just made. At most a subtle "tap to stop" *text*
  may remain for the toggle case — a build-time call, never a dot-like shape.
- A separate root-cause fix to do at the source: the pill currently lacks
  `WA_ShowWithoutActivating` / `WindowDoesNotAcceptFocus` (`overlay/qt_widget.py`),
  so *showing* it may itself momentarily steal activation — a plausible *cause* of
  drift that the anchor would otherwise paper over. Tracked as its **own issue**;
  making the pill provably never-activate complements (does not replace) the
  detect-and-hold guard.
