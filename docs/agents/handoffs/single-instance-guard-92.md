# Handoff — Single-instance guard (#92)

**Goal:** prevent two Dictatem daemons from ever running concurrently. Implement the
cross-platform single-instance guard described in issue **#92**.

## Why now (root cause from a live session)

While running the dev clone for the #126 vocabulary QA, **every dictation
double-pasted and left dictation text stuck on the clipboard.** It was *not* a
dispatch/paste/transcribe regression — all that code is clean. Instrumented logging
proved the cause was **two concurrent daemons**:

| Daemon | Process | State |
|---|---|---|
| Installed **v0.5.6** (autostarted at login) | `dictatem.exe` → `pythonw.exe` under `uv\tools\dictatem` | warm model → instant paste |
| **Dev clone** (`uv run python -m dictatem`) | `python.exe` in `.venv` | cold model → 2.2s load |

Both register the global Win+Alt hook, so each gesture was recorded → transcribed →
pasted by **both** independently (two distinct audio buffers, e.g. `03.120` vs
`03.094`; one warm-instant, one cold-loading). Killing the installed daemon →
immediately back to a single paste and a clean clipboard.

**Key gotcha that cost hours:** the installed daemon runs as **`pythonw.exe`**, so a
casual `Get-Process python` / `Name='python.exe'` check does **not** see it. Use
`Get-CimInstance Win32_Process | Where CommandLine -like '*dictatem*'` to enumerate
all instances regardless of host exe.

## The fix

Add a single-instance guard in `_run_daemon` (`src/dictatem/daemon.py`, the
OS-neutral entry around the Qt setup) so a second instance detects the first and
exits cleanly **before** installing hooks / capturing audio / showing a tray icon.

Issue #92's proposed mechanism: `QtCore.QLockFile` at `~/.dictatem/daemon.lock`.
- Acquire early in `_run_daemon`; if `tryLock()` fails, log `"Another Dictatem
  instance is already running; exiting"` and return (no Qt loop, no hooks).
- **Keep the QLockFile object alive for the whole process lifetime** (bind it to a
  variable that outlives setup) — releasing it would drop the guard.
- `QLockFile` handles **stale locks** from a crashed PID automatically; verify this
  on Windows (kill -9 the daemon, relaunch → should acquire, not deadlock).
- A named mutex (`CreateMutexW`) is an alternative on Windows, but `QLockFile` keeps
  it one cross-platform code path (Windows + macOS together — #92 wants both).

### Don't let the uv launcher trip it
`uv run` / the installed tool spawn a **parent stub + child** (the parent is a
1-thread, ~3 MB launcher that re-execs; only the child runs `_run_daemon`). The
guard lives in `_run_daemon`, which the stub never reaches, so the stub won't
acquire/contend the lock. Confirm with a process check after launch (expect exactly
one high-thread-count daemon).

### Installer (upgrade path — the real user trigger)
Most likely real-world cause is **upgrade**: a new version installed while the old
daemon is still in the tray, then autostart/relaunch → old + new concurrently until
reboot. The install path should **stop a running daemon before swapping files**
(`install.sh` already `pkill`s in the QA loop; add the Windows equivalent). This ties
into the active cross-platform install work (ADRs 0011–0014).

### Optional UX
When a second launch is blocked, flash/notify the existing instance's tray
("Dictatem is already running") instead of dying silently.

## Acceptance
- With the daemon running, launching again (any host exe) → **no** second tray icon,
  **no** second hook, second process exits with the log line.
- Stale lock from a crashed daemon does **not** block a fresh start.
- Windows boot smoke (touches the shared `_run_daemon` path) + a macOS launch check.

## Verify the original symptom is gone
After the guard lands: with a daemon already running, `uv run python -m dictatem`
should exit immediately; one dictation pastes exactly once and leaves the clipboard
unchanged.
