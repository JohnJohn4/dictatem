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
always pass through. Because a lone **Alt** release activates the Windows menu bar
and a lone **Win** release pops the Start menu, releasing a Win+Alt-style chord
would otherwise misfire one of those and steal keyboard focus from the next
paste. So on Windows, when an Alt/Win key that was part of a Dictatem combo
session is released and nothing else was pressed while it was down, the keyboard
hook swallows that key-up and re-emits it behind the unassigned mask key `0xE8`.
Your own lone Alt or Win press, outside dictation, still works normally (#171,
#177). Dictatem tags every keystroke it injects, and the hook never feeds those
to the hotkey logic.

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
Word firing. It is cleared on cancel. It is distinct from the
[Most-recent dictation](#most-recent-dictation) below.

### Most-recent dictation

The exact payload of the most recent regular dictation — normalised and with
[Replacements](#replacement) applied, i.e. the text that was (or would have been)
pasted — held in daemon memory. Unlike [Last Paste](#last-paste) it is retained
across pastes and exists even when the dictation landed nowhere (no window
focused, or the focused control was not a text field), so it carries no
`target_id` and does not by itself arm [Trigger Words](#trigger-word). It is what
the **`paste`** [Trigger Word](#trigger-word) and the [Tray Icon](#tray-icon)
"Copy last dictation" item recover, which is how Dictatem guarantees a dictation
is **never lost**: if text lands nowhere, focus where it should go and say
"paste" (or copy it from the tray). It is also where a regular dictation is **held
instead of pasted** when the foreground **identity changed between record-start
and paste** — i.e. focus drifted during a load wait: rather than mispaste into the
wrong window, Dictatem keeps the text here with a quiet flash, and the same
recovery applies. See
[ADR-0023](docs/adr/0023-dictation-is-never-lost-clipboard-fallback.md) and
[ADR-0026](docs/adr/0026-focus-drift-holds-the-dictation-overlay-shows-phase-by-colour.md).

### Dictation Session

The state that belongs to **one** dictation, from record-start to its paste (or
its cancel): whether a transcription or a [Transform](#transform) result is still
outstanding, the pending replace count, the record-start foreground identity
(the focus-drift anchor), and the text waiting to paste. Each session has an
**epoch**, a monotonically increasing integer: starting a recording begins a new
session and bumps it; cancel and error recovery end the session, bump it again,
and clear the fields. Daemon-lifetime state — [Last Paste](#last-paste), the
[Most-recent dictation](#most-recent-dictation), model warm and preload flags —
is *not* part of a session; Last Paste in particular survives across them.

### Trigger Word

A single-word utterance that, instead of being pasted as dictation, invokes an
**action**. Two kinds exist: a [Transform](#transform) — an LLM operation on the
[Last Paste](#last-paste), declared by a [Prompt File](#prompt-file) — and a
**built-in action**, hard-coded in Dictatem, that needs no Prompt File and no
LLM. The only built-in action today is **`paste`**, which re-pastes the
[Most-recent dictation](#most-recent-dictation) into the current window (the
recovery for a dictation that landed nowhere). Built-in actions work regardless
of whether the [Transform](#transform) feature is enabled.

A transcription is recognised as a Trigger Word if, after stripping
whitespace and ASCII punctuation and lowercasing, it exactly matches a configured
[Alias](#alias) or a built-in action word. Failing that, a **short** utterance
(about ≤ 2.5 s of speech, ≤ 3 tokens) whose joined tokens *sound like* an Alias
— strong letter or phonetic-key similarity, an unambiguous winner, and no sign
the model was unsure — also fires it (fuzzy matching, ADR-0028): `"haste"` fires
`paste`, `"clean up"` fires `cleanup`. Aliases shorter than about 5 letters are
matched exactly only. An utterance whose first word is an exact Alias followed
by more words is always dictation — `"summarize this"` and `"paste it"` are
regular dictation; only the lone word fires. Fuzzy matching never alters
dictated text (ADR-0024), and `[trigger_words].fuzzy_matching = false` restores
exact-only matching. A user [Prompt File](#prompt-file) that re-uses a built-in
name (`paste`) or a built-in action [Alias](#alias) is shadowed by the built-in.
A short utterance that only *might* be a Trigger Word is [Borderline](#borderline).

### Borderline

The third outcome of [Trigger Word](#trigger-word) recognition, beside
dictation and a fire: the short utterance sounds *close to* a Trigger Word but
Dictatem isn't sure — a weak fuzzy match, a strong match the model was
unconfident about, or a near-tie between two different actions. Its
**candidates** are the near-miss actions. Before giving up, Dictatem runs one
[Confirm pass](#confirm-pass). If that doesn't settle it, the Borderline outcome **pastes
nothing**: the [Overlay Pill](#overlay-pill) flashes a distinct **"say again"**
colour, and the [Most-recent dictation](#most-recent-dictation) and [Last
Paste](#last-paste) are left untouched, so saying `paste` (or the intended
Trigger Word) again still acts on the right text. The next utterance is judged
fresh. A genuine one-word dictation that trips it ("Summer.") is dictated inside
a longer phrase instead. See ADR-0028.

### Confirm pass

The single extra listen a [Borderline](#borderline) gets before the "say again"
flash: the same short audio is re-transcribed once, biased toward the lexicon's
[Trigger Words](#trigger-word) and with VAD off. If it is an exact or strong,
confident match for one of the Borderline's candidate actions (any of its
[Aliases](#alias)), that Trigger Word fires as normal, rails included. Anything
else (another action, another Borderline, dictation, empty) ends in "say again".
The pill stays "transcribing" meanwhile and Esc discards it like any in-flight
transcription. A broken model (load failure, GPU out of memory after retry)
is reported the same way as on the first pass, not hidden behind "say again".
Regular dictation never gets a confirm pass. See ADR-0028.

### Alias

One of the strings that map to a [Transform](#transform). Each Transform
has one or more Aliases. Aliases handle spelling variants (UK `"summarise"`
vs US `"summarize"`) and any other surface forms the user expects to work.

Aliases are declared in the YAML-style frontmatter of a [Prompt File](#prompt-file)
and are the single source of truth for matching. The prompt filename is
purely a human convenience and has no runtime meaning.

The built-in `paste` action can have Aliases too — **built-in action aliases**,
declared by the user in `[trigger_words].paste_aliases` (normalised the same
way), so a mishearing their voice consistently produces maps straight to
`paste`. They behave exactly like the built-in word: exact and fuzzy matching,
no Transform feature or [Last Paste](#last-paste) needed, and they shadow a
same-named Prompt File Alias (warned at startup).

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
flash on the overlay. The same-target rail is checked **twice** — before the
Transform runs and again at paste time, because the Transform can take up to
`[transform].model_timeout_s` and focus may drift during it; a mismatch at
either point discards the fire so backspaces never land in the wrong window.

Replacement is done by sending one backspace per
[Backspace Unit](#backspace-unit) of the Last Paste (post-normalisation, which
includes NFC composition) and pasting the Transform output. The
Transform output then itself becomes the new [Last Paste](#last-paste),
which allows trigger words to compose (e.g. running `"summarize"` twice
further condenses the result).

### Backspace Unit

One user-perceived character of pasted text — an extended grapheme cluster
(UAX #29), not a code point. A skin-toned emoji, a family ZWJ sequence, a flag,
a keycap or an accented letter is one Backspace Unit, matching what one
Backspace deletes in a text field. The [Last Paste](#last-paste) records its
length in Backspace Units so a [Trigger Fire](#trigger-fire) erases exactly what
was pasted. Counted by a stdlib-only approximation of UAX #29
(`dictatem.paste.backspace_units`), not the `regex` package.

### Vocabulary

User-supplied terms — names, jargon, acronyms, non-English words — that **bias
transcription recognition** toward those spellings. Declared one per line in
`~/.dictatem/vocabulary.md`. The terms are fed to the transcription model as
recognition hints: they influence how audio is *heard*, and do not by themselves
rewrite the transcribed text (contrast [Replacement](#replacement)). Keeping the
list focused matters — an over-long list can degrade recognition.

### Preferred Languages

The small set of languages a user dictates in, declared as
`[model].languages = ["en", "zh"]` (#273). When set, the transcription language
of each clip is **detected only among them** (Whisper's per-language
probabilities restricted to the set and renormalised); it takes precedence over
`[model].language`. Detection is **sure or fall back**: a clip with too little
speech (under 1.5 s) is never detected, and a winner below the confidence
threshold (0.6) is not trusted, so the clip uses the **fallback language**: the
last language confidently detected this session if allowed, else the first
Preferred Language (else, for `language = "auto"`, the OS display language, else
English). Without Preferred Languages or `language`, Dictatem transcribes in
English with no detection. The decision is pure (`dictatem.transcribe.language`);
the engines only gather probabilities. The [Confirm pass](#confirm-pass) reuses
the language of the pass it re-checks.

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

### Clutter-proof clipboard write

A clipboard write Dictatem tags so it pastes normally with Ctrl+V but leaves no
trace: the Windows markers `CanIncludeInClipboardHistory` and
`CanUploadToCloudClipboard` (both DWORD `0`) exclude it from the Win+V clipboard
**history** and from **cloud-clipboard** sync. Regular dictation pastes via the
clipboard + Ctrl+V (see
[ADR-0004](docs/adr/0004-trigger-fire-types-via-sendinput-not-clipboard.md)),
saving and restoring the user's original around the transient write; **both** the
transient write and the restore are clutter-proof, so the automatic juggling
never piles entries into Win+V or syncs the dictation off-device. (An explicit
[Tray Icon](#tray-icon) "Copy last dictation" is a *normal* copy — the user
deliberately asked for it on the clipboard.) [Trigger Fire](#trigger-fire) never
touches the clipboard at all (it types via `SendInput`), so this concerns only
the regular-dictation path. See
[ADR-0023](docs/adr/0023-dictation-is-never-lost-clipboard-fallback.md).

### Clipboard Snapshot

The opaque saved copy of the user's clipboard that the regular-dictation paste
takes before borrowing the clipboard and writes back afterwards (a
[clutter-proof](#clutter-proof-clipboard-write) restore). It holds every format
that could be safely captured, as raw bytes in the clipboard's own order —
images, file copies, HTML, rich text and plain text — and nothing between `save`
and `restore` (the paste pipeline, the deferred restore) looks inside it. An
empty clipboard gives an empty snapshot, which restores to an empty clipboard.

Which formats a snapshot takes is the **Clipboard Capture Plan**, a pure
decision over the formats on offer (id, name, kind, size): only memory-backed
formats are captured; handle-based, OS-synthesized, and owner-drawn or
delayed-render formats are skipped; and the total is held to a fixed size cap.
Over the cap — or if a format could not be measured in time — only the text is
kept and a warning names the formats and their sizes, never their content.
Windows ships full-format snapshots (#243). On macOS (#244) the snapshot is
every pasteboard item's types — legacy aliases and file promises skipped — and
restore rebuilds the same items in order; it awaits real-Mac QA.

## UI surfaces

### Overlay Pill

The transient, **informational** floating indicator shown in a corner of the
active monitor while dictation is active. It is the user's primary at-a-glance
feedback during a recording and carries **no interactive control** — it is
click-through; a recording is stopped with [Esc](#hold) or a toggle [Tap](#tap),
not by clicking the pill. It also **never takes focus or steals activation** when
shown, so raising it never deactivates the user's window or caret — the property
that lets it stay purely informational (it is *because* the pill grabs no focus
that no clickable stop control is offered).

The pill encodes recording **phase by colour**: a live waveform in the accent
colour while recording, a distinct processing colour while transcribing, and a
*further* distinct colour while a [Transform](#transform) computes (a warm LLM
generating). (This replaces the former [Status Dot](#status-dot); see
[ADR-0026](docs/adr/0026-focus-drift-holds-the-dictation-overlay-shows-phase-by-colour.md).)

When a regular dictation is **held** in the [Most-recent
dictation](#most-recent-dictation) buffer instead of pasted — the focus-drift
hold, or a paste that failed — the pill shows its own quiet **"Saved — say
paste"** signal: a distinct Held colour with that caption, for about a second and
a half, silent and never refocusing anything. It is *not* the error flash; the
error flash is kept for genuine failures where nothing is held (an empty result,
a discarded [Trigger Fire](#trigger-fire), "paste" with nothing to recover, a
transcription error).

A [Borderline](#borderline) Trigger Word gets its own **"say again"** flash: the
error flash's timing in a distinct colour — nothing broke and nothing was lost,
the user just repeats the command.

While a model is still loading or downloading — the first dictation's Whisper
load, the first [Trigger Word](#trigger-word)'s LLM load, a tray **Preload**, or
the one-time first-run model **download** — the pill instead shows a text caption
naming what is happening ("Loading Dict. Model", "Loading LLM Model", "Preloading
Models", or "Downloading model…") with dots cycling 1→2→3 and no waveform,
flipping to the recording-phase colour once the model is resident. When the LLM is
already resident, a [Trigger Word](#trigger-word) instead shows the **computing
colour** while it generates (no caption — a warm generation is a *phase*, not a
load; ADR-0026 refines ADR-0016's former "LLM Model Computing" caption to a
colour). See
[ADR-0016](docs/adr/0016-overlay-pill-model-loading-state.md) and
[ADR-0025](docs/adr/0025-cold-start-load-on-arm-fetch-on-first-run.md).

### Busy Nudge

The [Overlay Pill](#overlay-pill)'s brief acknowledgement of a hotkey press made
while Dictatem is already working (transcribing, computing a
[Transform](#transform), or loading a model): the pill shows "Still working —
Esc cancels" over the current phase colour for about a second and a half, then
reverts on its own. The press is never acted on — it does not start, stop or
queue anything — so a worried second press can't double a dictation (#240).

### Status Dot

**Retired.** The dot on the [Overlay Pill](#overlay-pill) formerly signalled
recording phase (red recording / amber transcribing) and mode (an outline dot for
a push-to-talk [Hold](#hold), a filled dot for a toggle [Tap](#tap)). It read as a
stop *button* it was not, and competed with the waveform — so recording **phase**
now lives in the pill's **colour**, the dot is removed, and the Tap/Hold **mode**
cue is dropped (the user knows the gesture they just made). See
[ADR-0026](docs/adr/0026-focus-drift-holds-the-dictation-overlay-shows-phase-by-colour.md).

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

On a Mac, Apple Silicon on macOS 14+ with the Apple GPU engine installed gets
the **Apple-GPU** Tier (`large-v3-turbo` on the GPU). With less unified memory
it gets **Apple-GPU-low** (`small` on the GPU). Apple Silicon without the GPU
engine gets the **Apple-Silicon** Tier (`small` on CPU), and an Intel Mac gets
the CPU Tier. If the Apple GPU can't be used, Dictatem runs that session on CPU
and leaves the config untouched (see
[ADR-0013](docs/adr/0013-macos-transcription-engine.md) and
[ADR-0009](docs/adr/0009-hardware-mismatch-falls-back-for-the-session.md)).

Resolving a Tier also yields a tier-appropriate default [Transform](#transform)
(Ollama) model tag, written into a fresh config. Beyond that suggestion the
Transform model is not Dictatem's to manage: Ollama is a separate, user-managed
process Dictatem only talks to — never installs, pulls, or runs on the user's
behalf (see [ADR-0008](docs/adr/0008-dictatem-does-not-manage-ollama-lifecycle.md)).

### Engine Prewarm

Loading the transcription engine's DLLs once in a short-lived, low-priority
background process, with **no model and no GPU memory**. On machines whose
security software scans each new file (e.g. Defender for Endpoint), this moves
a one-off delay of minutes off the first dictation. `install.ps1` runs it before
the first launch ("Preparing the speech engine…"), and the daemon repeats it a
second after each launch (seconds when warm). Windows only;
`[startup] prewarm_engine`. See
[ADR-0029](docs/adr/0029-engine-prewarm-in-a-child-process.md).

### Resident Engine

On a machine where an [Engine Prewarm](#engine-prewarm) ever took ≥ 20 s
(recorded in `~/.dictatem/.slow_engine_load`), Dictatem keeps the engine (not
the model, no GPU memory) loaded in its own process after launch. Those
scanners' verdicts expire after a gap, and this stops the first dictation after
a break from re-paying the scan: ~14.5 s → ~3 s on the work laptop. Costs about
230 MB of idle RAM, on those machines only. `[startup] resident_engine =
"auto" | "on" | "off"`. Distinct from `preload_model`, which loads the model
itself.

## Configuration

### Config Load Report

The list of problems found while loading `config.toml`: an unreadable or
unparseable file (with the parser's message and position), or a key with the
wrong type or an invalid value (which falls back to its default). The daemon
turns a non-empty report into exactly one startup tray notification, a short
summary that fits a Windows toast; the full detail goes to the log. Any
problem makes the config **read-only for the session**: Dictatem writes
nothing, not even the Start-at-login toggle (which then applies for the
session only). An unreadable file also runs the session on the
[Hardware Tier](#hardware-tier) defaults. Unknown keys and sections
are not problems; they stay info-only in the log. Dictatem never rewrites the
file to "fix" it (ADR-0009 / ADR-0022).

## Flagged ambiguities

- "the icon that changes colour" was used to mean both the **Tray Icon** and
  the **Status Dot**. Resolved: they are separate surfaces driven by separate
  state. The **Status Dot** carries recording state; the **Tray Icon** is
  static brand identity.
- "use a smaller model for summarise" conflated two independent model axes: the
  **Hardware Tier**'s Whisper model (transcription, bundled) and the
  **Transform** model (Ollama, separate install). Resolved: they are selected
  and managed separately.
