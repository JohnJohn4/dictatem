# The daemon owns autostart, reconciling the OS entry to the config flag

`config.startup.autostart` has existed (default `True`) and been documented since
the config landed, but **nothing acted on it** — no Run key, no LaunchAgent. The
flag was dead: Dictatem did not actually start at login. The cross-platform
install work is where we make it real, and we make the **daemon** own it, not the
installer.

On each launch the daemon **reconciles** the OS autostart entry to
`config.startup.autostart` — registering it when the flag is true and the entry
is missing, removing it when the flag is false and the entry is present — via a
new `AutostartRegistrar` Protocol in `interfaces.py` with a per-OS adapter
(Windows `HKCU\…\CurrentVersion\Run` key; macOS `~/Library/LaunchAgents` plist).
A tray "Start at login" toggle flips the same flag. The config is the single
source of truth, mirroring ADR-0007's "reconcile config to reality on launch"
shape. Default stays `True`.

## Considered options

- **Installer writes the Run key / LaunchAgent.** Simple, but splits ownership:
  the flag stays decorative and any later daemon logic (or a tray toggle) drifts
  from what the installer wrote. Two writers, no source of truth.
- **Daemon reconciles to the flag (chosen).** One owner, the flag finally means
  something, the tray toggle and config agree by construction, and it fits the
  existing Protocol-adapter seam so macOS is "add an adapter," not a redesign.
- **Flip the default to opt-in (`autostart=False`).** Considered, rejected: a
  dictation daemon is meant to be always available, and the product already
  defaulted the flag on. Kept default-on with clean removal on uninstall.

## Consequences

- New `AutostartRegistrar` Protocol joins the other OS-surface Protocols; the
  win32 adapter ships with the Windows track, the macOS LaunchAgent adapter with
  the Mac track. Like the other native adapters it is manual-QA only (excluded
  from pyright/tests); the reconcile *decision* (flag + current-entry → action)
  is pure and unit-tested.
- Uninstall must remove the autostart entry **before** `uv tool uninstall`
  (ADR-0011), otherwise the OS entry is orphaned, pointing at a deleted command.
- The entry points at the `gui-scripts` launcher (ADR-0011), so autostart runs
  the same windowless command as a manual launch — on **both** platforms.

  *Revised after real-Mac QA (#54).* The macOS entry originally launched the
  generated `.app` via `/usr/bin/open -g`, on the theory that a LaunchServices
  launch would attribute TCC grants to the bundle. QA disproved both halves:
  the grant attributes to the interpreter (`python3.12`) regardless (ADR-0014
  amendment, #91), and — decisively — launching *through* the bundle makes the
  daemon process inherit the bundle's LaunchServices identity, which macOS then
  **refuses to render a menu-bar status item for** (the tray icon never
  appeared; a directly-launched, non-bundle process shows it fine). So the
  LaunchAgent now launches the **uv-installed launcher directly**
  (`macapp.bundle.launch_arguments` returns `[launcher]`), exactly like the
  win32 Run key, and `launchd` itself provides the single-instance guarantee
  the `open`-launch was relied on for. The `.app` survives only as the icon /
  identity shell and the future home of a signed bundle (#91).
