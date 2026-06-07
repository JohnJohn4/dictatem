# macOS permissions: a locally-generated .app shell gives TCC a stable identity

macOS gates everything Dictatem must do behind privacy permissions: **Input
Monitoring** for the global hotkey (CGEventTap), **Accessibility** for synthetic
keystrokes/backspaces and focus control (CGEvent/AXUIElement), and **Microphone**
for capture. Microphone is the familiar auto TCC prompt; Accessibility and Input
Monitoring must be granted manually in System Settings and require a relaunch.

The problem is *identity*. TCC binds a grant to a stable, identifiable
executable — ideally an `.app` bundle. But the thin `uv tool` install (ADR-0011)
leaves the daemon behind a launcher in `~/.local/bin` pointing into a venv
Python. Granting Accessibility/Input-Monitoring to *that* makes the user grant
"**Python**" (not "Dictatem") and a `uv tool upgrade` that moves the path can
silently void the grant. So on macOS the install script **generates a minimal,
unsigned `.app` launcher** in `~/Applications` (an `Info.plist` with a stable
bundle identifier + icon, and a `Contents/MacOS` shim that execs the
uv-installed daemon). TCC binds to the bundle identity, the user grants
"Dictatem", and the grant **survives upgrades**.

This is a deliberate refinement of ADR-0011, not a contradiction: we still ship
**no downloaded, signed bundle**. The `.app` is *generated locally* by a
user-invoked script, so — like the rest of the thin-script install — it never
hits Gatekeeper. The `.app` exists for permission identity and a Finder-visible
launch target, not as a distribution artifact. Windows needs none of this.

On first launch the daemon detects missing grants and shows a guided dialog.
Detection uses the CoreGraphics preflight pair — `CGPreflightPostEventAccess()`
for Accessibility (probing exactly what Dictatem does: posting synthetic events)
and `CGPreflightListenEventAccess()` for Input Monitoring — rather than
`AXIsProcessTrusted()`: the CG pair lives in the already-shipped Quartz binding,
so no `pyobjc-framework-ApplicationServices` dependency is added, and tap
creation failing remains the runtime backstop signal. The dialog deep-links into
the exact
System Settings panes (`x-apple.systempreferences:com.apple.preference.security?
Privacy_Accessibility` / `…?Privacy_ListenEvent`) and explains the one-time
relaunch. It never tries to grant on the user's behalf.

## Considered options

- **Grant to the interpreter, no `.app`.** Zero bundle machinery, but the user
  grants an executable shown as "Python", and the grant breaks whenever the
  interpreter path changes on upgrade. Confusing and fragile.
- **Locally-generated unsigned `.app` shell (chosen).** Stable TCC identity, a
  clear "Dictatem" entry, grants survive upgrades, and it stays within the
  no-signing posture because it is generated locally rather than downloaded.
- **Full signed bundled app.** Solves identity, but reintroduces the
  notarization/signing dependency ADR-0011 rejected. The shell gets the identity
  benefit without the signing cost.

## Consequences

- The macOS install script gains `.app` generation: bundle layout, a stable
  bundle identifier, the `.icns` from #35, and an exec shim into the uv-installed
  daemon. Windows install has no equivalent step.
- Uninstall on macOS must also remove `~/Applications/Dictatem.app` (and the
  LaunchAgent from ADR-0012), in addition to `uv tool uninstall`.
- First-run permission detection + the guided/deep-linked dialog is new macOS-only
  daemon code; like other native adapters it is manual-QA only. The decision of
  *which* permission is missing → *which* pane to open is pure and unit-testable.
- The autostart LaunchAgent (ADR-0012) should launch the `.app` (the identity
  TCC trusts), not the bare venv binary, so a login-started daemon keeps its
  granted permissions — via `/usr/bin/open -g` (see ADR-0012's consequences for
  the launch-mechanism rationale).

## Amendment (2026-06, real-Mac QA of #61): the shell needs a pinned interpreter

QA on macOS 26 (arm64) found two ways the identity shell silently loses to the
interpreter underneath it when `uv tool install` discovers a *system* Python
instead of provisioning its own:

- **Rosetta mislaunch.** A bundle whose `Contents/MacOS` executable is a shell
  script has no Mach-O header for LaunchServices to read architectures from,
  and LS launched the bundle under Rosetta (x86_64). `LSRequiresNativeExecution`,
  `LSArchitecturePriority` and `lsregister -f` re-registration were all ignored
  for the script-only bundle. The discovered python.org interpreter was a
  `universal2` binary, so the translated shim handed it its x86_64 slice and
  the daemon died importing arm64-only wheels — before logging. The shim now
  carries a `sysctl.proc_translated` guard that re-execs itself natively via
  `arch -arm64` (a no-op on Intel Macs, same-PID `exec` throughout).
- **Identity theft by the framework build.** python.org framework builds run
  through their embedded `Python.app` stub, so even when launched *through*
  `Dictatem.app`, the process TCC saw was the interpreter's own bundle: the
  privacy panes seeded "python3.14" (generic icon), the guided dialog wore the
  Python rocket, and a Dock tile appeared despite `LSUIElement` — the
  interposed stub's plist won. No plist key in our bundle can prevent this.

Both failures share one root: the shell only anchors identity if *the process
it execs has no competing identity*. So `install.sh` pins the tool environment
to a **uv-managed CPython** (`--managed-python --python <CI-tested version>`)
— a plain, single-arch, stub-free binary — making interpreter discovery, and
with it both failure modes, impossible on the supported install path. A
manually-run `--install-macos-app` against an arbitrary interpreter still gets
the Rosetta guard, but framework-build identity theft remains out of scope:
the supported answer is the pinned install.

Rejected deeper fix: a tiny native Mach-O trampoline as `Contents/MacOS` would
give LaunchServices a real architecture header, but compiling one at install
time triggers the Xcode CLT prompt ADR-0015 exists to avoid, and shipping a
prebuilt binary is the distributed-artifact posture ADR-0011 rejects (ad-hoc
`codesign` on the script adds no arch header and fixes nothing here). The
guard hardcodes `arch -arm64` because no truthful native-arch query exists
from inside a translated process — `uname -m` and `hw.machine` both report
x86_64 under Rosetta — and `proc_translated=1` today only ever means
x86_64-on-arm64.
