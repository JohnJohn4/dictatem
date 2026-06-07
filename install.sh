#!/bin/sh
# Dictatem one-line installer (macOS).
#
# Run it piped, straight from raw GitHub:
#
#     curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.3.0/install.sh | sh
#
# It is a thin uv-tool provisioning script (ADR-0011), the macOS mirror of
# install.ps1: it installs `uv` if absent, `uv tool install`s Dictatem from
# the pinned release tarball over HTTPS, generates the Dictatem.app permission
# identity shell (ADR-0014), and launches it once. It runs with no interactive
# prompts so the piped form works.
#
# macOS always gets the CPU-lean dependency set — there is no NVIDIA/CUDA on a
# Mac (ADR-0013) — so install.ps1's GPU auto-detection has no equivalent here.
#
# It deliberately does NOT download a Whisper model (lazy on first dictation)
# and does NOT install, start, or pull Ollama (ADR-0008) — it only prints a
# pointer to the README Ollama/Transform setup.
#
# This installs Dictatem pinned to the v0.3.0 release (the DICTATEM_TAG line
# below) for an auditable, reproducible install. It installs from the release
# *tarball* over HTTPS, NOT a git+ URL, so a clean Mac needs no git — a git+
# URL would trigger the Command Line Tools install prompt (#71, ADR-0015).
# When cutting a new release, bump that tag and the README one-liner URL
# together.
#
# Pre-release/QA installs: set DICTATEM_REF to a branch, tag, or commit SHA
# (e.g. DICTATEM_REF=main) to install from that ref's tarball instead. The
# override also passes --force --no-cache to uv: a moving ref keeps the same
# URL and version number, which uv would otherwise serve stale from its cache
# or skip as already-installed.

set -eu

# --- 1. Ensure uv is installed ---------------------------------------------
if command -v uv >/dev/null 2>&1; then
    echo "uv is already installed."
else
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The uv installer adds uv to PATH for new sessions; make it usable now.
    PATH="$HOME/.local/bin:$PATH"
fi

# --- 2. Install Dictatem from the GitHub release tarball --------------------
DICTATEM_TAG="v0.3.0"

if [ -n "${DICTATEM_REF:-}" ]; then
    echo "DICTATEM_REF=${DICTATEM_REF} — installing from that ref, bypassing uv's cache."
    source_url="https://github.com/JohnJohn4/dictatem/archive/${DICTATEM_REF}.tar.gz"
    uv_flags="--force --no-cache"
else
    source_url="https://github.com/JohnJohn4/dictatem/archive/refs/tags/${DICTATEM_TAG}.tar.gz"
    uv_flags=""
fi

# A single PEP 508 direct-reference requirement: the extras and the source URL
# must travel together on one argument. Splitting the URL into `--from` and the
# `dictatem[extras]` into a positional makes uv treat them as two conflicting
# requirements for the same package and abort.
requirement="dictatem[runtime] @ ${source_url}"

echo "Installing ${requirement} ..."
# $uv_flags is deliberately unquoted: empty by default, two words on override.
uv tool install $uv_flags "$requirement"

# Make the freshly installed `dictatem` launcher usable in THIS session — uv
# only updates PATH for new sessions. `uv tool update-shell` ensures the tool
# bin dir is on PATH persistently; prepend it here so the steps below work.
uv tool update-shell
tool_bin="$(uv tool dir --bin 2>/dev/null || true)"
if [ -n "$tool_bin" ]; then
    PATH="$tool_bin:$PATH"
fi

# --- 3. Generate the Dictatem.app identity shell ----------------------------
# The minimal, unsigned, locally-generated .app gives TCC a stable permission
# identity (ADR-0014): the user grants "Dictatem" — not "Python" — in System
# Settings, and the grants survive `uv tool upgrade`. Generated locally, it
# never hits Gatekeeper. Re-running this on upgrade also refreshes the
# start-at-login LaunchAgent's launch command.
dictatem --install-macos-app

# --- 4. Launch the daemon once ----------------------------------------------
# Launch through the .app with /usr/bin/open, NOT by running `dictatem` from
# this shell: macOS attributes a terminal-spawned process's permission prompts
# to the *terminal app*, which would defeat the identity shell entirely.
echo "Launching Dictatem..."
open -g "$HOME/Applications/Dictatem.app"

# --- 5. Permissions + optional Ollama pointers ------------------------------
echo ""
echo "Dictatem is starting in the menu bar."
echo "macOS will ask for Microphone access on your first dictation, and Dictatem"
echo "will guide you through granting Accessibility and Input Monitoring in"
echo "System Settings (each needs a one-time relaunch to apply)."
echo "Optional Trigger Words (local-LLM rewrites) need Ollama set up yourself — see"
echo "the README: https://github.com/JohnJohn4/dictatem#ollama--transform-setup"
