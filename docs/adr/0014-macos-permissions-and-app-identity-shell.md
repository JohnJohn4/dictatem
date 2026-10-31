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
Developer-ID-signed bundle is tracked as a future enhancement (#91).

A second QA finding (#54) forced a further retreat: the `.app` can no longer
even *launch* the daemon. Launching through the bundle makes the daemon process
inherit the bundle's LaunchServices identity, and macOS then silently refuses
to render its **menu-bar status item** — the tray icon never appeared under any
`.app`/`open`/Spotlight/login launch, while a directly-launched (non-bundle)
process showed it fine (proven with a native `NSStatusItem`, so it is not a Qt
bug). So every launch path now runs the uv-installed launcher **directly** (see
ADR-0012's revised consequence); the menu-bar accessory behaviour that
`LSUIElement` was meant to provide is set on the running process instead
(`TransformProcessType` → UIElement, in `macapp.activation`). The `.app` is thus
reduced to just the generated icon and the placeholder for the eventual signed
bundle (#91) — it no longer launches anything and is not the recommended launch
path. This means `--install-macos-app` keeps generating it, but `install.sh` and
the LaunchAgent both bypass it.

Rejected deeper fix: a tiny native Mach-O trampoline as `Contents/MacOS` would
give LaunchServices a real architecture header, but compiling one at install
time triggers the Xcode CLT prompt ADR-0015 exists to avoid, and shipping a
prebuilt binary is the distributed-artifact posture ADR-0011 rejects (ad-hoc
`codesign` on the script adds no arch header and fixes nothing here). The
guard hardcodes `arch -arm64` because no truthful native-arch query exists
from inside a translated process — `uname -m` and `hw.machine` both report
x86_64 under Rosetta — and `proc_translated=1` today only ever means
x86_64-on-arm64.

## Amendment (2026-10-31, #227/#252): a signed App Launcher becomes the Permission Identity

**Status: proposed. The owner reviews this before any implementation ticket
of #227 starts. It is confirmed only by the real-Mac QA gate below (#254).**

### Context

The accepted limitation above has a public-launch cost. A stranger's first
impression of Dictatem is a prompt to let "python3.12", with a generic icon,
read and type their keystrokes. The install output and the guided dialog have
to explain that "that entry is Dictatem", and that copy is exactly what makes
careful users stop. Three smaller problems have the same root cause:

- **No integrity on the shim (prelaunch review S-5).** The generated `.app` is
  unsigned and user-writable. Nothing proves it is ours or unmodified.
- **Grants are tied to the interpreter identity.** They survive an upgrade only
  because the pinned managed interpreter happens to be byte-stable. A full tool
  uninstall and reinstall, or uv refreshing its managed Python, can silently
  drop them (#91 QA).
- **Login Items and the permission panes show an interpreter, not the
  product.** Dock and accessory behaviour also depends on a runtime
  `TransformProcessType`, not on the bundle that should own it.

On 2026-10-31 the owner decided to pay for an Apple Developer ID. The owner is
enrolling as an **organization**, MATAVEX PTY LTD, and the D-U-N-S number and
Apple's approval are pending (#253). The locally generated shell can't carry a
Developer ID signature, because signing uses the owner's private key, which
must never be on a user's machine. So the signed identity has to be built,
signed, notarized and stapled once per release in CI, then downloaded and
verified by `install.sh`. That deliberately revises ADR-0011's posture and this
ADR's.

The mechanism that makes this work is the one the earlier amendment's
diagnosis points at. TCC attributes a gated call to the **responsible code**
behind the calling process, and for a child process macOS follows the
responsibility chain to the parent. This is why a Terminal-launched daemon
attributes its grants to Terminal (#56/#59). The earlier tests failed because
the shim **exec'd** the interpreter: after `exec`, the process's code identity
*is* the interpreter. A launcher that **spawns** the interpreter as a child, and
stays alive as its parent, keeps the responsibility on itself.

### Decision

Ship a Developer-ID-signed, notarized and stapled **App Launcher**,
`Dictatem.app`, as a per-release asset. It becomes Dictatem's macOS
**Permission Identity**, the name TCC lists Dictatem under.

- **What it is.** The bundle contains only the launcher, `Info.plist`, the
  icon and the code signature. The launcher is a tiny native universal
  (arm64 + x86_64) Mach-O. CI builds it for the project's minimum supported
  macOS (12) and signs it with Developer ID, hardened runtime and a secure
  timestamp. Its entitlements include `com.apple.security.device.audio-input`.
  Without it, a hardened-runtime responsible app is silently denied the
  microphone.
- **What it does.** When launchd starts it at login, it spawns the uv-installed
  daemon as a child in its own process group and stays as that child's parent.
  It forwards SIGTERM, SIGINT and SIGHUP, and exits with the child's status, or
  128 plus the signal number. It never execs, so it stays the responsible code,
  and TCC attributes Accessibility, Input Monitoring and Microphone to
  "Dictatem" with the Dictatem icon.
- **Why the grant now lasts.** The grant binds to the launcher's **designated
  requirement**: the Developer ID Team ID plus the permanent bundle identifier
  `com.dictatem.daemon`. It survives every upgrade of the launcher, the tool
  environment and the interpreter.
- **The child runs unchanged.** The child is not bound by the launcher's
  hardened runtime or library validation. The uv-installed CPython, PySide6 and
  ctranslate2 wheels load as they do today, and no
  `disable-library-validation` entitlement is needed. The Python daemon stays a
  thin `uv tool install` from the release tarball (ADR-0011/0015). Windows is
  untouched.
- **The launcher contract is frozen,** so an older launcher can always start a
  newer daemon:
  - It reads the target from a per-user **launch-target record** in
    Dictatem's state directory, written by `--install-macos-app`. If the record
    is absent it falls back to uv's default tool-bin location.
  - It takes no target from its arguments or the environment. The hardened
    runtime strips dynamic-loader injection variables.
  - It sets exactly one environment marker, which tells the daemon it is
    running under the App Launcher.
  - If the target is missing or not executable, it logs one line and exits
    non-zero. It never runs anything else.
  - It never becomes an `NSApplication`, so it has no Dock tile and no
    window-server connection. The child keeps today's accessory transform
    (`macapp.activation`).
- **The daemon adopts the bundle and never rewrites it.**
  `--install-macos-app` reads the bundle-kind key in the bundle's `Info.plist`
  at the canonical path and classifies it as absent, generated shell, or App
  Launcher.
  - **App Launcher:** it never writes inside the bundle, because that breaks
    the seal. It writes the launch-target record and points the
    start-at-login LaunchAgent at the launcher's executable.
  - **No App Launcher:** it generates the unsigned shell exactly as today. The
    generated shell never carries the bundle-kind key, so it can never be
    mistaken for a signed bundle.
- **One-time migration for upgraders.** Existing grants belong to
  "python3.12", so the first App-Launcher launch finds them missing. It shows a
  one-time migration variant of the guided permission dialog (#95/#210). The
  dialog tells the user to turn on "Dictatem" once, warns that macOS will ask
  for the microphone again, and says the old "python3.12" entry can be
  removed. Old interpreter entries are never reset automatically, because
  other tools may share that interpreter.

### The download trust chain

This refines ADR-0011's point that a checksum fetched from the same host is
circular.

1. **SHA-256 checksum.** This guards against corruption and truncation only.
   It is not an authenticity claim.
2. **Strict code-signature verification** (`codesign --verify --deep
   --strict`), plus the stapled notarization ticket where present.
3. **A designated-requirement check pinned to Dictatem's Team ID and
   `com.dictatem.daemon`.** This is the authenticity anchor. The Team ID is a
   constant in `install.sh`, which is itself served from the pinned,
   auditable tag. A bundle signed by anyone else fails, however valid its
   signature is.

Only a bundle that passes all three replaces `~/Applications/Dictatem.app`,
atomically (stage, then move). If the asset is missing or any step fails,
`install.sh` keeps an already-installed bundle that still verifies. If there
isn't one, it falls back to the generated unsigned shell and the direct-launch
path. Either way it prints one line saying which identity is in use, and it
never replaces a valid signed bundle with the fallback.

**Ad-hoc bundles are never installed by default.** Until the signing secrets
exist (#253), the release job publishes an ad-hoc-signed bundle under a
distinct asset name. `install.sh` takes it only behind an explicit QA opt-in.
An ad-hoc bundle's identity is its cdhash, which changes with every build.
Installing one by default would break every user's grants on every upgrade.

### Integrity: what the seal does and does not cover

- **Covered (closes review S-5).** The signature seals the launcher bundle.
  Changing any byte of it invalidates the signature, Gatekeeper and TCC stop
  honouring it, and a modified bundle cannot quietly inherit the user's grants.
- **Not covered (documented residual).** The seal does not cover the uv tool
  environment the launcher starts, which stays user-writable like any uv tool.
  A user-level process that can write that environment can still run code
  under Dictatem's grants. This is not a regression: today the same process
  could just as well rewrite the unsigned shim. The README states this
  residual plainly rather than overclaiming.

### QA gate and fallback order

Apple describes responsibility attribution as general but undocumented, so this
decision stands only once real-Mac QA confirms it. The gate runs in #254 with an
**ad-hoc** local build launched by a LaunchAgent pointed at the launcher. An
ad-hoc build is enough to prove the chain, because Developer ID only adds
upgrade stability. All four checks must pass:

1. The Accessibility and Input Monitoring panes list **"Dictatem"** with its
   icon, not "python3.12".
2. After the user grants and restarts, the grant applies to the **child's**
   hotkey (Input Monitoring) and paste (Accessibility).
3. The **menu-bar status item still renders.** This is the named risk. #54
   showed that launching through a bundle via LaunchServices (`open`) loses the
   status item. The App Launcher is exec'd directly by launchd, not opened
   through LaunchServices, and never registers as an application. Whether that
   avoids #54 is exactly what this check settles.
4. There is **no Dock tile.**

If any check fails, stop and fall back in this order:

1. **A signed launcher that loads libpython in-process.** This gives a direct
   identity that does not rely on the chain. It needs
   `disable-library-validation` to load the user's interpreter and extension
   modules, which weakens the integrity S-5 asks for.
2. **A fully embedded bundle (py2app/Briefcase style).** This is the
   strongest seal and the most conventional approach, at the cost of
   everything listed against it below.
3. **Keep the "python3.12" label** (the earlier amendment's accepted
   limitation) and stop #227.

### Considered options

- **Signed native App Launcher that spawns the daemon (chosen).**
  - Gains: "Dictatem" in every pane, grants that survive every upgrade, a
    sealed launcher and a small download. The uv-tool install path is kept,
    and library validation isn't weakened.
  - Costs: one signed release artifact, CI signing infrastructure, and
    reliance on attribution that is general but undocumented (carried as the
    QA gate).
- **Signed launcher that execs Python.** After `exec`, the process's identity
  is the interpreter. This is today's failure, and the earlier amendment's
  ad-hoc test confirmed it.
- **Fully embedded bundle.** The strongest seal, but it means a
  multi-hundred-MB artifact, signing every `.so`/`.dylib`, abandoning the
  uv-tool install and update path on macOS, and usually
  `disable-library-validation` (Briefcase's default). It is fallback 2.
- **Signed launcher that loads libpython in-process.** Direct identity without
  relying on the chain, but it needs `disable-library-validation`. It is
  fallback 1.
- **Self-contained ad-hoc bundle with a copied interpreter.** Needs no Apple
  account, but the cdhash identity churns on every build and breaks grants on
  every upgrade.
- **Keep the "python3.12" label.** This is the limitation being replaced. It
  stays as the last fallback.

### Evidence

- Apple DTS (Quinn) on responsible code following the child-to-parent chain,
  with a working Input Monitoring test in a child process:
  developer.apple.com/forums/thread/805245.
- The tcc-venv project: a signed spawn-not-exec trampoline that gives venv
  Pythons a stable TCC identity (pypi.org/project/tcc-venv).
- M. Tsai, "The Curious Case of the Responsible Process" (2025), on
  `responsibility_spawnattrs_setdisclaim` and inheritance.
- This repo:
  - Terminal-launched daemons attribute their grants to Terminal (#56/#59),
    which is the same chain.
  - The earlier amendment's ad-hoc-sign-plus-exec failure (#91) is the control
    case.

### Revised postures

- **ADR-0011's "no downloaded, signed bundle" narrows to "no bundled
  runtime".** Exactly one small signed artifact, the App Launcher, is
  downloaded. Python, PySide6 and the speech engine are still never bundled.
- **This ADR's "the `.app` no longer launches anything" is reversed for the
  signed App Launcher only.** The generated unsigned shell stays the fallback
  and keeps today's behaviour: icon placeholder plus direct launch.
- **The earlier "rejected deeper fix" (a native Mach-O trampoline) is
  reversed.** Both of its reasons are gone:
  - CI compiles the launcher, so users never see an Xcode CLT prompt
    (ADR-0015).
  - Shipping a prebuilt artifact is now allowed under the narrowed posture
    above.

  Being a native universal binary, it also closes the Rosetta-mislaunch class
  of bug (#61) for the signed path.

### Consequences

- **CI.** A new macOS release workflow runs on every published release (#256,
  #258). It can also be dispatched manually for an existing tag. It:
  - compiles the launcher and assembles the bundle;
  - signs inside to out, with hardened runtime and a timestamp;
  - notarizes with `notarytool --wait` and staples the `.app`;
  - uploads the archive plus its SHA-256 under stable, tag-independent asset
    names.

  Secrets live in a protected `release` environment and an ephemeral keychain
  that is deleted at job end. The private key never touches a laptop or a
  user's Mac.
- **Release checklist.** It gains a "wait for the signed asset" step. A
  release whose asset is late still installs, with the fallback identity.
- **`install.sh`.** It gains the download, the three-step verification, the
  atomic swap and the fallback (#257).
- **Uninstall.** It also removes the bundle and the launch-target record. It
  best-effort resets Dictatem's own TCC entries by bundle identifier, never
  the interpreter's (#260).
- **Daemon.** The adoption and Permission Identity decisions are pure,
  unit-tested logic (#255/#259). They are added to `macapp.bundle`, the
  autostart registrar, `macapp.plist` and `permissions.mapper`. Tray Restart's
  `launchctl kickstart -k` now restarts the launcher job, and process-group
  cleanup takes the child with it.
- **Signer name.** The enrollment is an organization, so the certificate reads
  `Developer ID Application: MATAVEX PTY LTD (TEAMID)`, and that name shows in
  Gatekeeper and Login Items. No personal name appears anywhere.
- **Manual QA.** The TCC, Gatekeeper and launchd behaviour is manual QA on a
  real Mac and is never mocked (`needs-real-mac-qa`).
