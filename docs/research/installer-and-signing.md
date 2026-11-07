# Installer and signing options for non-technical users (#320)

*Researched 2026-11-07 for v1.1 (about three weeks after the 8 Nov 2026
launch, so roughly 29 Nov 2026). Every web source was accessed on 2026-11-07.
Microsoft Learn `ms.date`/`updated_at` stamps are given where the page has
them. Repo facts are cited by path. **[measured]** marks something checked
on the research machine (Windows 11 x64, uv 0.11.16, a v0.8.x GPU install).
**[inference]** marks a conclusion drawn from sources rather than stated by
one.*

## The short version

- **Windows: ship a thin, signed Inno Setup bootstrapper.** It is about
  2–5 MB, per-user and needs no admin rights. It embeds the tag's
  `install.ps1` and runs it, so the result is the exact `uv tool` layout we
  have today, and the in-app **Check for updates…** keeps working untouched.
  Sign it with **Azure Artifact Signing** (US$9.99/month) under **MATAVEX PTY
  LTD**. Australian *organisations* are now on the eligible list, and
  Artifact Signing does not need a D-U-N-S number. Australian *individuals*
  are not eligible. If MATAVEX's validation fails (most likely if the company
  is under three years old), fall back to an OV certificate (about
  US$129/year plus cloud-HSM signing). Bundling the venv, MSIX, the Store and
  winget all lose for v1.1.
- **macOS: ship a signed, notarised `.pkg`, layered on the #227 App
  Launcher.** The `.pkg` places the Developer-ID-signed `Dictatem.app` and
  runs the same `uv tool install` as the logged-in user (the Homebrew `.pkg`
  pattern). It then hands the daemon to launchd. Prefer it to a `.dmg`,
  because a `.dmg` can only copy an app and can't run the uv install. The
  certificate reads "MATAVEX PTY LTD" once Apple approves the organisation
  enrolment, which is blocked on the pending D-U-N-S.
- **What's realistic for v1.1:** the Windows installer, *if* the owner starts
  Artifact Signing validation now. Validation takes 1–20 business days, so
  everything else fits in about a week of work. On macOS, v1.1 can carry the
  App Launcher (#254/#258) if Apple approves in time. The `.pkg` on top of it
  is probably v1.2. Don't ship an **unsigned** `.exe`. On Windows 11 with
  Smart App Control on, an unsigned app with no reputation is blocked, and
  there is no per-app override. That is worse than the one-liner.

---

## 1. Where we are today (repo)

- **Install** is a user-run script, `irm …/install.ps1 | iex` or
  `curl … | sh`. It installs uv if it is missing. It pins a uv-managed CPython
  and runs `uv tool install "dictatem[<extra>] @ <tag tarball>"`. On Windows
  it picks `runtime-gpu` or `runtime` by probing for an NVIDIA GPU, and on
  ARM64 it pins an x64 CPython 3.11.
  ([ADR-0011](../adr/0011-install-via-thin-uv-tool-script.md),
  [ADR-0015](../adr/0015-install-from-tag-tarball-not-git-url.md),
  [ADR-0017](../adr/0017-windows-on-arm-installs-under-x64-emulation.md),
  `install.ps1`, `install.sh`.)
- **Updates** run through `src/dictatem/upgrade/`:
  - The tray reads GitHub `releases/latest` (`github.py`, `core.py`).
  - On **Windows** (`UpdateMode.IN_APP`), after explicit consent,
    `win32_upgrader.spawn_upgrade` opens a detached PowerShell that re-runs
    the pinned `install.ps1` at the new tag.
  - On **macOS** (`UpdateMode.MANUAL`, `prompt.py`), the user gets the pinned
    `curl … install.sh | sh` command to copy.
  - Both paths depend on one fact: **re-running the installer script is the
    upgrade**.
- **macOS identity.** The shipped `.app` is an unsigned placeholder, and the
  TCC panes list "python3.12" (ADR-0014 amendment). Spec #227 replaces it
  with a Developer-ID-signed, notarised **App Launcher**. The launcher is a
  native binary that *spawns* the uv-installed daemon as a child, so TCC
  attributes Accessibility, Input Monitoring and Microphone to "Dictatem".
  - The grant binds to Team ID + `com.dictatem.daemon`.
  - The ADR amendment is PR #264. It is still **open, not merged**.
  - #253 (Apple account and secrets), #254 (launcher) and #258 (CI
    sign/notarise) are open with no progress comments.
  - #253 records an **organisation** enrolment for MATAVEX PTY LTD, with
    D-U-N-S pending (Apple case 103014763435).
  - The wizard `scripts/wizards/macos-signing-setup.sh` creates only a
    **Developer ID Application** certificate (it tells the user "NOT
    'Developer ID Installer'").
- **Licence.** The repo has no `LICENSE` file and `pyproject.toml` declares
  no licence. That matters for SignPath Foundation (§2.4).
- **Sizes [measured].**
  - The installed GPU tool env is **2,490 MB**: `nvidia/` 2,011 MB, PySide6
    209 MB, ctranslate2 61 MB. This matches the ~2.5 GB in the ticket.
  - `uv.exe`, uv's managed `python.exe` (python-build-standalone) and the
    generated `dictatem.exe` trampoline in uv's tool-bin dir are all
    **Authenticode-unsigned**.
  - The trampoline is a 47 KB exe, built locally by uv.

## 2. Windows

### 2.1 SmartScreen and Smart App Control: what signing buys

- **Unsigned download.** "Windows protected your PC". The user must choose
  More info › Run anyway, and enterprise policy can remove that choice
  entirely. Reputation starts at zero for every new version.
  ([SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation),
  ms.date 2026-05-04, updated 2026-08-17.)
- **Signed (OV, EV or Artifact Signing), new publisher.** There is *still* a
  warning until reputation accumulates, but the **verified publisher name is
  displayed**. Microsoft says: "There is no exact threshold, but it can take
  several weeks and hundreds of clean installs." Signing every release with
  the **same identity** lets reputation carry across versions. Unsigned
  files "must build reputation anew with every update". (Same page.)
- **EV no longer bypasses SmartScreen** (since 2024): "Paying a premium for EV
  solely to avoid SmartScreen warnings is no longer justified."
  ([SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation);
  [Code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options),
  ms.date 2026-08-29.)
- **Smart App Control (Windows 11)** is stricter than SmartScreen. It
  consults cloud reputation first. If that can't vouch for the app, it lets
  the app run only if it has a valid signature. Microsoft says "there is no
  way to bypass Smart App Control for an individual app."
  ([What is Smart App Control](https://support.microsoft.com/en-us/topic/what-is-smart-app-control-285ea03d-fa88-4d56-882e-6698afdb7003).)
  Its signature checks apply to **all** executables, not just downloaded
  ones (the tip on the SmartScreen page above).
  - **[inference]** An *unsigned* Dictatem `Setup.exe` would be blocked
    outright on SAC-on machines. A *signed* one would run.
  - **Separate, pre-existing risk:** the unsigned, per-machine
    `dictatem.exe` trampoline uv generates has no cloud reputation by
    construction. On a SAC-on machine it may already be blocked under
    today's one-liner. Signing our installer does not change this, because
    we don't build that file. **Worth one QA pass on a SAC-on Windows 11
    box.**
- **Why the one-liner sees no SmartScreen at all.** A script piped into
  `iex`, and files fetched by uv's own HTTP client, carry no
  Mark-of-the-Web. A browser-downloaded `.exe` does.
  - **[inference]** This is ADR-0011's original rationale. It also means an
    installer that fetches its payload itself only has to sign the outer
    `.exe`.

### 2.2 Installer formats compared

| Option | Size | Upgrade fit | Verdict |
|---|---|---|---|
| **Thin bootstrapper** (Inno Setup, or a custom exe) that runs `install.ps1` | ~2–5 MB; payload downloads at install | Same `uv tool` layout, so the in-app updater keeps working unchanged | **Recommended** |
| **Inno Setup/NSIS bundling a prebuilt venv** | GPU ≈ 2.5 GB [measured] | Forks the install path away from the updater | Rejected |
| **MSIX** (sideload or Store) | Payload must be inside the package | Container virtualisation breaks uv and autostart assumptions | Rejected for v1.1 |
| **winget** | Manifest only; points at our installer | Still a terminal command | Later, as a channel, not a replacement |
| **Microsoft Store (EXE path)** | Must be an *offline* installer | Bootstrapper not allowed | Not viable with a bootstrapper |

**Thin bootstrapper (recommended).**
- Inno Setup supports per-user non-admin installs, signed installers and
  uninstallers, and single-exe output, with about 2 MB of overhead
  ([Inno Setup](https://jrsoftware.org/isinfo.php)).
- Its free licence *requests* that commercial users buy a licence, but "it
  is not strictly required" ([ordering FAQ](https://jrsoftware.org/isorder.php)).
  The price is not shown on that page; budget for one Single User licence.
- The installer embeds the tag's `install.ps1` and runs it with
  `-ExecutionPolicy Bypass -File`, so the script is not fetched at run time.
  Output is the byte-identical `uv tool` layout, GPU detection and ARM64
  emulation pin included, so ADR-0011/0015/0017 all stay true.
- A custom bootstrapper (Rust, Go or C#) could show a nicer download-progress
  UI. It would cost more code, and it would have to rebuild what Inno gives
  for free: the Add/Remove Programs entry, the uninstaller, Start-menu
  wiring and SignTool hooks.

**Bundling a prebuilt venv (rejected).**
- The GPU env is 2,490 MB [measured]. That is over NSIS's practical
  ~2 GB ceiling ([NSIS wiki](https://nsis.sourceforge.io/I_get_an_error_when_compiling_large_installers)).
  It is also over GitHub's hard **2 GiB per release asset** limit
  ([About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)).
- Inno Setup only needs disk spanning above 4.2 GB
  ([DiskSpanning](https://jrsoftware.org/ishelp/topic_setup_diskspanning.htm)),
  but the GitHub limit would still force a split, multi-file download.
- You would need a CPU build and a GPU build, a per-release build of
  2.5 GB of CUDA wheels, and a venv relocated to the user's path.
- Worst, it **forks the install path**: the in-app updater re-runs
  `install.ps1`, which would then manage an env it didn't create.
- It buys no SmartScreen benefit over a signed thin installer, because only
  the outer downloaded file is assessed.

**MSIX (rejected for v1.1).**
- Packaged full-trust desktop apps are **virtualised**. New files under
  `AppData` (Local and Roaming) are redirected to a private per-package
  location, HKCU writes are copy-on-write into a private hive, and the
  package itself is read-only
  ([How packaged desktop apps run](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes),
  ms.date 2026-09-30).
- **[inference]** That collides with three things:
  - uv's tool and Python directories under `%APPDATA%\uv`
    ([measured] path `…\AppData\Roaming\uv\python\…`);
  - the daemon-owned HKCU autostart entry (ADR-0012,
    `autostart/win32_registrar.py`);
  - "re-run `install.ps1`" as the upgrade path.
- An MSIX would have to carry the whole env, and it still needs signing (or
  the Store).
- The Store's free MSIX re-signing with no SmartScreen
  ([Code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options))
  is attractive in principle, but it requires a rewrite to a bundled,
  Store-updated app.

**winget (later).**
- winget accepts EXE/INNO/NULLSOFT/MSI/MSIX installers
  ([WinGet overview](https://learn.microsoft.com/en-us/windows/package-manager/winget/),
  ms.date 2026-07-19).
- Repository policy 1.2.1 forbids a product that downloads "a remote script
  and subsequently execute[s] that script in a manner that is not
  consistent with the described functionality". An honestly described
  bootstrapper is arguably consistent, but expect review friction.
  `InstallerUrl` must be our own release location
  ([winget policies](https://learn.microsoft.com/en-us/windows/package-manager/package/windows-package-manager-policies),
  ms.date 2026-08-30).
- It is still a terminal command, so it doesn't serve the non-technical
  user. It is a cheap add-on once a signed `Setup.exe` exists.

**Microsoft Store, EXE path (not viable).**
- The Store accepts signed EXE/MSI submissions, but the installer must be "a
  standalone installer and … not a downloader stub/web installer"
  ([MSI/EXE package requirements](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/app-package-requirements),
  updated 2026-08-24). A thin bootstrapper is excluded by definition.

### 2.3 Code-signing options and eligibility (AU sole trader vs MATAVEX PTY LTD)

| Option | AU sole trader | MATAVEX PTY LTD | Name shown | Cost (USD) | CI fit |
|---|---|---|---|---|---|
| **Azure Artifact Signing** (formerly Trusted Signing) | **Not eligible**: individuals must be in the US or Canada | **Eligible on paper**: Australia is listed for organisations. Years-in-business rule unclear (below) | Validated legal name, e.g. "MATAVEX PTY LTD"; no custom CN/O | Basic **$9.99/mo** (5,000 signatures); Premium $99.99/mo; overage $0.005/signature | GitHub Action, OIDC, Windows runners only |
| **OV certificate** (e.g. SSL.com, DigiCert, Sectigo) | No: OV needs a registered legal entity | Yes | Company name | SSL.com **$129/yr** (from $96.75/yr on 5-year terms); Microsoft quotes $150–300/yr | Key must sit in an HSM (CA/B rule since June 2023), so add cloud signing, e.g. SSL.com eSigner **$20/mo** for 20 signings |
| **IV (individual) certificate** | **Yes** ("no business entity required") | n/a | Owner's personal name | SSL.com $129/yr (search snippet; not confirmed on the live page) | Same HSM/eSigner constraint |
| **EV certificate** | Sole-proprietor EV exists at some CAs | Yes | Company name | $400+/yr | No SmartScreen advantage since 2024; Artifact Signing doesn't issue EV |
| **SignPath Foundation** (free for OSS) | **Not eligible** | **Not eligible** | "SignPath Foundation", not us | Free | n/a |

Artifact Signing detail:
- **Eligible countries.** The service's own quickstart says: "Public Trust
  certificates are available to organizations in the United States, Canada,
  the European Union, the United Kingdom, **Australia**, New Zealand,
  Japan, … Individual developers must be located in the United States or
  Canada"
  ([quickstart](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart),
  ms.date 2026-05-21, updated 2026-10-08).
  - **Conflict:** the Windows-apps page still lists only USA, Canada, EU
    and UK for organisations
    ([code-signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options),
    2026-08-29). The service's own page is newer and authoritative.
    Confirm in the portal's country drop-down.
- **What validation asks for.** Organisation validation asks for a
  "Business Identifier" (for MATAVEX, the ACN/ABN), a website, a monitored
  email on the company's domain, and a representative's Verified ID (AU10TIX
  plus Microsoft Authenticator).
  - It does **not** ask for a D-U-N-S, so it is independent of Apple's
    D-U-N-S wait.
  - Documents must be issued within the previous 12 months.
  - Processing takes "1 to 20 business days".
  - You get three attempts at extra documents, and a failure "can't" be
    retried on the same request. (Same quickstart.)
- **Years in business: undocumented and unresolved.** A preview-era rule
  required "three years or more of verifiable history". The GA docs no
  longer state it. Microsoft Q&A threads from Aug–Oct 2026 report young
  companies (one a 2y8m-old Portuguese Lda, another a newly formed US LLC)
  failing with no reason given, and no staff answer.
  ([Q&A 5979123](https://learn.microsoft.com/en-au/answers/questions/5979123/artifact-signing-organization-identity-validation),
  [Q&A 6042852](https://learn.microsoft.com/en-us/answers/questions/6042852/artifact-signing-public-organization-validation-fa).)
  **Treat a company under three years old as at real risk of rejection.**
  Have the OV fallback ready.
- **Cost and billing.** Prices come from Microsoft's first-party Retail
  Prices API, product "Trusted Signing": Basic Account $9.99/month, Premium
  Account $99.99/month, Signature Overage $0.005
  (`https://prices.azure.com/api/retail/prices?$filter=contains(productName,'Signing')`).
  The marketing pricing page
  ([Artifact Signing pricing](https://azure.microsoft.com/en-us/pricing/details/artifact-signing/))
  renders client-side. Billing is not pro-rated. A **paid** Azure
  subscription is required; free, trial and sponsored subscriptions are
  rejected
  ([FAQ](https://learn.microsoft.com/en-us/azure/artifact-signing/faq),
  updated 2026-10-27).
- **Name on the certificate.** No custom CN/O: "CN values must always be the
  legal entity's validated name" (FAQ). So the publisher shows as MATAVEX
  PTY LTD, which is what the owner wants.
- **CI.** [`Azure/artifact-signing-action`](https://github.com/Azure/artifact-signing-action)
  supports OIDC and runs on `windows-2022`/`windows-2025` only. Certificates
  are short-lived and held by the service; you never hold a key file.

OV and IV detail:
- SSL.com prices are on its
  [code-signing purchase page](https://www.ssl.com/certificates/code-signing/buy/)
  and [eSigner pricing](https://www.ssl.com/guide/esigner-pricing-for-code-signing/).
- Microsoft calls OV "functionally equivalent to Azure Artifact Signing for
  SmartScreen purposes"
  ([code-signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)).

SignPath Foundation detail:
- It requires an "OSI-approved Open Source license without commercial
  dual-licensing" and no proprietary components, and SignPath Foundation is
  named as the publisher ([SignPath terms](https://signpath.org/terms)).
- Dictatem has no licence file, and the owner wants MATAVEX named. **Ruled
  out** on both counts.

**Recommendation.** Use MATAVEX PTY LTD with **Artifact Signing Basic**.
Fall back to an **SSL.com OV certificate plus eSigner** (about US$129/yr +
US$240/yr) if validation fails. A sole-trader route only gets an IV
certificate in the owner's personal name, at the same price as OV, so the
company route dominates.

### 2.4 How the Windows installer coexists with uv and the updater

- **The installer must not change the layout.** It runs the tag's
  `install.ps1` verbatim, with no custom `UV_TOOL_DIR` or `UV_INSTALL_DIR`.
  Then `win32_upgrader.spawn_upgrade` (which re-runs `install.ps1` at the
  next tag) upgrades an installer-installed copy exactly like a one-liner
  copy. The reverse also holds. **No change is needed in `upgrade/` for
  v1.1.**
- **Who owns the Add/Remove Programs entry.** If Inno owns it,
  `DisplayVersion` goes stale after the first in-app update.
  **[inference]** Better: set Inno to `Uninstallable=no`, and have
  `install.ps1` write and refresh a per-user
  `HKCU\…\Uninstall\Dictatem` entry on every run. Its `UninstallString`
  runs `dictatem --uninstall` then `uv tool uninstall dictatem` (README
  "Uninstalling"). One-liner users then get an Apps & Features entry too.
- **Running the script.** Run it visibly, in the same console window the
  in-app updater already opens, so the multi-minute CUDA download shows
  progress. Alternatively, capture it to a log and show a "this can take
  several minutes" page. Keep the first launch through `Start-Process
  dictatem` as now.
- **Later (v1.2+).** The updater could download the signed
  `Dictatem-Setup-vX.exe` and verify that its Authenticode signer is
  MATAVEX before running it. That is optional, since re-running the script
  already works.

**Effort.** About **3–5 dev days**:
- the Inno script, with `install.ps1` embedded at the tag;
- the HKCU uninstall entry in `install.ps1`, plus a static contract test;
- a `windows-2025` release job that builds, signs (Artifact Signing
  action, OIDC), and uploads `Dictatem-Setup-<tag>.exe` under the 2 GiB
  limit;
- README copy;
- manual QA on a clean VM, on ARM64, and on a SAC-on machine.

Owner-only steps: a paid Azure subscription, identity validation (wait 1–20
business days), and a federated credential for GitHub OIDC. An agent could
script these with the wizard skill.

## 3. macOS

### 3.1 Apple Developer Program: individual vs organisation

- **Price.** US$99 per membership year, "prices may vary by region and are
  listed in local currency during the enrollment process"
  ([Enroll](https://developer.apple.com/programs/enroll/);
  [What's included](https://developer.apple.com/programs/whats-included/)).
  Membership includes Certificates, Identifiers & Profiles, where Developer
  ID certificates are made.
- **Individual or sole trader.** A sole trader enrols as an individual, with
  an Apple Account under their legal name. No D-U-N-S is needed. The
  person's own name is shown as the developer (Enroll page;
  [D-U-N-S help](https://developer.apple.com/help/account/membership/D-U-N-S/)).
  For Developer ID, the personal name appears in the certificate, in
  Gatekeeper dialogs and in Login Items (#227 owner note).
- **Organisation (MATAVEX PTY LTD).** The organisation must be a legal
  entity ("We do not accept DBAs, fictitious business names, trade
  names"), with a D-U-N-S, a domain email and a public website, and the
  enroller must have binding authority.
  - D-U-N-S timing: "allow up to 5 business days to receive your number
    from D&B" (expediting doesn't help), then "up to 2 business days" before
    Apple can see it.
  - The certificate then reads `Developer ID Application: MATAVEX PTY LTD
    (TEAMID)` (#253).
- **Certificates.** Developer ID **Application** signs apps and Mach-O;
  Developer ID **Installer** signs `.pkg`. You can have up to five of each.
  The Account Holder creates them, or an admin with the cloud-managed
  Developer ID role
  ([Create Developer ID certificates](https://developer.apple.com/help/account/certificates/create-developer-id-certificates/)).
- **The current #253 wizard creates only the Application certificate.** A
  `.pkg` also needs an Installer certificate and two more secrets. This is a
  small addition to #253 and #258.

### 3.2 Notarisation requirements

From [Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution),
[Customizing the notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)
and [Resolving common notarization issues](https://developer.apple.com/documentation/security/resolving-common-notarization-issues)
(read through Apple's docs JSON):

- Since macOS 10.15, all Developer-ID-distributed software must be
  notarised.
- Requirements:
  - every executable is signed with a **Developer ID** certificate
    (Application for code, **Installer** for `.pkg`);
  - **Hardened Runtime** is on;
  - the signature carries a **secure timestamp**;
  - there is no `get-task-allow`;
  - entitlements are XML/ASCII.
- Deliverables can be apps, UDIF disk images and signed flat installer
  packages. Nested containers are processed, and a ticket is issued for
  each nested item. Use `notarytool`; `altool` stopped working on
  2023-11-01.
- Apple on network installers: "If you use a network installer, separately
  notarize both the installer and the items it downloads."
- Gatekeeper UX: since macOS Sequoia, users can't Control-click past an
  un-notarised app. They must go to System Settings › Privacy & Security ›
  Open Anyway
  ([Apple developer news, 2024-08-06](https://developer.apple.com/news/?id=saqachfa);
  [Safely open apps](https://support.apple.com/en-us/102445), 2026-05-27).
  That rules out shipping any *unsigned* downloadable `.app`, `.dmg` or
  `.pkg` to non-technical users.

**Can a signed bootstrapper install the uv tool layout without breaking
notarisation or permissions? Yes, with one honest caveat.**

1. **Notarisation of the installer is unaffected.** The notary service
   scans the submitted `.pkg` and its signed App Launcher. Scripts inside a
   `.pkg` are normal.
2. **What uv downloads isn't Gatekeeper-assessed**: CPython, wheels and
   their `.so`/`.dylib` files. Quarantine is something the *downloading
   app* opts into; `LSFileQuarantineEnabled` controls "whether the files
   this app creates are quarantined by default"
   ([Apple reference](https://developer.apple.com/documentation/bundleresources/information-property-list/lsfilequarantineenabled)).
   **[inference]** uv's HTTP client doesn't set quarantine, which is
   exactly why today's `curl | sh` works. So the payload behaves the same
   whether `install.sh` or a `.pkg` postinstall runs uv.
   - **The caveat:** this falls short of Apple's "notarize the items it
     downloads" advice. It is the same documented residual as #227 ("the
     signature seals the launcher bundle … not the uv tool environment").
     Say so in the ADR. Don't claim more.
3. **Permissions are unaffected by *how* the files arrive.**
   - The TCC grant binds to the App Launcher's designated requirement (Team
     ID + `com.dictatem.daemon`), not to its path or installer (#227). A
     `.pkg` install and an `install.sh` install produce the same identity,
     and switching between them costs no grants.
   - The hardened runtime binds only the launcher, not its spawned Python
     child, so the PySide6 and ctranslate2 wheels load without
     `disable-library-validation` (#227).
   - **One trap:** the `.pkg` must **not** start the daemon as a child of
     Installer. That would make Installer the responsible process for the
     first TCC prompts. Instead, bootstrap the LaunchAgent into the user's
     GUI domain so the chain is launchd → App Launcher → daemon, as #227
     intends. This is the same concern as the "terminal-parented first-run
     launch" (#213).

### 3.3 `.dmg` vs `.pkg`

**`.dmg` (drag `Dictatem.app` to Applications).**
- It is a familiar Mac idiom and can be notarised and stapled.
- But a `.dmg` **only copies files**. The Python daemon would have to be
  installed by the app on first launch. The #227 App Launcher contract is
  frozen to "spawn the recorded target; if missing, log one line and exit
  non-zero; never run anything else". So a `.dmg` needs either a contract
  change or a second, signed "Install Dictatem" helper app.
- The app also lands in `/Applications`, not the `~/Applications` that
  `install.sh` and `macapp.bundle` manage, so the adoption logic gains a
  second path.

**`.pkg` (Installer.app wizard). Recommended.**
- It is signed with Developer ID Installer and notarised and stapled.
- The payload is the already-notarised App Launcher. A `postinstall` script
  runs the bundled `install.sh` logic **as the logged-in user**.
- This is exactly how Homebrew's official `.pkg` works. Its
  [postinstall](https://raw.githubusercontent.com/Homebrew/brew/main/package/scripts/postinstall)
  runs as root, resolves the console user, refuses to proceed as root,
  runs work through `sudo -u "$user"`, and `chown`s the result. Its
  [Distribution.xml](https://raw.githubusercontent.com/Homebrew/brew/main/package/Distribution.xml)
  is a minimal `customize="never"` installer.
- The alternative is a home-directory install domain
  (`enable_currentUserHome`), which runs "as the current user (not as
  root)" and "cannot write outside of the home directory"
  ([Distribution XML reference](https://developer.apple.com/library/archive/documentation/DeveloperTools/Reference/DistributionDefinitionRef/Chapters/Distribution_XML_Ref.html),
  2012). It is cleaner on paper, but the archive doc is old and the
  "Install for me only" UI is less familiar. **[inference]** Prefer the
  Homebrew pattern.
- During the uv download, Installer only shows "Running package scripts…".
  Put the expected time on the welcome or conclusion page.

### 3.4 How it coexists with uv and the updater

- The `.pkg` runs the same `install.sh` logic, so the tool layout (uv's
  default `~/.local/…` paths) and `~/Applications/Dictatem.app` are
  identical.
- The existing MANUAL update prompt (`curl … | sh`) keeps working for
  `.pkg` users unchanged. `install.sh` also refreshes the App Launcher per
  #227.
- **Phase 2 of #193 becomes easy.** The tray downloads the tag's signed
  `.pkg` and verifies it with `pkgutil --check-signature` (Team ID pinned)
  or `spctl -a -t install`. **[inference]** The app must check this
  itself, because a file it downloads isn't quarantined and Gatekeeper
  won't. Then it opens the `.pkg` in Installer, so the user consents in a
  familiar UI.

**Effort.** On top of #254/#258 (the App Launcher, which is already scoped
work), about **3–5 dev days**:
- a `pkgbuild`/`productbuild` step in the #258 macOS release job;
- Developer ID Installer signing and notarisation of the `.pkg`;
- a postinstall that reuses `install.sh` as the console user and hands the
  daemon to launchd;
- the Installer certificate and secrets added to #253;
- real-Mac QA: clean install, upgrade over a one-liner install, grants
  persisting, and no TCC prompt attributed to Installer.

## 4. Recommendation and v1.1 scope

| | Windows | macOS |
|---|---|---|
| **Route** | Thin **Inno Setup** bootstrapper running the tag's `install.ps1`; per-user; owns nothing the updater doesn't | Signed, notarised **`.pkg`** around the #227 App Launcher; postinstall runs `install.sh` as the user and bootstraps the LaunchAgent |
| **Signing** | **Azure Artifact Signing Basic** as MATAVEX PTY LTD (US$9.99/mo); fallback SSL.com OV + eSigner (~US$370/yr) | **Developer ID** as MATAVEX PTY LTD (US$99/yr, already paid); add a **Developer ID Installer** certificate |
| **Dev effort** | 3–5 days | 3–5 days *after* #254/#258 (which are 1–2 weeks of their own) |
| **Owner HITL** | Paid Azure subscription, org identity validation (1–20 business days), OIDC credential | D-U-N-S issued, then Apple approval, then #253 wizard (+ Installer certificate) |
| **v1.1 (≈29 Nov)?** | **Yes**, if validation is started now and passes. If not, keep the one-liner and **don't** ship an unsigned exe | **App Launcher: maybe.** It depends on D-U-N-S and Apple approval, then #254's real-Mac gate. **`.pkg`: probably v1.2** |

Do now, in this order:
1. **Owner:** open a paid Azure subscription and submit **MATAVEX PTY LTD**
   organisation validation today. It is the long pole, and it doesn't need
   the D-U-N-S.
2. **Owner:** chase the D-U-N-S, then the Apple enrolment.
3. **Agent:** build the Inno bootstrapper and its CI job in parallel. The
   build can be exercised unsigned in CI; just don't publish it unsigned.
4. **Agent:** run the SAC-on QA check (§2.1) on today's one-liner. If uv's
   unsigned trampoline is blocked, that's a launch-relevant finding,
   independent of the installer.
5. **Record:** add an ADR-0011 amendment that narrows "no signed bundle" to
   "signed thin bootstrapper, no bundled runtime" on Windows too, matching
   the macOS narrowing in PR #264.

Open questions for the owner:
- When was MATAVEX PTY LTD registered (the three-year risk)?
- Is a ~US$370/yr OV fallback acceptable if Artifact Signing rejects it?
- Is a licence for the repo planned? It only matters if SignPath is ever
  wanted, and it isn't under the "show MATAVEX" goal.
