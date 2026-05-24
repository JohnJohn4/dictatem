#!/bin/sh
# Dictatem one-line installer (macOS).
#
# Run it piped, straight from raw GitHub:
#
#     curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/feat/macos-track/install.sh | sh
#
# It is a thin uv-tool provisioning script (ADR-0011): it installs `uv` if
# absent, `uv tool install`s Dictatem (the CPU `runtime` extra — macOS v1
# transcribes on CPU faster-whisper, ADR-0013), then generates the local
# ~/Applications/Dictatem.app identity shell (ADR-0014) and launches it. It runs
# with no interactive prompts so the piped form works (stdin is the script).
#
# It deliberately does NOT download a Whisper model (lazy on first dictation) and
# does NOT install, start, or pull Ollama (ADR-0008) — it only prints a pointer
# to the README Ollama/Transform setup.
#
# DEVELOPMENT PIN: this installs from the branch ref `@feat/macos-track`. The
# release (the macOS go-live, issue #60) will pin this to a tag for an auditable,
# reproducible install — do not invent a tag here.

set -eu

# --- 1. Ensure uv is installed -------------------------------------------
if command -v uv >/dev/null 2>&1; then
    echo 'uv is already installed.'
else
    echo 'Installing uv...'
    curl -fsSL https://astral.sh/uv/install.sh | sh
    # The uv installer adds uv to PATH for new shells; make it usable now.
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- 2. Install Dictatem from the GitHub branch --------------------------
# macOS uses the CPU-lean `runtime` extra: there is no CUDA on a Mac and v1
# transcribes on CPU faster-whisper (ADR-0013). There is no GPU/CPU auto-detect
# branch like Windows has.
#
# DEVELOPMENT PIN: installs from @feat/macos-track. Release pins this to a tag.
SOURCE='git+https://github.com/JohnJohn4/dictatem@feat/macos-track'

echo "Installing dictatem[runtime] from ${SOURCE} ..."
uv tool install --from "$SOURCE" 'dictatem[runtime]'

# Make the freshly installed `dictatem` launcher usable in THIS shell — uv only
# updates PATH for new shells. update-shell makes the tool bin dir persistent;
# prepend it here so the steps below resolve `dictatem`.
uv tool update-shell || true
TOOL_BIN="$(uv tool dir --bin 2>/dev/null || true)"
if [ -n "${TOOL_BIN}" ]; then
    export PATH="${TOOL_BIN}:$PATH"
fi

# --- 3. Generate the .app identity shell + LaunchAgent -------------------
# The unsigned, locally-generated bundle gives TCC a stable identity so the
# Accessibility / Input Monitoring grants survive `uv tool` upgrades (ADR-0014).
# This also reconciles the LaunchAgent to config.startup.autostart.
echo 'Generating ~/Applications/Dictatem.app ...'
dictatem --install-macos-app

# --- 4. Launch the daemon once -------------------------------------------
echo 'Launching Dictatem...'
open -a "$HOME/Applications/Dictatem.app" || dictatem &

# --- 5. Point at first-run permissions + Ollama setup --------------------
echo ''
echo 'Dictatem is installed and running in the menu bar.'
echo 'On first launch macOS will ask you to grant Input Monitoring (the hotkey)'
echo 'and Accessibility (typing into the focused app) in System Settings, then'
echo 'relaunch Dictatem once. Microphone access is the automatic prompt.'
echo ''
echo 'Optional Trigger Words (local-LLM rewrites) need Ollama set up yourself — see'
echo 'the README "Ollama / Transform setup": https://github.com/JohnJohn4/dictatem#ollama--transform-setup'
