# Replacements are opt-in — Dictatem never silently autocorrects speech

> Introduces the [Replacement](../../CONTEXT.md#replacement) and
> [Vocabulary](../../CONTEXT.md#vocabulary) mechanisms and records a product
> stance the competitor scan put on the table.

Every competitor scanned (Wispr Flow, superwhisper) **silently auto-cleans**
dictation — removing filler words, fixing grammar — by default, in the cloud.
Dictatem is adding a local, deterministic [Replacement](../../CONTEXT.md#replacement)
mechanism (find/replace, empty-target deletes). The question this ADR settles:
do we ship default filler removal and clean speech automatically like everyone
else, or not?

## Decision

**Replacements are user-authored and opt-in. Dictatem does not alter dictated
words unless the user has enabled a rule.** The first-run `replacements.md` ships
with only **commented-out** examples (e.g. `# um =>`), so out of the box nothing
is changed. Removal of unambiguous fillers (`um`, `uh`, `er`) is available the
moment the user uncomments or adds a rule; ambiguous fillers (`like`,
`you know`, `actually`) are **never** offered as blind rules — they are real
words in context and would shred meaning.

This is grounded in a deliberate product direction surfaced during the grill:
**Dictatem aims to help users *speak* better, not just paste cleaner text.**
Silent autocorrect removes the user's awareness of their own filler use; an
opt-in model preserves agency and keeps the door open to a future
*filler-awareness / coaching* feature (surface that "um" usage is high rather
than hiding it). That coaching loop is **deferred and to be prototyped**, not
built blind — it risks sliding into the stats/gamification surface this project
already rejects, and the ambiguous-filler detection it needs is non-trivial.

## Considered options

- **Silent auto-cleanup by default** (match the competitors). Cleaner output with
  zero setup, but it removes user agency and awareness, contradicts the
  speech-aid direction, and — done deterministically — cannot safely touch the
  ambiguous fillers that matter most without an LLM. Rejected.
- **Ship active default filler-removal rules** (`um =>` enabled out of the box).
  A middle ground, but it still *silently* alters the user's words on first run,
  which is the behaviour we are deliberately rejecting. Rejected for
  commented-out examples.
- **LLM auto-cleanup on every dictation** (an Ollama pass like superwhisper's
  Message mode). Genuinely useful and local-capable, but adds per-dictation
  latency and trades away instant raw paste; parked for user feedback as a
  separate decision, not folded in here.
- **Build the coaching/feedback loop now.** The speech-aid payoff, but speculative
  ("not convinced yet"), surface-heavy, and dependent on ambiguous-filler
  detection. Deferred to a prototype.

## Consequences

- Dictatem now has **three clearly separated text-affecting mechanisms**, which
  the glossary keeps distinct: [Vocabulary](../../CONTEXT.md#vocabulary)
  (recognition bias, before text exists), [Replacement](../../CONTEXT.md#replacement)
  (deterministic substitution, after transcription), and
  [Transform](../../CONTEXT.md#transform) (an LLM operation invoked by a
  [Trigger Word](../../CONTEXT.md#trigger-word)).
- The default experience is "clean if you ask," not "clean by default" — a
  deliberate divergence from the category that a future contributor should not
  silently reverse by enabling default auto-cleanup.
- The speech-aid direction is recorded but unbuilt; the Replacement primitive
  (empty-target deletion) is the foundation a later filler-awareness feature
  builds on.
- Replacement and Vocabulary lists live in their own line-based `.md` files
  (parsed by small pure, unit-tested parsers), not in `config.toml` (avoids
  bloat) and not in `prompts/` (whose `*.md` glob builds the Trigger-Word map).
