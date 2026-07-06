#!/bin/sh
# Dictatem one-line installer (macOS).
#
# Run it piped, straight from raw GitHub:
#
#     curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.6.3/install.sh | sh
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
# This installs Dictatem pinned to the v0.6.3 release (the DICTATEM_TAG line
# below) for an auditable, reproducible install. It installs from the release
# *tarball* over HTTPS, NOT a git+ URL, so a clean Mac needs no git — a git+
# URL would trigger the Command Line Tools install prompt (#71, ADR-0015).
# When cutting a new release, bump that tag and the README one-liner URL
# together.
#
# Pre-release/QA installs: set DICTATEM_REF to a branch, tag, or commit SHA
# (e.g. DICTATEM_REF=main) to install from that ref's tarball instead. The
# override also passes --force --refresh-package dictatem to uv: a moving ref
# keeps the same URL and version number, which uv would otherwise serve stale
# from its cache or skip as already-installed. (--refresh-package, not
# --no-cache: only the dictatem tarball is moving — the cached dependency
# wheels, ~0.5 GB, stay valid across QA iterations.)

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
DICTATEM_TAG="v0.6.3"

if [ -n "${DICTATEM_REF:-}" ]; then
    echo "DICTATEM_REF=${DICTATEM_REF} — installing from that ref, refreshing uv's copy of it."
    source_url="https://github.com/JohnJohn4/dictatem/archive/${DICTATEM_REF}.tar.gz"
    uv_flags="--force --refresh-package dictatem"
else
    source_url="https://github.com/JohnJohn4/dictatem/archive/refs/tags/${DICTATEM_TAG}.tar.gz"
    uv_flags=""
fi

# A single PEP 508 direct-reference requirement: the extras and the source URL
# must travel together on one argument. Splitting the URL into `--from` and the
# `dictatem[extras]` into a positional makes uv treat them as two conflicting
# requirements for the same package and abort.
requirement="dictatem[runtime] @ ${source_url}"

# Pin the tool environment to a uv-MANAGED CPython instead of whatever Python
# the Mac happens to have. Real-Mac QA (#61) showed a discovered python.org
# universal2 build Rosetta-mislaunching its x86_64 slice and crashing on the
# arm64-only wheels; a managed single-arch arm64 build fixes that boot crash.
# (It does NOT fix the TCC label — the daemon still shows as "python3.12" in
# the privacy panes; a clean "Dictatem" identity needs a signed bundle and is
# an accepted limitation, see ADR-0014's amendment / #91.) Keep the version
# inside CI's tested matrix (tests/test_install_python_pin.py enforces this for
# both installers, #90); the env override mirrors DICTATEM_REF for QA.
DICTATEM_PYTHON="${DICTATEM_PYTHON:-3.12}"

# Recover a half-removed / invalid tool env before installing (parity with
# install.ps1, #110). A prior upgrade that aborted mid-removal can leave the env
# at `<uv tools dir>/dictatem` invalid — its `bin/python` gone — and uv then
# refuses every later install ("Invalid environment ... missing Python
# executable"). File locking makes this far rarer on macOS than Windows, but the
# recovery is cheap and idempotent. `uv tool uninstall` clears even an invalid
# env (uv validates on install, not on uninstall), so we clear a broken env (and
# force-remove any leftover the ledger no longer tracks) before installing.
dictatem_env_dir() {
    _tools="$(uv tool dir 2>/dev/null || true)"
    [ -n "$_tools" ] && printf '%s/dictatem' "$_tools"
}

# True (exit 0) only when a Dictatem env dir EXISTS but its Python is gone — the
# half-removed shape. A healthy env and a clean machine both return non-zero, so
# recovery never touches a working install.
dictatem_env_broken() {
    _env="$(dictatem_env_dir)"
    [ -n "$_env" ] && [ -d "$_env" ] && [ ! -e "$_env/bin/python" ]
}

repair_dictatem_env() {
    echo "Found a broken/leftover Dictatem tool environment — clearing it before installing..."
    uv tool uninstall dictatem >/dev/null 2>&1 || true
    _env="$(dictatem_env_dir)"
    [ -n "$_env" ] && [ -d "$_env" ] && rm -rf "$_env" 2>/dev/null || true
    _bin="$(uv tool dir --bin 2>/dev/null || true)"
    [ -n "$_bin" ] && rm -f "$_bin/dictatem" 2>/dev/null || true
}

# Heal a pre-broken env before the first attempt so uv doesn't bail on its
# "Invalid environment" validation. Idempotent — a healthy env is left untouched.
if dictatem_env_broken; then repair_dictatem_env; fi

echo "Installing ${requirement} (on managed CPython ${DICTATEM_PYTHON}) ..."
# $uv_flags is deliberately unquoted: empty by default, two words on override.
# The else block exists because --managed-python needs a recent uv: step 1 only
# installs uv when ABSENT, and a stale pre-existing uv fails on the unknown
# flag — a piped user never sees source comments, so print the remedy.
if uv tool install $uv_flags --managed-python --python "$DICTATEM_PYTHON" "$requirement"; then
    :  # installed cleanly
elif dictatem_env_broken; then
    # The install corrupted the env mid-run (#110) — clear it and retry ONCE.
    # Gated on the broken-env check, not a blind retry: an unrelated failure
    # (network, build, or the stale-uv case below) skips this branch.
    echo "uv tool install failed — recovering the broken tool environment and retrying once..."
    repair_dictatem_env
    uv tool install $uv_flags --managed-python --python "$DICTATEM_PYTHON" "$requirement" || {
        echo ""
        echo "uv tool install failed after recovering the environment. See the error"
        echo "above; Dictatem was not installed."
        exit 1
    }
else
    echo ""
    echo "uv tool install failed. If the error above calls '--managed-python'"
    echo "unexpected, your pre-existing uv is too old: update it ('uv self update',"
    echo "or 'brew upgrade uv' if it came from Homebrew) and re-run this installer."
    exit 1
fi

# Make the freshly installed `dictatem` launcher usable in THIS session — uv
# only updates PATH for new sessions. `uv tool update-shell` ensures the tool
# bin dir is on PATH persistently; prepend it here so the steps below work.
# update-shell is best-effort (|| true): a pre-existing older uv without the
# subcommand must not abort the install under set -e — the session PATH below
# is what the remaining steps actually need.
uv tool update-shell || true
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

# --- 4. Start the daemon under launchd --------------------------------------
# The daemon must run under launchd — NOT via `open` on the .app, and NOT via a
# plain Terminal launch. Real-Mac QA (#54/#56/#59) pinned down two constraints:
#   * Launching through the .app makes the daemon inherit the bundle's
#     LaunchServices identity, and macOS then refuses to render its menu-bar
#     status item (the tray icon never appears).
#   * A Terminal-launched daemon (e.g. `nohup dictatem &` from this `curl | sh`)
#     makes macOS attribute the daemon's permission-gated actions — the hotkey
#     CGEventTap and the synthetic paste — to the *responsible* process,
#     Terminal, which is not granted Input Monitoring / Accessibility. The
#     hotkey and paste then silently die.
# launchd is the responsible process for a LaunchAgent, so the grants bound to
# the interpreter apply, and a launchd launch is a direct (non-bundle) launch
# so the status item shows. (Grants bind to the interpreter regardless; the
# .app does not change that — ADR-0014 / #91.)
echo "Launching Dictatem..."
launcher="$(command -v dictatem || echo "$HOME/.local/bin/dictatem")"
uid="$(id -u)"
# launchctl target grammar differs by subcommand: bootout/print/kickstart take
# a SERVICE target (gui/<uid>/<label>), but bootstrap takes the DOMAIN target
# (gui/<uid>) followed by the plist path. Passing the service target to
# bootstrap makes every retry fail and fall through to the broken
# terminal-launch fallback (hotkey + paste then silently die) — fresh-Mac QA
# caught exactly this on a clean install (#56/#59).
domain="gui/$uid"
service="gui/$uid/com.dictatem.daemon"
plist="$HOME/Library/LaunchAgents/com.dictatem.daemon.plist"

# Stop any running daemon (launchd-managed or a stray direct run) so a
# re-install/upgrade restarts cleanly (until the single-instance guard, #92),
# then WAIT for the launchd job to finish unloading: bootout is asynchronous,
# so bootstrapping immediately would race it, fail, and fall through to the
# broken terminal-launch fallback.
launchctl bootout "$service" 2>/dev/null || true
pkill -f "$launcher" 2>/dev/null || true
i=0
while launchctl print "$service" >/dev/null 2>&1 && [ "$i" -lt 40 ]; do
    sleep 0.25
    i=$((i + 1))
done

# Register the LaunchAgent if it does not exist yet: the daemon writes it on its
# first run by reconciling config.startup.autostart (default on, ADR-0012). A
# brief direct run is enough; stop it once the plist appears. The wait is
# generous — a cold first run imports the ML/Qt stack before reconciling.
if [ ! -f "$plist" ]; then
    "$launcher" >/dev/null 2>&1 &
    boot_pid=$!
    i=0
    while [ ! -f "$plist" ] && [ "$i" -lt 160 ]; do
        sleep 0.25
        i=$((i + 1))
    done
    kill "$boot_pid" 2>/dev/null || true
    wait "$boot_pid" 2>/dev/null || true
fi

# Start the daemon under launchd (see the comment above for why a terminal
# launch breaks the hotkey/paste). bootstrap loads the plist and RunAtLoad
# starts it; retry a few times in case the unload has not fully settled.
if [ -f "$plist" ]; then
    i=0
    while ! launchctl bootstrap "$domain" "$plist" 2>/dev/null && [ "$i" -lt 12 ]; do
        sleep 0.5
        i=$((i + 1))
    done
    if ! launchctl print "$service" >/dev/null 2>&1; then
        # launchd would not take it — direct-run fallback so the install still
        # leaves a daemon up (hotkey/paste limited until a launchd start).
        nohup "$launcher" >/dev/null 2>&1 &
    fi
else
    # Autostart is off (no plist written) — direct-run fallback. The hotkey and
    # paste will not work until the daemon runs under launchd; re-enable "Start
    # at Login" from the tray to fix that.
    nohup "$launcher" >/dev/null 2>&1 &
fi

# --- 5. Permissions + optional Ollama pointers ------------------------------
echo ""
echo "Dictatem is starting in the menu bar."
echo "macOS will ask for Microphone access on your first dictation, and Dictatem"
echo "will guide you through granting Accessibility and Input Monitoring in"
echo "System Settings (each needs a one-time relaunch to apply)."
echo "Optional Trigger Words (local-LLM rewrites) need Ollama set up yourself — see"
echo "the README: https://github.com/JohnJohn4/dictatem#trigger-words-setup-ollama"
