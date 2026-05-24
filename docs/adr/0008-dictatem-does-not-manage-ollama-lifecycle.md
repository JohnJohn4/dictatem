# Dictatem does not manage the Ollama lifecycle

Dictatem talks to a *running* Ollama server to run [Transforms](../../CONTEXT.md#transform),
but it never installs Ollama, never starts `ollama serve`, and never pulls
models on the user's behalf. When a [Trigger Fire](../../CONTEXT.md#trigger-fire)
fails because Ollama isn't ready, Dictatem diagnoses *why* and tells the
user the exact manual step to take — install it, start it, or
`ollama pull <model>` — but it does not take that step itself.

The diagnosis is a pure classifier (`transform/failure_classifier.py`) that
maps two structured signals onto one of `not_installed`, `not_running`,
`model_missing`, or `unknown`, plus an actionable message:

- **`not_installed`** — no `ollama` binary on PATH (`shutil.which("ollama")`).
  Message points to the README setup section.
- **`not_running`** — connection refused / transport error reaching the
  server. Message: start Ollama, then try again.
- **`model_missing`** — HTTP 404 from `/api/generate`. Message names the
  configured model and the `ollama pull <model>` command.

The single OS touch (probing PATH for the binary) is injected into
`DaemonCore` as a `bool`-returning callable, so the classifier itself stays
pure and fully unit-tested with fakes.

## Considered Options

- **Auto-install / auto-`serve` / auto-`pull`.** Convenient, but pulls
  Dictatem into owning a second heavyweight runtime's install, version,
  GPU-memory, and update lifecycle. Ollama is a separate product with its
  own installer, model store (multi-GB pulls), and server process the user
  may already run for other tools. Silently mutating it — spawning a
  background `serve`, downloading gigabytes, or upgrading a shared install —
  is surprising and hard to undo. Out of scope.
- **One generic "Transform failed" error.** What shipped before this ADR.
  Cheap, but unactionable: the user can't tell "I never installed Ollama"
  from "the server is down" from "I typed the wrong model tag". Each needs
  a different fix.
- **Probe Ollama health proactively at startup / on a timer.** Lets the
  tray show readiness ahead of the first Trigger Fire, but adds background
  polling and a health-state machine for a feature that's off by default.
  Diagnosing lazily on the failure path covers the acceptance criteria
  without that machinery; revisit if users want a readiness indicator.

## Consequences

- The Ollama backend enriches its single `TransformFailedError` with a
  small immutable `OllamaFailure` value (`transform/failure.py`) carrying
  the failure kind and any HTTP status, so the classifier can distinguish
  cases without re-probing the network.
- The classifier is pure and lives beside the backend; the daemon does the
  one PATH probe and maps the resulting `FailureReason` to a tray title +
  the classifier's message on the existing overlay-flash / tray path.
- Dictatem's network surface is unchanged: it still only ever POSTs to a
  user-run Ollama. No new processes are spawned, no downloads triggered.
- If a future need arises to manage Ollama (e.g. an opt-in "set up Ollama
  for me" button), it must be an explicit, user-initiated action — this ADR
  rules out doing it implicitly on the failure path.
