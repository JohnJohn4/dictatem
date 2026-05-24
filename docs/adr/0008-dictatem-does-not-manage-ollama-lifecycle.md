# Dictatem talks to Ollama but does not manage its lifecycle

The [Transform](../../CONTEXT.md#transform) feature calls a local Ollama server
over HTTP. Dictatem deliberately **does not** install Ollama, start it
(`ollama serve`), or pull models on the user's behalf. It only talks to an
already-running instance and, on failure, reports an **actionable** error
distinguishing the three cases: Ollama not installed (point to README setup),
installed but not running (ask the user to start it), and running but the model
missing (suggest `ollama pull <model>`).

We chose this boundary because Ollama already runs itself as a background
service on Windows and macOS, so spawning our own `ollama serve` risks port
collisions and saddles Dictatem with another process's lifecycle; and
auto-pulling is a multi-GB download that must not happen silently. The
trade-off is a heavier manual setup for non-technical users, mitigated by clear
error messages and README instructions.

## Consequences

- Default users without Ollama get a friendly "Summarise needs Ollama" message,
  not a crash or a silent no-op.
- Auto-detect-installed → auto-pull (with consent) and auto-serve are a
  **deliberately deferred** power-user feature, to be designed as a separate
  effort — not bolted on by adding subprocess management to the daemon.
- The fresh-config default Transform model is tier-appropriate (a small tag on
  weak machines, `gemma4:e4b` on capable ones), but the user must still pull it.
