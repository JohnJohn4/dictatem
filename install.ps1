# Dictatem one-line installer (Windows).
#
# Run it piped, straight from raw GitHub (the leading Set-ExecutionPolicy is a
# process-scoped bypass so a restrictive machine policy doesn't block it — it
# needs no admin and reverts when the window closes):
#
#     Set-ExecutionPolicy -Scope Process Bypass -Force; irm https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.5.2/install.ps1 | iex
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
# This installs Dictatem pinned to the v0.5.2 release (the line marked below)
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

# --- 2.9 Stop any running daemon before (re)installing (#98) --------------
# Re-running the installer to UPGRADE fails while the old daemon is running:
# Windows won't let uv remove the tool dir whose loaded .exe/.dll is in use, so
# `uv tool install` aborts with "failed to remove directory ...\Scripts: Access
# is denied". Sibling of #69 (same lock, uninstall side). Stop the daemon first;
# step 4 relaunches the freshly installed version. No elevation — same-user
# processes — so this works where `sudo` is disabled on managed machines.
function Stop-DictatemDaemon {
    # Identify Dictatem processes by EXECUTABLE PATH, never by image name: the
    # daemon runs as a generic `pythonw.exe`, so name-matching would risk
    # killing unrelated Python. A process is a *root* iff its exe is the
    # `~/.local/bin/dictatem.exe` trampoline or lives under the uv tool's
    # `dictatem` env dir. Then walk root->descendants, because the launcher
    # (`Scripts\pythonw.exe`) re-execs the base CPython as a child (#43, the two
    # `pythonw.exe`), and THAT child is the real daemon — its exe lives outside
    # the tool dir, so path-matching alone would orphan it: the old daemon would
    # survive the upgrade, keep `Lib`/`Scripts` file-locked, AND fight the
    # relaunched one. Best-effort throughout: any failure leaves install to
    # proceed exactly as before.
    # `Select-Object -Last 1` keeps only the path line: uv prints diagnostics to
    # stderr (already dropped by 2>$null), but if a future uv ever wrote an
    # extra stdout line these captures would become arrays, and `Join-Path` on
    # an array throws (DriveNotFoundException) — which, under
    # $ErrorActionPreference='Stop', would abort the whole install instead of
    # just skipping the best-effort daemon-stop.
    $targets = @()
    $toolDir = (uv tool dir 2>$null | Select-Object -Last 1)
    if ($toolDir) { $targets += (Join-Path $toolDir 'dictatem') }
    $toolBin = (uv tool dir --bin 2>$null | Select-Object -Last 1)
    if ($toolBin) { $targets += (Join-Path $toolBin 'dictatem.exe') }
    if ($targets.Count -eq 0) { return }

    try {
        $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    } catch {
        return  # WMI unavailable — skip; the install proceeds as it did before.
    }
    if ($procs.Count -eq 0) { return }

    $byId = @{}
    $byParent = @{}
    foreach ($p in $procs) {
        $byId[[int]$p.ProcessId] = $p
        $ppid = [int]$p.ParentProcessId
        if (-not $byParent.ContainsKey($ppid)) {
            $byParent[$ppid] = New-Object System.Collections.Generic.List[int]
        }
        $byParent[$ppid].Add([int]$p.ProcessId)
    }

    $roots = New-Object System.Collections.Generic.List[int]
    foreach ($p in $procs) {
        $exe = $p.ExecutablePath
        if (-not $exe) { continue }
        foreach ($t in $targets) {
            if ($exe -ieq $t -or
                $exe.StartsWith("$t\", [System.StringComparison]::OrdinalIgnoreCase)) {
                $roots.Add([int]$p.ProcessId)
                break
            }
        }
    }
    if ($roots.Count -eq 0) { return }  # nothing running — fresh-install path

    # Breadth-first walk from the path-matched roots. Guard each hop with
    # creation time (a real child cannot predate its parent) so a recycled
    # parent PID can never drag an unrelated process into the kill set.
    $kill = New-Object System.Collections.Generic.HashSet[int]
    $queue = New-Object System.Collections.Generic.Queue[int]
    foreach ($r in $roots) { $queue.Enqueue($r) }
    while ($queue.Count -gt 0) {
        $id = $queue.Dequeue()
        if (-not $kill.Add($id)) { continue }
        if (-not $byParent.ContainsKey($id)) { continue }
        $parentStart = $byId[$id].CreationDate
        foreach ($childId in $byParent[$id]) {
            $child = $byId[$childId]
            if ($null -ne $parentStart -and $null -ne $child.CreationDate -and
                $child.CreationDate -lt $parentStart) {
                continue  # stale/recycled parent PID — not a genuine child
            }
            $queue.Enqueue($childId)
        }
    }

    $stopped = New-Object System.Collections.Generic.List[int]
    foreach ($id in $kill) {
        try {
            Stop-Process -Id $id -Force -ErrorAction Stop
            $stopped.Add($id)
        } catch {
            # Already exiting, or denied — best effort, keep going.
        }
    }
    if ($stopped.Count -gt 0) {
        Write-Host "Stopped the running Dictatem daemon before (re)installing (PID(s): $($stopped -join ', '))."
        # Wait for full exit so the loaded .exe/.dll handles release; otherwise
        # uv still can't remove the old tool dir.
        try {
            Wait-Process -Id $stopped -Timeout 10 -ErrorAction SilentlyContinue
        } catch {
            # Timed out or already gone — proceed regardless (best effort).
        }
    }
}

Stop-DictatemDaemon

# --- 3. Install Dictatem from the GitHub release tarball -----------------
# Install from the tag's source tarball over HTTPS, NOT a git+ URL: `uv tool
# install` resolves git+ URLs by shelling out to the `git` executable, so a git+
# install fails on machines without git (#71, ADR-0015). uv fetches the tarball
# with its own HTTP client and builds it with hatchling; Dictatem is pure-Python,
# so no git and no compiler are needed. Pinned to the v0.5.2 release for an
# auditable, reproducible install; when cutting a new release, bump this tag AND
# the README one-liner URL.
$source = 'https://github.com/JohnJohn4/dictatem/archive/refs/tags/v0.5.2.tar.gz'

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
$toolBin = (uv tool dir --bin 2>$null | Select-Object -Last 1)
if ($toolBin) {
    $env:Path = "$toolBin;$env:Path"
}

# Persist the tool-bin dir to the USER PATH ourselves (#99). On some managed
# machines `uv tool update-shell` doesn't reliably land the bin dir in the user
# PATH, so `dictatem` isn't found in a fresh shell and the user gets told to
# "add it to PATH" by hand. Writing the User-scope PATH needs no admin, so it
# works where `sudo` is disabled. We add both the uv tool-bin dir and
# `~/.local/bin` (where uv itself and the `dictatem` trampoline live) — they're
# usually the same dir, but we don't assume it.
function Add-ToUserPath {
    param([string]$Dir)
    if (-not $Dir) { return }
    try {
        # Edit HKCU\Environment directly rather than via
        # [Environment]::SetEnvironmentVariable(...,'User'): that API EXPANDS any
        # %VARS% it reads and writes the result back as a plain REG_SZ, which on
        # a default/managed Windows user PATH (REG_EXPAND_SZ, e.g.
        # `%USERPROFILE%\AppData\Local\Microsoft\WindowsApps`) bakes those refs
        # to literals and flips the value type — a silent regression. Reading
        # with DoNotExpandEnvironmentNames and re-writing the original value kind
        # leaves existing entries byte-for-byte intact.
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
        if ($null -eq $key) {
            $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
        }
        $rawPath = [string]$key.GetValue(
            'Path', '',
            [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        # Preserve the existing value type (REG_EXPAND_SZ vs REG_SZ); default to
        # ExpandString when no Path value exists yet.
        $kind = [Microsoft.Win32.RegistryValueKind]::ExpandString
        if ($rawPath) {
            try { $kind = $key.GetValueKind('Path') } catch { }
        }
        # Idempotent: compare the EXPANDED form of each stored entry against the
        # (already literal) target dir, ignoring case and a trailing slash, so a
        # dir stored as `%USERPROFILE%\.local\bin` still counts as present.
        $needle = $Dir.TrimEnd('\')
        foreach ($entry in ($rawPath -split ';')) {
            if (-not $entry) { continue }
            $expanded = [Environment]::ExpandEnvironmentVariables($entry).TrimEnd('\')
            if ($expanded -ieq $needle) { $key.Close(); return }
        }
        if ($rawPath) { $newPath = "$Dir;$rawPath" } else { $newPath = $Dir }
        $key.SetValue('Path', $newPath, $kind)
        $key.Close()
        Write-Host "Added $Dir to your user PATH (persists in new shells)."
    } catch {
        # A locked-down registry ACL must not fail the install — uv tool
        # update-shell above has already made its own attempt.
        Write-Host "Note: couldn't persist $Dir to your user PATH automatically (uv tool update-shell already tried)."
    }
}

Add-ToUserPath $toolBin
Add-ToUserPath "$env:USERPROFILE\.local\bin"

# --- 4. Launch the daemon once -------------------------------------------
Write-Host 'Launching Dictatem...'
Start-Process -FilePath 'dictatem'

# --- 5. Report status + point at the optional Ollama/Transform setup ------
# Don't claim the tray icon is already up (#102): the daemon is only just
# starting — Qt's event loop, and on managed machines an AV/EDR scan of the
# freshly written exe + CUDA DLLs on first launch, mean the icon can take a few
# seconds to appear. Saying "running in the system tray" before it's visible
# reads as a glitch, so set expectations instead.
Write-Host ''
Write-Host 'Dictatem is installed and starting now.'
Write-Host 'The tray icon will appear in a few seconds — on a managed/work machine the first launch can be slower while Windows scans the new files.'
Write-Host 'Optional Trigger Words (local-LLM rewrites) need Ollama set up yourself — see the README "Ollama / Transform setup" section: https://github.com/JohnJohn4/dictatem#ollama--transform-setup'
