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

These two failures split cleanly once tested on a real Mac (#61), and only one
is fixable within this ADR's no-signing posture.

The **Rosetta mislaunch** is fixed: `install.sh` pins the tool environment to a
**uv-managed CPython** (`--managed-python --python <CI-tested version>`) — a
plain, single-arch arm64 binary with no x86_64 slice to mislaunch — and the
shim's `proc_translated` re-exec guard backs it up for a manually-run
`--install-macos-app` against some other universal interpreter. QA confirmed the
boot crash is gone: the daemon launches, the menu-bar icon appears, no Intel
warning.

The **identity** problem is NOT fixed by the pin, and QA proved it: the managed
interpreter still presents to TCC as `python3.12` (generic icon) in the
Accessibility and Input Monitoring panes — not "Dictatem". The cause is deeper
than which interpreter runs: TCC attributes Accessibility / Input Monitoring to
the **binary that calls the gated API**, keyed on its code signature, and the
daemon's calls come from the Python interpreter the `.app` shim execs into. A
locally-generated, unsigned (or ad-hoc-signed) shell-shim bundle cannot override
that — ad-hoc `codesign --force --deep -s -` on the bundle was tested on the QA
Mac and the panes still read `python3.12`. The only thing that makes the calling
process present as "Dictatem" is a **code-signed bundle that owns the
interpreter** (the Developer-ID-signed, py2app-style bundle Espanso and
Hammerspoon ship) — exactly the signing tax ADR-0011 rejected, and even those
tools have TCC-identity pain on macOS 26.

**Accepted limitation (this revises the ADR's headline claim).** Dictatem ships
with the `python3.12` label rather than holding go-live for a signed bundle. The
grant is functional and, because the pinned managed interpreter is byte-stable
across `uv tool upgrade`, it *survives upgrades* — only the displayed name and
icon are wrong. An ad-hoc local bundle would be worse (content-hash identity
churns on regeneration, breaking the grant every upgrade). A clean
Developer-ID-signed bundle is tracked as a future enhancement (#91). The `.app`
shell still earns its place even with the wrong label: a Spotlight/Finder launch
target, single-instance launch via LaunchServices, `LSUIElement`, and the
autostart identity the LaunchAgent launches.

Rejected deeper fix: a tiny native Mach-O trampoline as `Contents/MacOS` would
give LaunchServices a real architecture header, but compiling one at install
time triggers the Xcode CLT prompt ADR-0015 exists to avoid, and shipping a
prebuilt binary is the distributed-artifact posture ADR-0011 rejects (ad-hoc
`codesign` on the script adds no arch header and fixes nothing here). The
guard hardcodes `arch -arm64` because no truthful native-arch query exists
from inside a translated process — `uname -m` and `hw.machine` both report
x86_64 under Rosetta — and `proc_translated=1` today only ever means
x86_64-on-arm64.
