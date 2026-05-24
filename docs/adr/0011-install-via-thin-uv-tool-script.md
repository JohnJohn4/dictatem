# Install is a thin uv-tool provisioning script, not a signed bundled app

Dictatem ships as a one-line provisioning **script** (`irm …/install.ps1 | iex`
on Windows, `curl -fsSL …/install.sh | sh` on macOS) that installs
[`uv`](https://docs.astral.sh/uv/) if absent and then
`uv tool install git+https://github.com/JohnJohn4/dictatem@<tag>` with the
appropriate extra. We deliberately do **not** build a bundled, code-signed
application (`.app` / `.exe` / MSIX) for the foreseeable future.

A bundled app gives the glossiest "double-click, no Python" experience, but a
*downloaded* bundle trips macOS Gatekeeper (needs notarization → a paid Apple
Developer ID) and Windows SmartScreen (needs an Authenticode cert), and it
bundles Python + PySide6 + the transcription engine + CUDA into a multi-hundred-MB
artifact. The thin script sidesteps the entire signing tax — the interpreter
`uv` installs and the PySide6/engine wheels are already signed upstream, and a
*user-invoked* shell script is not subject to Gatekeeper/SmartScreen the way a
downloaded bundle is — while reusing the `uv` install path the project already
documented. We have no signing infrastructure and don't want to take on owning
one to ship installs.

## What the script does and does not do

- **Installs `uv`** (if not already present), then `uv tool install` from the
  GitHub repo pinned to a **release tag** (not `main`) for an auditable,
  reproducible install. Updating is re-running the one-liner at a newer tag, not
  a magic self-updater.
- **Picks the dependency set itself.** On Windows it auto-detects an NVIDIA GPU
  (`nvidia-smi` / WMI `Win32_VideoController`) and installs `dictatem[runtime-gpu]`
  if found, else `dictatem[runtime]` (the CPU-lean set from #40). An override
  env var / flag forces the choice. Interactive prompting is avoided because it
  breaks the piped `curl | sh` case (stdin is the script).
- **Does not pull the Whisper model.** The model lazy-downloads on first
  dictation (or via the tray Preload), so the first dictation has a one-time
  download lag and the install stays lean. Pre-pulling would presume a tier
  before the first-run [Hardware Tier](../../CONTEXT.md#hardware-tier) resolve
  (ADR-0007) and betray the lean-install promise.
- **Does not touch Ollama** — ADR-0008 stands; the script at most prints a
  pointer to the README's Ollama/Transform setup.
- **Does not register autostart itself.** The daemon owns autostart, reconciling
  the OS entry to `config.startup.autostart` on launch (see ADR-0012); the
  script's only startup role is the first launch.

## Distribution & trust

Scripts live in-repo and are served from raw GitHub at a pinned release tag with
a **readable** URL (no shortener, no custom domain for v1). The trust anchors are
honest: HTTPS defeats MITM, GitHub is the host, and a pinned tag lets a reviewer
audit the exact commit and guarantees it cannot change under the user. A cautious
user can `curl` the URL, read it, then run it. Checksums of a piped script are
circular (the hash would be fetched from the same host), so the readable, pinned
URL *is* the trust story rather than a published digest.

## Considered options

- **Bundled, signed app (`.app` / `.exe`).** Best UX, but pulls in a code-signing
  + notarization dependency (paid Apple Developer ID, Windows Authenticode cert)
  and a heavy multi-GB artifact. Rejected for v1: no signing infrastructure, and
  the script delivers "install in one line" without it.
- **Bundled app, unsigned.** Heavy build *and* a scary first-run ("unidentified
  developer" / "Windows protected your PC"). Worst of both.
- **`uv tool install` from PyPI.** More official and versioned, but needs a PyPI
  name claim and a release/publish workflow before anyone can install. Installing
  from a pinned GitHub tag needs neither and ships today; revisit if we want PyPI
  discoverability.
- **Custom domain (`get.dictatem.dev`).** Prettier one-liner, but adds DNS +
  hosting + redirect upkeep, and the natural wiring (→ `main`) reintroduces the
  unpinned-"latest" problem that tag-pinning solves.
- **Release-asset download (download `install.ps1` then run).** Most auditable,
  but not a one-liner — cuts against the "dead simple to install" goal.

## Consequences

- A `[project.gui-scripts]` entry point (`dictatem = "dictatem.daemon:main"`) is
  added so `uv tool install` yields a launch command that runs windowless (no
  console pop). This replaces `python -m dictatem` as the documented launch.
- Updates are "re-run the one-liner at a newer tag"; `uv tool upgrade` semantics
  don't move a git-pinned install across tags.
- Uninstall is **not** just `uv tool uninstall` — that would orphan the
  daemon-written autostart entry (ADR-0012). A real uninstall step removes the
  autostart entry first, then `uv tool uninstall dictatem`.
- Shipping installs now depends on cutting **tagged releases**; the README's
  one-liner names a concrete tag and is bumped per release.
- The same script shape serves both OSes (`.ps1` / `.sh`); the macOS engine and
  permissions story (separate ADRs) plug into the same provisioning flow.
