# Dictatem talks to Ollama but does not manage its lifecycle

The [Transform](../../CONTEXT.md#transform) feature calls a local Ollama server
over HTTP. Dictatem deliberately **does not** install Ollama, start it
(`ollama serve`), or pull models on the user's behalf. When a
[Trigger Fire](../../CONTEXT.md#trigger-fire) fails because Ollama isn't ready,
Dictatem diagnoses *why* and tells the user the exact manual step to take,
distinguishing three cases:

- **not installed** — no `ollama` binary on PATH → point to the README setup.
- **not running** — connection refused / transport error reaching the server →
  start Ollama, then try again.
- **model missing** — HTTP 404 from `/api/generate` → name the configured model
  and the `ollama pull <model>` command.

The diagnosis is a pure classifier fed structured failure signals; the single OS
touch (probing PATH for the binary) is injected so the classifier stays pure and
unit-tested.

## Considered options

- **Auto-install / auto-`serve` / auto-`pull`.** Convenient, but pulls Dictatem
  into owning a second heavyweight runtime's install, version, GPU-memory, and
  update lifecycle. Ollama is a separate product with its own installer, multi-GB
  model store, and a server the user may already run for other tools; silently
  spawning a background `serve`, downloading gigabytes, or upgrading a shared
  install is surprising and hard to undo. Deferred to a separate, explicitly
  user-initiated effort.
- **One generic "Transform failed" error** (what shipped before). Cheap but
  unactionable: the user can't tell "never installed" from "server down" from
  "wrong model tag" — each needs a different fix.
- **Proactively probe Ollama health at startup / on a timer.** Lets the tray show
  readiness before the first Trigger Fire, but adds background polling and a
  health-state machine for a feature that's off by default. Diagnosing lazily on
  the failure path is enough; revisit if users want a readiness indicator.

## Consequences

- Default users without Ollama get a friendly "Summarise needs Ollama — see
  README" message, not a crash or a silent no-op.
- The Ollama backend enriches its failure with a small structured value (failure
  kind + any HTTP status) so the classifier can distinguish cases without
  re-probing the network.
- Dictatem's network surface is unchanged: it only ever POSTs to a user-run
  Ollama; no processes are spawned, no downloads triggered.
- The fresh-config default Transform model is tier-appropriate (a small tag on
  weak machines, `gemma4:e4b` on capable ones), but the user must still pull it.
- Any future "set up Ollama for me" affordance must be explicit and
  user-initiated — this ADR rules out doing it implicitly on the failure path.
