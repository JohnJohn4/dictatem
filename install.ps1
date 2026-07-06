# Dictatem one-line installer (Windows).
#
# Run it piped, straight from raw GitHub (the leading Set-ExecutionPolicy is a
# process-scoped bypass so a restrictive machine policy doesn't block it — it
# needs no admin and reverts when the window closes):
#
#     Set-ExecutionPolicy -Scope Process Bypass -Force; irm https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.6.4/install.ps1 | iex
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
# This installs Dictatem pinned to the v0.6.4 release (the line marked below)
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

# --- 2.5 Pin a uv-managed CPython (interpreter-discovery hazard, #90) ------
# Pin the tool environment to a uv-MANAGED CPython instead of whatever Python
# `uv` happens to discover on PATH. On x64, a discovered python.org 3.14+ build
# can hit missing-wheel resolution failures or land the install on an interpreter
# no CI cell tests — defeating the reproducible-install goal of ADR-0011/0015
# (the x64 mirror of the macOS discovery hazard install.sh already pins against).
# The version is kept inside CI's tested matrix (.github/workflows/ci.yml);
# tests/test_install_python_pin.py enforces that. Override for QA via
# DICTATEM_PYTHON (mirrors install.sh).
$dictatemPython = if ($env:DICTATEM_PYTHON) { $env:DICTATEM_PYTHON } else { '3.12' }

# Windows on ARM (ARM64 / Snapdragon-class): `uv` installs a NATIVE ARM64 CPython
# by default, but the transcription engine `ctranslate2` (pulled by
# faster-whisper) ships NO win_arm64 wheel and is wheel-only (no sdist), so a
# native-ARM64 environment cannot provide a working engine. Every dependency
# does, however, run under Windows' built-in x64 emulation (Prism): pinned to an
# x64 build of the managed CPython, `ctranslate2`, `faster-whisper`, `sounddevice`
# and PySide6 all resolve and run (ADR-0017). The hardware-tier logic is left
# untouched (a Snapdragon has no NVIDIA GPU, so it resolves to a CPU tier on its
# own). `--force` overwrites any stale launcher a prior failed native-ARM64
# attempt may have left behind.
#
# The ARM pin is 3.11, NOT the project-wide 3.12 (#181). Under x64 emulation,
# Python 3.12+ `platform.machine()` returns 'ARM64': 3.12 rewrote
# `platform._get_machine_win32()` to query WMI `Win32_Processor.Architecture`
# ("WOW64 processes mask the native architecture"), which reports the native
# silicon even inside an emulated x64 process. On 'ARM64', `sounddevice` (0.5.x)
# selects `libportaudioarm64.dll`, which the x64 (win_amd64) wheel does NOT
# bundle, so audio capture dies on the first dictation with `error 0x7e`. Python
# 3.11 has no such query and reports 'AMD64' under emulation, so `sounddevice`
# loads its bundled `libportaudio64bit.dll` and audio works — the exact config
# ADR-0017 originally QA'd. No ARM64 CI runner exists to catch this; 3.11 is in
# the matrix, so tests/test_install_python_pin.py stays green.
if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
    Write-Host 'Windows on ARM detected — installing under x64 CPython (runs via Prism emulation).'
    Write-Host 'Native ARM64 is not yet supported: the transcription engine (ctranslate2) ships no win_arm64 wheel.'
    # DICTATEM_PYTHON still overrides (QA); otherwise pin 3.11, not 3.12 — see above.
    if ($env:DICTATEM_PYTHON) {
        $x64Python = "cpython-$($env:DICTATEM_PYTHON)-windows-x86_64"
    } else {
        $x64Python = 'cpython-3.11-windows-x86_64'
    }
    uv python install $x64Python
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to provision an x64 Python ($x64Python) for emulation (exit code $LASTEXITCODE)."
    }
    $pythonArgs = @('--python', $x64Python)
    $forceArgs = @('--force')
} else {
    # x64 (incl. GPU): pin the managed CPython by version so uv downloads/uses it
    # rather than discovering a system Python (#90).
    $pythonArgs = @('--managed-python', '--python', $dictatemPython)
    $forceArgs = @()
}

# --- 2.9 Stop any running daemon before (re)installing (#98) --------------
# Re-running the installer to UPGRADE fails while the old daemon is running:
# Windows won't let uv remove the tool dir whose loaded .exe/.dll is in use, so
# `uv tool install` aborts with "failed to remove directory ...\Scripts: Access
# is denied". Sibling of #69 (same lock, uninstall side). Stop the daemon first;
# step 4 relaunches the freshly installed version. No elevation — same-user
# processes — so this works where `sudo` is disabled on managed machines.

# >>> Canonical daemon-stop decision — synced VERBATIM from
# scripts/daemon_stop_lib.ps1. tests/test_daemon_stop_parity.py keeps this block
# identical to that file AND parity-checks it against the Python stopper
# (dictatem.process.daemon_stop.pids_to_stop). Edit the .ps1, then re-sync here. >>>
# Pure daemon-stop decision — the PowerShell mirror of
# dictatem.process.daemon_stop.pids_to_stop (kept in parity by
# tests/test_daemon_stop_parity.py). Given a process snapshot, the install dir,
# the launcher trampoline(s), and the current PID, return the PIDs of the daemon's
# process tree to terminate. No live enumeration, no Stop-Process — pure logic, so
# it is unit-tested against the Python core. install.ps1 embeds an identical copy
# (verified by the same test) and calls it from Stop-DictatemDaemon.
#
# Roots = a process whose ExecutablePath is under ToolDir or equals a Trampoline;
# the result is each root and its descendants (the launcher's re-exec'd base
# interpreter, whose exe is outside the tool dir), minus SelfPid and SelfPid's own
# subtree (so the tray upgrade's installer — a daemon child — never kills itself
# or the uv processes it spawns).
function Get-DnNormalizedPath {
    param([string] $Path)
    if (-not $Path) { return '' }
    return ($Path -replace '\\', '/').TrimEnd('/').ToLowerInvariant()
}

function Get-DnIsUnder {
    param([string] $Path, [string] $Parent)
    if (-not $Path) { return $false }
    $np = Get-DnNormalizedPath $Path
    $npar = Get-DnNormalizedPath $Parent
    if (-not $npar) { return $false }
    return $np.StartsWith($npar + '/')
}

function Get-DaemonKillSet {
    param(
        [object[]] $Processes,
        [string]   $ToolDir,
        [string[]] $Trampolines = @(),
        [int]      $SelfPid = 0
    )
    $byId = @{}
    $byParent = @{}
    foreach ($p in $Processes) {
        $byId[[int] $p.ProcessId] = $p
        $ppid = [int] $p.ParentProcessId
        if (-not $byParent.ContainsKey($ppid)) {
            $byParent[$ppid] = New-Object System.Collections.Generic.List[object]
        }
        $byParent[$ppid].Add($p)
    }

    $tramp = @{}
    foreach ($t in $Trampolines) { if ($t) { $tramp[(Get-DnNormalizedPath $t)] = $true } }

    $seen = New-Object System.Collections.Generic.HashSet[int]
    $queue = New-Object System.Collections.Generic.Queue[int]
    foreach ($p in $Processes) {
        $exe = [string] $p.ExecutablePath
        $isRoot = $false
        if ($exe) {
            if (Get-DnIsUnder $exe $ToolDir) { $isRoot = $true }
            elseif ($tramp.ContainsKey((Get-DnNormalizedPath $exe))) { $isRoot = $true }
        }
        if ($isRoot) { $queue.Enqueue([int] $p.ProcessId) }
    }

    while ($queue.Count -gt 0) {
        $id = $queue.Dequeue()
        # Never us, and never descend into our own subtree.
        if ($id -eq $SelfPid) { continue }
        if (-not $seen.Add($id)) { continue }
        if (-not $byParent.ContainsKey($id)) { continue }
        $parent = $byId[$id]
        foreach ($child in $byParent[$id]) {
            $cid = [int] $child.ProcessId
            if ($seen.Contains($cid)) { continue }
            # A genuine child cannot have started before its parent; a child that
            # does is a stale/recycled parent PID, not really ours — skip it.
            if ($null -ne $parent -and $parent.CreationDate -and $child.CreationDate -and
                ([string] $child.CreationDate) -lt ([string] $parent.CreationDate)) {
                continue
            }
            $queue.Enqueue($cid)
        }
    }

    # Return PIDs in input order (parity with the Python core).
    $result = New-Object System.Collections.Generic.List[int]
    foreach ($p in $Processes) {
        if ($seen.Contains([int] $p.ProcessId)) { $result.Add([int] $p.ProcessId) }
    }
    return $result.ToArray()
}
# <<< end canonical daemon-stop decision <<<

function Stop-DictatemDaemon {
    # Best-effort: enumerate processes, run the pure Get-DaemonKillSet decision
    # (path-matched roots + descendants, minus us/our subtree — see its comment),
    # and terminate the result. Any failure leaves install to proceed as before.
    # Resolve the install dir + launcher trampoline the daemon's processes live
    # under. `Select-Object -Last 1` keeps only the path line (uv diagnostics go
    # to stderr, already dropped); if a future uv wrote an extra stdout line the
    # capture would be an array and Join-Path would throw under
    # $ErrorActionPreference='Stop', aborting the whole install.
    $dictatemToolDir = $null
    $toolDir = (uv tool dir 2>$null | Select-Object -Last 1)
    if ($toolDir) { $dictatemToolDir = (Join-Path $toolDir 'dictatem') }
    $trampolines = @()
    $toolBin = (uv tool dir --bin 2>$null | Select-Object -Last 1)
    if ($toolBin) { $trampolines += (Join-Path $toolBin 'dictatem.exe') }
    if (-not $dictatemToolDir -and $trampolines.Count -eq 0) { return }

    try {
        $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    } catch {
        return  # WMI unavailable — skip; the install proceeds as it did before.
    }
    if ($procs.Count -eq 0) { return }

    # Path-matched roots + their descendants, minus us and our subtree (the tray
    # upgrade runs this installer as a daemon child). The decision is the synced
    # Get-DaemonKillSet above, parity-tested against the Python stopper.
    $kill = Get-DaemonKillSet -Processes $procs -ToolDir $dictatemToolDir -Trampolines $trampolines -SelfPid $PID
    if (-not $kill -or @($kill).Count -eq 0) { return }

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

# --- 2.95 Recover a half-removed / invalid tool env (#110) ----------------
# A prior upgrade that aborted mid-removal can leave the tool env at
# `…\uv\tools\dictatem` HALF-REMOVED: `Scripts\python.exe` is already deleted
# but the loaded `pythonw.exe` survived (a running daemon held a file lock, so
# uv hit "Access is denied" and bailed). uv then refuses EVERY later install —
# it validates the existing env first and errors with "Invalid environment …
# missing Python executable at …\Scripts\python.exe" (exit 2). Older installers
# (pre-#98 daemon-stop) corrupted envs this way; their users only escape it by
# upgrading through this script, so it must self-heal. `uv tool uninstall`
# cleanly clears even an invalid env (uv validates on install, not on uninstall
# — proven in v0.5.x QA), so we clear the broken env, then install fresh.
function Get-DictatemToolEnvDir {
    $toolDir = (uv tool dir 2>$null | Select-Object -Last 1)
    if (-not $toolDir) { return $null }
    return (Join-Path $toolDir 'dictatem')
}

function Test-DictatemEnvBroken {
    # True when a Dictatem tool env dir EXISTS but is invalid the way uv reports
    # on (re)install: the env is present yet its Python executable is gone — the
    # exact half-removed shape from #110. A healthy env (python.exe present) and
    # a clean machine (no env dir) both return false, so recovery never touches
    # a working install.
    $envDir = Get-DictatemToolEnvDir
    if (-not $envDir -or -not (Test-Path -LiteralPath $envDir)) { return $false }
    return -not (Test-Path -LiteralPath (Join-Path $envDir 'Scripts\python.exe'))
}

function Repair-DictatemToolEnv {
    # Best-effort: clear a broken/leftover Dictatem tool env so the next
    # `uv tool install` recreates it from scratch. `uv tool uninstall` removes
    # even an invalid env and its trampoline; force-remove whatever it leaves
    # behind (an env uv's ledger no longer tracks won't be touched by uninstall).
    # The daemon was already stopped above, so the files are unlocked. Nothing
    # here throws — a failure just falls through to the install attempt.
    Write-Host 'Found a broken/leftover Dictatem tool environment — clearing it before installing...'
    try { uv tool uninstall dictatem 2>$null | Out-Null } catch { }
    $envDir = Get-DictatemToolEnvDir
    if ($envDir -and (Test-Path -LiteralPath $envDir)) {
        try { Remove-Item -LiteralPath $envDir -Recurse -Force -ErrorAction Stop } catch { }
    }
    $toolBin = (uv tool dir --bin 2>$null | Select-Object -Last 1)
    if ($toolBin) {
        $tramp = (Join-Path $toolBin 'dictatem.exe')
        if (Test-Path -LiteralPath $tramp) {
            try { Remove-Item -LiteralPath $tramp -Force -ErrorAction Stop } catch { }
        }
    }
}

# --- 3. Install Dictatem from the GitHub release tarball -----------------
# Install from the tag's source tarball over HTTPS, NOT a git+ URL: `uv tool
# install` resolves git+ URLs by shelling out to the `git` executable, so a git+
# install fails on machines without git (#71, ADR-0015). uv fetches the tarball
# with its own HTTP client and builds it with hatchling; Dictatem is pure-Python,
# so no git and no compiler are needed. Pinned to the v0.6.4 release for an
# auditable, reproducible install; when cutting a new release, bump this tag AND
# the README one-liner URL.
$source = 'https://github.com/JohnJohn4/dictatem/archive/refs/tags/v0.6.4.tar.gz'

# A single PEP 508 direct-reference requirement: the extras and the source URL
# must travel together on one argument. Splitting the URL into `--from` and the
# `dictatem[extras]` into a positional makes uv treat them as two conflicting
# requirements for the same package and abort.
$requirement = "dictatem[$extras] @ $source"

# Heal a pre-broken env before the first attempt, so uv doesn't bail on its
# "Invalid environment" validation (#110). Idempotent: a healthy env is left
# untouched. `--force` (ARM64 only) overwrites a valid env but does NOT recover
# an invalid one, so this runs on every arch.
if (Test-DictatemEnvBroken) { Repair-DictatemToolEnv }

Write-Host "Installing dictatem[$extras] from $source ..."
# @forceArgs / @pythonArgs pin the interpreter (step 2.5, #90 / ADR-0017 / #181):
# on x64 they expand to `--managed-python --python 3.12`; on ARM64 to `--force
# --python cpython-3.11-windows-x86_64` (ARM pins 3.11, not 3.12 — see step 2.5).
uv tool install @forceArgs @pythonArgs $requirement
# $ErrorActionPreference='Stop' does NOT halt on a native exe's non-zero exit,
# so guard explicitly — otherwise a failed install falls through to the launch
# below and surfaces as a misleading "cannot find the file" error.
if ($LASTEXITCODE -ne 0) {
    # The install itself can corrupt the env mid-run if a process slipped past
    # Stop-DictatemDaemon and still held pythonw.exe: uv deletes python.exe, then
    # aborts on the lock, leaving the same half-removed shape (#110). If the env
    # is now broken, clear it and retry ONCE. Gated on the broken-env check — not
    # a blind retry — so an unrelated failure (network, build) never nukes a
    # healthy env: it falls straight through to the throw, preserving prior
    # behaviour.
    if (Test-DictatemEnvBroken) {
        Write-Host "uv tool install failed (exit code $LASTEXITCODE) — recovering the broken tool environment and retrying once..."
        Repair-DictatemToolEnv
        uv tool install @forceArgs @pythonArgs $requirement
    }
    if ($LASTEXITCODE -ne 0) {
        # --managed-python (step 2.5) needs a recent uv; step 1 only installs uv
        # when ABSENT, so a stale pre-existing uv fails on the unknown flag.
        Write-Host "If the error above calls '--managed-python' unexpected, your pre-existing uv is too old: update it ('uv self update') and re-run this installer."
        throw "uv tool install failed (exit code $LASTEXITCODE). See the error above; Dictatem was not installed."
    }
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
Write-Host 'Optional Trigger Words (local-LLM rewrites) need Ollama set up yourself — see the README "Trigger Words setup (Ollama)" section: https://github.com/JohnJohn4/dictatem#trigger-words-setup-ollama'
