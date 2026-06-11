# Context

Glossary of domain terms used in Dictatem. Implementation details belong in
the code or in ADRs (`docs/adr/`), not here.

## Terms

### Tap

A press-and-release of the [Hotkey Combo](#hotkey-combo) whose total held
duration is shorter than the **tap threshold** (default 200 ms, configurable
via `[hotkey].tap_threshold_ms`). A Tap toggles recording on and off:
the first Tap starts recording, the next Tap stops it and transcribes.

Discriminating a Tap from a [Hold](#hold) requires that every timestamp
in the hotkey pipeline come from the same clock; see
[ADR-0005](docs/adr/0005-hotkey-uses-time-monotonic-end-to-end.md).

### Hold

A press of the [Hotkey Combo](#hotkey-combo) held continuously for at least
the **tap threshold**. While the combo is held, recording runs in
push-to-talk mode and stops on release.

### Hotkey Combo

The set of **trigger inputs** — modifier keys and/or a single mouse button —
that, pressed together, arm dictation. Configured by name via
`[hotkey].modifiers` (default `["win", "alt"]`; the field name is kept for
back-compat even though the set may now include a mouse button) and matched
against **platform-neutral identities**, so the same configuration means the
same thing on every OS while each platform maps its own physical keys and
buttons:

| Modifier name | Identity | Windows key | macOS key |
| --- | --- | --- | --- |
| `meta` (alias `win`) | Meta | Windows key | Command (⌘) |
| `alt` | Alt | Alt | Option (⌥) |
| `ctrl` | Ctrl | Ctrl | Control |
| `shift` | Shift | Shift | Shift |

A trigger input may also be a single **mouse button**: `mouse4` or `mouse5`
(the two side buttons) or `middle` (the wheel click). Left and right click are
never available — they are primary interaction. A mouse button may be used
**standalone** (`["mouse4"]`) or **combined** with modifiers
(`["ctrl", "mouse4"]`).

The configurable vocabulary is a **curated allow-list**: only the names above
are accepted; anything else is rejected on load and falls back to the default.
Dictatem has no free-form key binding and no settings UI — the combo is
opinionated by default and configurable only as an escape hatch
(discoverability over configurability).

While a mouse button is actively completing the combo it is **suppressed** — it
does not also fire its usual action (e.g. browser-back) — whereas modifier keys
always pass through.

`meta` is the canonical cross-platform name for the OS key; `win` is a
permanent alias kept for existing Windows configs. The default combo is
therefore Win+Alt on Windows and Option+Command on macOS. The keyboard and
mouse hooks on each platform translate native codes into these identities; the
[Tap](#tap)/[Hold](#hold) classifier reasons only about identities and never
sees a raw OS code. See
[ADR-0010](docs/adr/0010-hotkey-modifiers-are-configurable.md) and
[ADR-0020](docs/adr/0020-mouse-buttons-are-trigger-inputs.md).

### Last Paste

The snapshot of the text most recently pasted by Dictatem into the user's
focused window, together with the **foreground identity** (`target_id`) at the
time of the paste and a monotonic timestamp. The `target_id` is an opaque
integer the [Trigger Fire](#trigger-fire) rail compares for equality — a window
handle (HWND) on Windows, the frontmost-app process id (PID) on macOS. It is
therefore window-granular on Windows but **app-granular on macOS**: a Trigger
Fire after switching to a different window of the *same* macOS app still passes
the same-target rail.

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
identity (`target_id`) still matches the one captured when the
[Last Paste](#last-paste) was made, and the Last Paste is younger than its TTL
(default 5 min, configurable via `[transform].last_paste_ttl_s`). The match is
window-granular on Windows and app-granular on macOS (see
[Last Paste](#last-paste)). Otherwise the trigger is discarded with an error
flash on the overlay.

Replacement is done by sending backspaces equal to the character length of
the Last Paste (post-normalisation) and pasting the Transform output. The
Transform output then itself becomes the new [Last Paste](#last-paste),
which allows trigger words to compose (e.g. running `"summarize"` twice
further condenses the result).

### Vocabulary

User-supplied terms — names, jargon, acronyms, non-English words — that **bias
transcription recognition** toward those spellings. Declared one per line in
`~/.dictatem/vocabulary.md`. The terms are fed to the transcription model as
recognition hints: they influence how audio is *heard*, and do not by themselves
rewrite the transcribed text (contrast [Replacement](#replacement)). Keeping the
list focused matters — an over-long list can degrade recognition.

### Replacement

A **deterministic, post-transcription substitution** applied to regular
dictation before it is pasted: each rule rewrites a matched source string to a
target, matched **case-insensitively on whole words**. Declared one per line as
`source => target` in `~/.dictatem/replacements.md`; an **empty target deletes**
the match and collapses the surrounding whitespace, which is the literal-minded
way to drop unambiguous filler words (`um`, `uh`). Replacements never involve the
LLM, distinguishing them from a [Transform](#transform) (an LLM operation invoked
by a [Trigger Word](#trigger-word)).

Dictatem does **not** silently clean up speech by default: the shipped
`replacements.md` carries only commented-out examples, so words are altered only
by rules the user has consciously enabled. Ambiguous fillers (`like`,
`you know`) are deliberately *not* removed this way — they are real words in
context and need LLM judgement, not a blind rule. See
[ADR-0024](docs/adr/0024-replacements-are-opt-in-no-silent-autocorrect.md).

### Clipboard Fallback

A dictation is **never silently lost**. Dictatem types transcribed text into the
focused window via keystrokes — it does not paste through the clipboard (see
[ADR-0004](docs/adr/0004-trigger-fire-types-via-sendinput-not-clipboard.md)) —
but when there is **no foreground target** to type into, the text is placed on
the **clipboard** instead and the [Overlay Pill](#overlay-pill) shows a brief
notice, so the user can paste it where they meant to. The most recent dictation
can also be copied on demand from the [Tray Icon](#tray-icon) menu
("Copy last dictation").

Dictatem deliberately does **not** detect whether the focused control is
editable: typing blind is what lets it work in every application without per-app
knowledge. The automatic fallback therefore fires only on the cheaply-known
"no foreground window" case; for the rarer "focused, but not a text field" case,
the on-demand copy is the recovery. See
[ADR-0023](docs/adr/0023-dictation-is-never-lost-clipboard-fallback.md).

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
When the LLM is already resident, a [Trigger Word](#trigger-word) instead shows
"LLM Model Computing" while it generates — the same pill with an accurate verb.
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

### Usage Guide

The read-only, in-app help window opened from the [Tray Icon](#tray-icon)
menu's "How to use Dictatem…" item. It teaches the critical workflows —
dictating ([Tap](#tap) vs [Hold](#hold)), [Trigger Words](#trigger-word), and
first-use model loading — and reflects the **live configuration**: the actual
[Hotkey Combo](#hotkey-combo) and the user's configured
[Trigger Words](#trigger-word), not static examples. It carries no controls; it
grows by appending a section as each feature lands, so there is one place to
learn Dictatem rather than a help item per feature.

It also **auto-opens once the first time Dictatem runs** (after any first-run
permission flow has settled), so a new user meets it without hunting through the
tray menu; thereafter it opens only on demand. Because it reflects live config
and is the single place usage is taught, it is also where the user learns to
**change the [Hotkey Combo](#hotkey-combo)** — Dictatem has no settings UI (see
[ADR-0011](docs/adr/0011-install-via-thin-uv-tool-script.md)).

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
