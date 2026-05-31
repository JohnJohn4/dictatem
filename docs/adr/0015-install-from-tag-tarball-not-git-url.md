# Install from the GitHub tag tarball over HTTPS, not a git+ URL

The provisioning scripts (ADR-0011) installed Dictatem with
`uv tool install "dictatem[<extra>] @ git+https://github.com/JohnJohn4/dictatem@<tag>"`.
`uv tool install` resolves a `git+` URL by **shelling out to the `git`
executable** to clone the repo before building it. That quietly makes **git an
undeclared prerequisite**: on a fresh machine without git the install aborts with
`Git executable not found. Ensure that Git is installed and available.` — even
though our only stated prerequisite is Python 3.11+ (uv brings the rest). This
bit a real user on a clean Windows machine (#71).

**Decision:** install from the tag's **source tarball over HTTPS** instead —
`"dictatem[<extra>] @ https://github.com/JohnJohn4/dictatem/archive/refs/tags/<tag>.tar.gz"`.
uv fetches the tarball with its own HTTP client (no git) and builds it with
hatchling. Dictatem is pure-Python (`py3-none-any`), so there is no compiler and
no git in the path — the build does byte-for-byte the same work as the git path,
minus the clone.

This is a deliberate refinement of ADR-0011's *transport*, not a contradiction of
its substance: still a thin, user-invoked `uv tool` script; still pinned to a
**readable release tag** (the tarball URL names the exact tag — the same audit and
trust story as a git ref, and a user can open the URL to inspect it); still no
signing, no bundle. GitHub already serves a tarball for every tag, so the release
process is unchanged (tag → GitHub release → bump the tarball tag and the README
one-liner URL together).

## Considered options

- **Tag tarball over HTTPS (chosen).** Removes the git prerequisite with a
  one-line installer change and zero new release machinery. The extras still
  resolve from the built metadata.
- **Keep the `git+` URL, document git as a prerequisite.** Pushes a manual
  install step onto every git-less user and undercuts the "one line, Python only"
  promise. Rejected.
- **Bundle PortableGit / MinGit in the installer** (as some installers do).
  Removes the prerequisite, but adds a ~50 MB download plus PATH wiring to
  maintain — and we only need git *transiently* for a clone the tarball removes
  entirely. Worth it only for installers that keep a live git working tree; ours
  does not. Rejected.
- **Attach a prebuilt wheel to each GitHub release and install that URL.** Also
  git-free, and faster still (no build step at all), but adds a per-release
  asset-upload step. The tarball needs zero new release work. Revisit if build
  time on the user's machine becomes a pain.
- **Publish to PyPI** (`uv tool install "dictatem[<extra>]"`). The cleanest
  prerequisite-free end state, but adds standing release discipline (name claim,
  publish workflow, version hygiene) we are deferring until the product is solid
  across Windows / macOS / Windows-ARM. Tracked as #72; see ADR-0011's PyPI
  option.

## Consequences

- `install.ps1` installs from the tag tarball URL, not a `git+` URL — a machine
  without git now installs cleanly. First shipped in v0.2.1.
- The PEP 508 single-requirement shape (`dictatem[<extra>] @ <url>`) is unchanged:
  the extras and the URL still travel together on one argument, and the
  `--from`-split pitfall (uv treats a split as two conflicting requirements) still
  applies.
- The macOS `install.sh` on `feat/macos-track` (DRAFT PR #63) still uses a `git+`
  URL and must adopt the same change before it ships — a clean Mac has no git and
  triggers the Command Line Tools install prompt, the same class of friction.
- Trust story unchanged: HTTPS defeats MITM, GitHub is the host, and a pinned,
  readable tag URL lets a reviewer audit the exact release and guarantees it
  cannot change under the user.
