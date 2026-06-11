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
