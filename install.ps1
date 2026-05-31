# Dictatem one-line installer (Windows).
#
# Run it piped, straight from raw GitHub:
#
#     irm https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.2.2/install.ps1 | iex
#
# It is a thin uv-tool provisioning script (ADR-0011): it installs `uv` if
# absent, picks the CPU or GPU dependency set by auto-detecting an NVIDIA GPU,
# `uv tool install`s Dictatem from this repo, and launches the daemon once. It
# runs with no interactive prompts so the piped form works.
#
# It deliberately does NOT download a Whisper model (lazy on first dictation)
# and does NOT install, start, or pull Ollama (ADR-0008) — it only prints a
# pointer to the README Ollama/Transform setup.
#
# This installs Dictatem pinned to the v0.2.2 release (the line marked below)
# for an auditable, reproducible install. It installs from the release *tarball*
# over HTTPS, NOT a git+ URL, so the user does NOT need `git` on their machine
# (#71). When cutting a new release, bump that tag and the README one-liner URL
# together.

$ErrorActionPreference = 'Stop'

# --- 1. Ensure uv is installed -------------------------------------------
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host 'uv is already installed.'
} else {
    Write-Host 'Installing uv...'
    irm https://astral.sh/uv/install.ps1 | iex
    # The uv installer adds uv to PATH for new sessions; make it usable now.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# --- 2. Pick the CPU or GPU dependency set -------------------------------
# Honor an explicit override first: DICTATEM_GPU=gpu forces the CUDA set,
# DICTATEM_GPU=cpu forces the lean set. Otherwise auto-detect an NVIDIA GPU.
function Test-NvidiaGpu {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        return $true
    }
    try {
        $gpus = Get-CimInstance -ClassName Win32_VideoController -ErrorAction Stop
        foreach ($gpu in $gpus) {
            if ($gpu.Name -and $gpu.Name -match 'NVIDIA') {
                return $true
            }
        }
    } catch {
        # WMI query unavailable — fall through to the CPU set.
    }
    return $false
}

$override = $env:DICTATEM_GPU
if ($override) { $override = $override.ToLower() }

if ($override -eq 'gpu') {
    $useGpu = $true
    Write-Host 'DICTATEM_GPU=gpu — installing the GPU (CUDA) dependency set.'
} elseif ($override -eq 'cpu') {
    $useGpu = $false
    Write-Host 'DICTATEM_GPU=cpu — installing the CPU-lean dependency set.'
} elseif (Test-NvidiaGpu) {
    $useGpu = $true
    Write-Host 'NVIDIA GPU detected — installing the GPU (CUDA) dependency set.'
} else {
    $useGpu = $false
    Write-Host 'No NVIDIA GPU detected — installing the CPU-lean dependency set.'
}

if ($useGpu) {
    $extras = 'runtime-gpu'
} else {
    $extras = 'runtime'
}

# --- 2.5 Windows on ARM: install under an x64 CPython (Prism emulation) ---
# On Windows on ARM (ARM64 / Snapdragon-class), `uv` installs a NATIVE ARM64
# CPython by default. The transcription engine `ctranslate2` (pulled by
# faster-whisper) ships NO win_arm64 wheel and is wheel-only (no sdist), so a
# native-ARM64 environment cannot provide a working engine. Every dependency
# does, however, run under Windows' built-in x64 emulation (Prism): pinned to an
# x64 interpreter, `ctranslate2`, `faster-whisper`, `sounddevice` (which then
# correctly loads the x64 PortAudio binary — its own arch check reports AMD64)
# and PySide6 all resolve and run. So on ARM64 we pin an x64 CPython for the tool
# environment. The hardware-tier logic is left untouched (a Snapdragon has no
# NVIDIA GPU, so it resolves to a CPU tier on its own). `--force` overwrites any
# stale launcher a prior failed native-ARM64 attempt may have left behind.
$pythonArgs = @()
$forceArgs = @()
if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
    Write-Host 'Windows on ARM detected — installing under x64 CPython (runs via Prism emulation).'
    Write-Host 'Native ARM64 is not yet supported: the transcription engine (ctranslate2) ships no win_arm64 wheel.'
    $x64Python = 'cpython-3.11-windows-x86_64'
    uv python install $x64Python
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to provision an x64 Python ($x64Python) for emulation (exit code $LASTEXITCODE)."
    }
    $pythonArgs = @('--python', $x64Python)
    $forceArgs = @('--force')
}

# --- 3. Install Dictatem from the GitHub release tarball -----------------
# Install from the tag's source tarball over HTTPS, NOT a git+ URL: `uv tool
# install` resolves git+ URLs by shelling out to the `git` executable, so a git+
# install fails on machines without git (#71, ADR-0015). uv fetches the tarball
# with its own HTTP client and builds it with hatchling; Dictatem is pure-Python,
# so no git and no compiler are needed. Pinned to the v0.2.2 release for an
# auditable, reproducible install; when cutting a new release, bump this tag AND
# the README one-liner URL.
$source = 'https://github.com/JohnJohn4/dictatem/archive/refs/tags/v0.2.2.tar.gz'

# A single PEP 508 direct-reference requirement: the extras and the source URL
# must travel together on one argument. Splitting the URL into `--from` and the
# `dictatem[extras]` into a positional makes uv treat them as two conflicting
# requirements for the same package and abort.
$requirement = "dictatem[$extras] @ $source"

Write-Host "Installing dictatem[$extras] from $source ..."
# @forceArgs / @pythonArgs are empty on x64 (no behaviour change there); on ARM64
# they expand to `--force --python cpython-3.11-windows-x86_64` (see step 2.5).
uv tool install @forceArgs @pythonArgs $requirement
# $ErrorActionPreference='Stop' does NOT halt on a native exe's non-zero exit,
# so guard explicitly — otherwise a failed install falls through to the launch
# below and surfaces as a misleading "cannot find the file" error.
if ($LASTEXITCODE -ne 0) {
    throw "uv tool install failed (exit code $LASTEXITCODE). See the error above; Dictatem was not installed."
}

# Make the freshly installed `dictatem` launcher usable in THIS session — uv
# only updates PATH for new sessions. `uv tool update-shell` ensures the tool
# bin dir is on PATH persistently; prepend it here so the launch below works.
uv tool update-shell
$toolBin = (uv tool dir --bin 2>$null)
if ($toolBin) {
    $env:Path = "$toolBin;$env:Path"
}

# --- 4. Launch the daemon once -------------------------------------------
Write-Host 'Launching Dictatem...'
Start-Process -FilePath 'dictatem'

# --- 5. Point at the optional Ollama/Transform setup ---------------------
Write-Host ''
Write-Host 'Dictatem is installed and running in the system tray.'
Write-Host 'Optional Trigger Words (local-LLM rewrites) need Ollama set up yourself — see the README "Ollama / Transform setup" section: https://github.com/JohnJohn4/dictatem#ollama--transform-setup'
