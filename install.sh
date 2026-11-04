#!/bin/sh
# Dictatem one-line installer (macOS).
#
# Run it piped, straight from raw GitHub:
#
#     curl -fsSL https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.8.3/install.sh | sh
#
# It is a thin uv-tool provisioning script (ADR-0011), the macOS mirror of
# install.ps1: it installs `uv` if absent, `uv tool install`s Dictatem from
# the pinned release tarball over HTTPS, generates the Dictatem.app permission
# identity shell (ADR-0014), and launches it once. It runs with no interactive
# prompts so the piped form works.
#
# There is no NVIDIA/CUDA on a Mac (ADR-0013), so install.ps1's CUDA detection
# has no equivalent here. Instead, Apple Silicon on macOS 14+ also gets the MLX
# (Apple GPU) engine via the `apple-gpu` extra; every other Mac gets the CPU set
# (see select_dictatem_extra below).
#
# It deliberately does NOT download a Whisper model (lazy on first dictation)
# and does NOT install, start, or pull Ollama (ADR-0008) — it only prints a
# pointer to the README Ollama/Transform setup.
#
# This installs Dictatem pinned to the v0.8.3 release (the DICTATEM_TAG line
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
DICTATEM_TAG="v0.8.3"

if [ -n "${DICTATEM_REF:-}" ]; then
    echo "DICTATEM_REF=${DICTATEM_REF} — installing from that ref, refreshing uv's copy of it."
    source_url="https://github.com/JohnJohn4/dictatem/archive/${DICTATEM_REF}.tar.gz"
    uv_flags="--force --refresh-package dictatem"
else
    source_url="https://github.com/JohnJohn4/dictatem/archive/refs/tags/${DICTATEM_TAG}.tar.gz"
    uv_flags=""
fi

# Pick the engine set (ADR-0013 amendment, #224). The `apple-gpu` extra is the
# runtime set plus the MLX engine (mlx-whisper, ~230 MB more), which transcribes
# on the Apple GPU. It is OPT-IN for now (owner decision, v0.7.0): only
# DICTATEM_APPLE_GPU=1 on Apple Silicon with macOS 14+ selects it, until real-Mac
# QA of #230-#233 confirms latency and fallback; then this becomes the default.
# Everything else (no opt-in, Intel Macs, macOS 12/13, an unreadable version)
# keeps `runtime`: mlx/mlx-metal/torch ship macOS 14+ arm64 wheels only, so
# asking for them there would fail the whole install. A PEP 508 marker can't
# express "macOS 14+", hence this gate. faster-whisper is in both sets (it is the
# fallback engine). The user's config is never touched.
# Args: $1 = `uname -m`, $2 = `sw_vers -productVersion`. Prints the extra name.
# tests/test_apple_gpu_extra.py runs this function under sh — keep it top-level
# and self-contained.
select_dictatem_extra() {
    if [ "${DICTATEM_APPLE_GPU:-}" != "1" ] || [ "$1" != "arm64" ]; then
        echo runtime
        return
    fi
    _major="${2%%.*}"
    case "$_major" in
        '' | *[!0-9]*) echo runtime ;;
        *) if [ "$_major" -ge 14 ]; then echo apple-gpu; else echo runtime; fi ;;
    esac
}

dictatem_extra="$(select_dictatem_extra "$(uname -m)" "$(sw_vers -productVersion 2>/dev/null || true)")"
if [ "$dictatem_extra" = "apple-gpu" ]; then
    echo "Engine set: Apple GPU (MLX, beta) + CPU fallback — DICTATEM_APPLE_GPU=1 on Apple Silicon, macOS 14+."
elif [ "${DICTATEM_APPLE_GPU:-}" = "1" ]; then
    echo "Engine set: CPU (faster-whisper) — the Apple GPU engine needs Apple Silicon on macOS 14+."
else
    echo "Engine set: CPU (faster-whisper)."
fi

# A single PEP 508 direct-reference requirement: the extras and the source URL
# must travel together on one argument. Splitting the URL into `--from` and the
# `dictatem[extras]` into a positional makes uv treat them as two conflicting
# requirements for the same package and abort.
requirement="dictatem[${dictatem_extra}] @ ${source_url}"

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

# One-time PySide6 meta -> PySide6-Essentials migration (see install.ps1 for the
# full story): releases up to v0.7.0 used the `PySide6` meta package, which
# shares `PySide6/__init__.py` with Essentials, so an in-place upgrade that
# uninstalls the meta breaks Qt. Reinstall Essentials in the same transaction —
# only when the meta's dist-info (`pyside6-<ver>.dist-info`) is present, so
# steady-state upgrades don't rewrite Qt.
dictatem_has_pyside6_meta() {
    _env="$(dictatem_env_dir)"
    [ -n "$_env" ] && [ -d "$_env" ] || return 1
    for _d in "$_env"/lib/python3*/site-packages/pyside6-[0-9]*.dist-info; do
        [ -d "$_d" ] && return 0
    done
    return 1
}
if dictatem_has_pyside6_meta; then
    uv_flags="$uv_flags --reinstall-package pyside6-essentials"
fi

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

# The daemon drops this marker once its menu-bar icon is up (#95). Clear any
# stale one now, so the wait below only sees the daemon started here.
ready_marker="$HOME/.dictatem/.daemon_ready"
rm -f "$ready_marker" 2>/dev/null || true

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

# --- 5. Wait for the menu-bar icon, then say what's left ------------------
# Setup is NOT done when the files are installed: the first launch spends a
# while importing the speech stack before the icon and the permission prompts
# appear, and a hotkey pressed before the grants are in does nothing (#95).
# So wait for the daemon's ready marker (up to ~90 s) and keep the user posted,
# rather than printing "done" into ~20 s of silence.
printf "Waiting for Dictatem to start (the first launch can take up to a minute) "
i=0
while [ ! -f "$ready_marker" ] && [ "$i" -lt 360 ]; do
    sleep 0.25
    i=$((i + 1))
    if [ $((i % 8)) -eq 0 ]; then printf "."; fi
done
echo ""
echo ""
if [ -f "$ready_marker" ]; then
    echo "Dictatem is running — its icon is in your menu bar."
else
    echo "Dictatem is still starting — its menu-bar icon should appear shortly."
    echo "If it doesn't, see Troubleshooting:"
    echo "  https://github.com/JohnJohn4/dictatem#troubleshooting"
fi
echo ""
echo "Setup isn't finished until you've granted two permissions:"
echo "  1. When Dictatem asks for Accessibility and Input Monitoring, click"
echo "     Open System Settings and turn on \"python${DICTATEM_PYTHON}\" in each pane"
echo "     (that entry is Dictatem)."
echo "  2. Then choose Restart from the Dictatem menu-bar menu."
echo "The hotkey and paste won't work until both are on and Dictatem has restarted."
echo "(Already granted them on an earlier install? Then you're all set.)"
echo "macOS asks for Microphone access on your first dictation."
echo ""
echo "Optional Trigger Words (local-LLM rewrites) need Ollama set up yourself — see"
echo "the README: https://github.com/JohnJohn4/dictatem#trigger-words-setup-ollama"
