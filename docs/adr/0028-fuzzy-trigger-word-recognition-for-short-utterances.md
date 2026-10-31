# Fuzzy Trigger Word recognition, only for short utterances

> Spec #226 (Trigger Word recognition), first slice #247. Updates the match
> rule in [Trigger Word](../../CONTEXT.md#trigger-word).

Whisper decodes a lone word with no language context, so a quick "paste" is
often heard as "haste" and "polish" as "palish". Exact-only matching then types
the wrong word into the user's document, and that word becomes the next Most-
recent dictation and Last Paste. The question: may Dictatem treat a word that
*sounds like* a Trigger Word as that Trigger Word, and if so, how?

## Decision

**A short utterance that sounds like an Alias fires that Trigger Word.** The
recognizer adds a fuzzy tier behind the unchanged exact rule:

- **Gate.** Fuzzy only runs on about ≤ 2.5 s of speech and ≤ 3 tokens, and never
  when the first token is an exact Alias followed by more words ("summarize
  this", "paste it" stay dictation). Longer speech is never a Trigger Word.
- **Score.** Join the tokens ("clean up" → "cleanup") and take the better of
  the letter edit similarity and the edit similarity of a small metaphone-style
  phonetic key. A strong match fires; a weak match is Borderline (below);
  anything weaker is dictation. Aliases
  shorter than about 5 letters are matched exactly only. A near-tie between
  different actions never fires; it is Borderline.
- **Confidence guardrail.** A strong fuzzy match fires only when Whisper's own
  conventional thresholds hold (`avg_logprob` ≥ −1.0, `no_speech_prob` < 0.6) or
  the backend can't report confidence; otherwise it is Borderline. Confidence
  never blocks an exact match
  and never fires anything on its own (hallucinations can be confident).
- **Same rails.** A fuzzy fire is an ordinary Fire: an unarmed Transform is
  never a candidate, and a Transform passes the same-target and TTL rails,
  both before the LLM call and at paste time.
- **It never rewrites dictation (ADR-0024).** Fuzzy matching only answers "is
  this utterance a Trigger Word". Text that isn't one is pasted exactly as
  transcribed; Replacements and Vocabulary are untouched.
- **Pure Python, no new dependency.** An in-repo Levenshtein and phonetic key
  (`transform/phonetic.py`), pinned by the recognizer's golden-table tests.
- **Escape hatch.** `[trigger_words].fuzzy_matching = false` restores exact-only
  matching. The section is hand-edited (ADR-0022) and follows a "commented
  while default, live once changed" serialisation rule (`_COMMENTED_WHEN_DEFAULT`
  in `config.py`): whenever Dictatem writes the config, `[trigger_words]` is
  written commented out while it still equals its defaults (discoverable, but
  never pinned by the app), and written live once the user has changed it.
  The reason is the app's own config rewrites, such as the Start-at-login
  toggle: they serialise the loaded config, so a section that was always
  written commented would silently revert a user's hand edit, and one always
  written live would pin today's defaults into every config.

**Borderline pastes nothing (#248).** A weak match, an unconfident strong match
or a cross-action tie is a third outcome, [Borderline](../../CONTEXT.md#borderline):
nothing is pasted or typed, the pill flashes a distinct "say again" colour (the
error flash's timing, not its coral), and the Most-recent dictation and Last
Paste are left untouched. This is a deliberate, visible exception to "paste what
was heard", limited to ≤ 3-token near-homophones of a Trigger Word inside the
short-utterance gate. Pasting instead re-creates the original bug: "haste"
lands in the document, becomes the Most-recent dictation, and the user's next
"paste" re-pastes "haste". It squares with ADR-0023's never-lost guarantee
because nothing the user *dictated* is dropped: the buffer still holds the
previous dictation, and the Borderline utterance was, by construction, a
near-miss of a command rather than content. The cost is that a genuine one-word
dictation such as "Summer." is swallowed; the Usage Guide and README tell the
user to say it inside a longer phrase. A command-biased confirm pass (#249) runs
before the flash, so most Borderlines resolve without a repeat.

**A Borderline gets one command-biased confirm pass (#249).** Before the
say-again flash, the daemon re-transcribes the same short audio once with a
one-off command bias: a sentence-like `initial_prompt` naming the lexicon's
Trigger Words ("Summarize. Paste.") plus `hotwords` where the installed
faster-whisper supports them. The recognizer fires only if that pass is an
exact or strong-confident match for the *same action* as one of the Borderline
candidates (any Alias of it). A match for a different action, another
Borderline, dictation, or an unexpected error all end in say-again, as before.
A model-load failure or a GPU out-of-memory error (after the usual retry) is
surfaced exactly as on the first pass (tray notification, back to idle):
"say again" would hide a broken model behind a prompt to repeat a command
that can never work. The pill
stays "transcribing" and Esc discards the pass like any in-flight
transcription. The persistent Vocabulary hint is not applied to this pass, and
regular dictation is never biased.

- **Two passes, not global biasing.** Biasing only the confirm pass keeps the
  lexicon's real words ("paste", "polish", "summarize") from leaking into
  regular dictation. The cost is a second decode, but only on the rare
  Borderline and only of a ≤ 2.5 s clip.
- **The confirm pass bypasses VAD (review §6.3).** The question was whether
  first-pass VAD clips a quick command's onset ("summarise" → "some of us"). We
  keep first-pass VAD unchanged, since it guards dictation against silence
  hallucinations, and run the confirm pass with `vad_filter=False` so a clipped
  onset can't be trimmed again. The confirm utterance is judged against the
  first pass's post-VAD speech duration, because the VAD-off pass reports the
  whole recording.

**Load-time collision warnings use a cautious "within fuzzy range" bound
(#251).** At startup Dictatem warns about two Aliases of different actions
that sound alike (spec #226 Layer 4: an Alias that "sits within fuzzy range
of" another), and about each Alias too short for fuzzy tolerance. Two Aliases
are paired when they are equal, when their phonetic keys are equal, or, only
if both are long enough for fuzzy matching, when the better of their spelling
and phonetic-key similarity is at least 0.60 (`COLLISION_SCORE`). An
exact-only Alias never fires on a near-miss, so it is only paired on an
identical sound. The 0.60 bound is a heuristic, not a derived guarantee: it
sits deliberately below the recognizer's weak band (0.70) so that pairs a
mishearing could carry from one to the other are flagged. "palace" /
"polish" scores only 0.67 on phonetic keys yet is exactly the pair a user
should hear about. A false warning costs a log line; a missed one costs a
wrong Trigger Fire.

Thresholds are module constants, not config, and tests assert decisions only,
so they stay tunable.

## Considered options

- **RapidFuzz + jellyfish.** Both ship wheels for every target, but jellyfish
  has no Double Metaphone, and plain metaphone equality misses the flagship
  case (`someofus` → SMFS vs `summarise` → SMRS); edit distance over the key is
  what works, and that is a few lines. With a lexicon of ~20 Aliases a native
  extension buys nothing and adds install surface (ADR-0011, Windows-on-ARM
  under x64 emulation). Rejected.
- **Bias every transcription toward the lexicon** (`hotwords`/`initial_prompt`).
  Nudges all regular dictation toward "paste"/"polish"/"summarize", which are
  real words. Rejected; spec #226 adds a targeted confirm pass instead (#249).
- **Turn VAD off for every short recording.** Would answer §6.3 for the first
  pass too, but gives up VAD's protection against silence hallucinations on
  every brief dictation. Rejected in favour of a VAD-off confirm pass only.
- **Let users add mishearings as Aliases.** Doesn't scale, and `paste` had no
  Alias mechanism. Kept as a complement (`paste_aliases`, #250), not the fix.

## Consequences

- A lone "Taste." / "Waste." / "Past." fires `paste`, which re-pastes the
  Most-recent dictation; Ctrl+Z recovers it. Accepted.
- Weak matches, unconfident strong matches and cross-action ties show the "say
  again" flash and paste nothing (#248); a command-biased confirm pass (#249)
  gets one more listen first.
- A genuine single-word dictation that sounds like a Trigger Word ("Summer.")
  needs a longer phrase. Accepted.
