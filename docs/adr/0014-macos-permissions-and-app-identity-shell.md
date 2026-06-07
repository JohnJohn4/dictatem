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
