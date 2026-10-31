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
  phonetic key. A strong match fires; anything weaker is dictation. Aliases
  shorter than about 5 letters are matched exactly only. A near-tie between
  different actions never fires.
- **Confidence guardrail.** A strong fuzzy match fires only when Whisper's own
  conventional thresholds hold (`avg_logprob` ≥ −1.0, `no_speech_prob` < 0.6) or
  the backend can't report confidence. Confidence never blocks an exact match
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
  matching. The section is hand-edited and appears commented in the first-run
  config (ADR-0022).

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
- **Let users add mishearings as Aliases.** Doesn't scale, and `paste` had no
  Alias mechanism. Kept as a complement (`paste_aliases`, #250), not the fix.

## Consequences

- A lone "Taste." / "Waste." / "Past." fires `paste`, which re-pastes the
  Most-recent dictation; Ctrl+Z recovers it. Accepted.
- Weak matches, unconfident strong matches and cross-action ties are dictation
  in this slice. The Borderline outcome (#248) turns them into a "say again"
  flash plus a command-biased confirm pass (#249), and is recorded there.
