# Dictatem talks to Ollama but does not manage its lifecycle

The [Transform](../../CONTEXT.md#transform) feature calls a local Ollama server
over HTTP. Dictatem deliberately **does not** install Ollama, start it
(`ollama serve`), or pull models on the user's behalf. When a
[Trigger Fire](../../CONTEXT.md#trigger-fire) fails because Ollama isn't ready,
Dictatem diagnoses *why* from the **network response** and tells the user the
exact manual step to take:

- **not running / unreachable** — connection refused or transport error reaching
  `base_url` → "Ollama isn't reachable at `<base_url>`; make sure it's running —
  see the README to install it." The message names `base_url` (so a WSL/remote
  user sees *where* we looked) and keeps the install hint (so a brand-new user is
  still pointed at setup).
- **model missing** — HTTP 404 from `/api/generate` → name the configured model
  and the `ollama pull <model>` command.

The diagnosis is a pure classifier fed the structured failure signal; it makes no
network or filesystem calls.

We deliberately do **not** try to distinguish "not installed" as its own case.
The obvious signal — an `ollama` binary on PATH — is unreliable: Ollama commonly
runs in WSL, a container, or on another host reachable via `base_url` with no
binary on the local PATH, so "no binary" is not evidence it's uninstalled and
must never override a "connection refused". An unreachable server is therefore
reported as *not running* (with an install hint) rather than a false *not
installed*.

## Considered options

- **Auto-install / auto-`serve` / auto-`pull`.** Convenient, but pulls Dictatem
  into owning a second heavyweight runtime's install, version, GPU-memory, and
  update lifecycle. Ollama is a separate product with its own installer, multi-GB
  model store, and a server the user may already run for other tools; silently
  spawning a background `serve`, downloading gigabytes, or upgrading a shared
  install is surprising and hard to undo. Deferred to a separate, explicitly
  user-initiated effort.
- **One generic "Transform failed" error** (what shipped before). Cheap but
  unactionable: the user can't tell "Ollama unreachable" from "wrong model tag"
  from a server error — each needs a different fix.
- **Proactively probe Ollama health at startup / on a timer.** Lets the tray show
  readiness before the first Trigger Fire, but adds background polling and a
  health-state machine for a feature that's off by default. Diagnosing lazily on
  the failure path is enough; revisit if users want a readiness indicator.

## Consequences

- Default users without Ollama get a friendly "Ollama isn't reachable … see the
  README" message (with install guidance), not a crash or a silent no-op.
- The Ollama backend enriches its failure with a small structured value (failure
  kind + any HTTP status) so the classifier can distinguish cases without
  re-probing the network.
- Dictatem's network surface is unchanged: it only ever POSTs to a user-run
  Ollama; no processes are spawned, no downloads triggered.
- The fresh-config default Transform model is tier-appropriate (a small tag on
  weak machines, `gemma4:e4b` on capable ones), but the user must still pull it.
- Any future "set up Ollama for me" affordance must be explicit and
  user-initiated — this ADR rules out doing it implicitly on the failure path.
