# Context

Glossary of domain terms used in Dictatem. Implementation details belong in
the code or in ADRs (`docs/adr/`), not here.

## Terms

### Tap

A press-and-release of the hotkey combo (Alt+Win) whose total held
duration is shorter than the **tap threshold** (default 200 ms, configurable
via `[hotkey].tap_threshold_ms`). A Tap toggles recording on and off:
the first Tap starts recording, the next Tap stops it and transcribes.

Discriminating a Tap from a [Hold](#hold) requires that every timestamp
in the hotkey pipeline come from the same clock; see
[ADR-0005](docs/adr/0005-hotkey-uses-time-monotonic-end-to-end.md).

### Hold

A press of the hotkey combo (Alt+Win) held continuously for at least
the **tap threshold**. While the combo is held, recording runs in
push-to-talk mode and stops on release.

### Last Paste

The snapshot of the text most recently pasted by Dictatem into the user's
focused window, together with the foreground window handle (HWND) at the
time of the paste and a monotonic timestamp.

The **Last Paste** is the operand for [Trigger Words](#trigger-word). It is
updated after every paste — both from regular dictation and from a Trigger
Word firing. It is cleared on cancel.

### Trigger Word

A single-word utterance that, instead of being pasted as dictation, invokes
a [Transform](#transform) on the [Last Paste](#last-paste).

A transcription is recognised as a Trigger Word if, after stripping
whitespace and ASCII punctuation and lowercasing, it exactly matches one of
the configured [Aliases](#alias). Multi-token utterances never match —
`"summarize this"` is regular dictation, only the lone word `"summarize"`
(or its [Aliases](#alias)) fires.

### Alias

One of the strings that map to a [Transform](#transform). Each Transform
has one or more Aliases. Aliases handle spelling variants (UK `"summarise"`
vs US `"summarize"`) and any other surface forms the user expects to work.

Aliases are declared in the YAML-style frontmatter of a [Prompt File](#prompt-file)
and are the single source of truth for matching. The prompt filename is
purely a human convenience and has no runtime meaning.

### Prompt File

A markdown file under `~/.dictatem/prompts/` that declares one
[Transform](#transform). Each file has a frontmatter block (declaring
[Aliases](#alias)) and a body (the system prompt sent to the LLM).

The daemon globs every `*.md` in this folder at startup and builds a flat
map from each alias to its prompt body.

### Transform

A pure-text operation: input is the current [Last Paste](#last-paste) text,
output is new text destined to replace it. Each [Trigger Word](#trigger-word)
maps to exactly one Transform, declared by a single [Prompt File](#prompt-file).

Transforms are currently implemented by calling a locally-hosted LLM
(Ollama) with the prompt body from the matched [Prompt File](#prompt-file)
as the system prompt and the [Last Paste](#last-paste) text as the user
prompt.

### Trigger Fire

The act of running a [Transform](#transform) on the [Last Paste](#last-paste)
and replacing the previously-pasted text with the result.

A Trigger Fire only proceeds if both safety rails hold: the foreground
window still has the same HWND as when the Last Paste was made, and the
Last Paste is younger than its TTL (default 5 min, configurable via
`[transform].last_paste_ttl_s`). Otherwise the trigger is discarded with
an error flash on the overlay.

Replacement is done by sending backspaces equal to the character length of
the Last Paste (post-normalisation) and pasting the Transform output. The
Transform output then itself becomes the new [Last Paste](#last-paste),
which allows trigger words to compose (e.g. running `"summarize"` twice
further condenses the result).

## UI surfaces

### Overlay Pill

The transient floating indicator shown in a corner of the active monitor
while dictation is active. It carries the [Status Dot](#status-dot) and a
live waveform. It is the user's primary at-a-glance feedback during a
recording.

While a model is still loading — the first dictation's Whisper load, the first
[Trigger Word](#trigger-word)'s LLM load, or a tray **Preload** — the pill
instead shows a loading caption naming what is loading ("Loading Dict. Model",
"Loading LLM Model", or "Preloading Models") with dots cycling 1→2→3 and no
waveform, flipping to the [Status Dot](#status-dot) once the model is resident.
See [ADR-0016](docs/adr/0016-overlay-pill-model-loading-state.md).

### Status Dot

The dot on the [Overlay Pill](#overlay-pill) that signals recording phase
(red while recording, amber while transcribing) and recording mode (an
outline dot for a push-to-talk [Hold](#hold), a filled dot for a toggle
[Tap](#tap)). The Status Dot is where Dictatem communicates recording
**state**.

### Tray Icon

The system notification-area (system tray) icon. It carries the app's brand
identity and is **independent of the [Status Dot](#status-dot)**: it does not
encode recording state. Swapping the Tray Icon has no effect on the Status
Dot, and vice versa.

## Hardware

### Hardware Tier

The capability-matched bundle of transcription model, compute device, and
compute type Dictatem runs on a given machine — e.g. `large-v3-turbo` / CUDA /
float16 on a 16 GB GPU, down to `base` / CPU / int8 on a modest laptop. A Tier
is chosen from detected hardware on first run and baked into config; any value
the user pins always overrides the chosen one. `base` is the smallest Tier ever
chosen automatically; `tiny` is never auto-selected and models stay
multilingual. See [ADR-0007](docs/adr/0007-hardware-tier-resolved-on-first-run.md).

Resolving a Tier also yields a tier-appropriate default [Transform](#transform)
(Ollama) model tag, written into a fresh config. Beyond that suggestion the
Transform model is not Dictatem's to manage: Ollama is a separate, user-managed
process Dictatem only talks to — never installs, pulls, or runs on the user's
behalf (see [ADR-0008](docs/adr/0008-dictatem-does-not-manage-ollama-lifecycle.md)).

## Flagged ambiguities

- "the icon that changes colour" was used to mean both the **Tray Icon** and
  the **Status Dot**. Resolved: they are separate surfaces driven by separate
  state. The **Status Dot** carries recording state; the **Tray Icon** is
  static brand identity.
- "use a smaller model for summarise" conflated two independent model axes: the
  **Hardware Tier**'s Whisper model (transcription, bundled) and the
  **Transform** model (Ollama, separate install). Resolved: they are selected
  and managed separately.
