# The Usage Guide auto-opens once on first run

> Builds on [ADR-0019](0019-usage-guide-is-an-in-app-window-reflecting-live-config.md):
> the in-app [Usage Guide](../../CONTEXT.md#usage-guide) now also serves as the
> onboarding surface, opening itself the first time Dictatem runs.

Both competitors (Wispr Flow, superwhisper) onboard new users with a guided
first-run flow. Dictatem already built the surface for it — a Usage Guide that
reflects live config and grows one section per feature — but it only opened when
the user happened to find the tray menu item. A new user who never opens the
tray menu never learns the Tap/Hold/Trigger-Word workflow. This ADR makes the
guide introduce itself.

## Decision

On first run, after the tray icon exists and any first-run permission flow has
settled, Dictatem **auto-opens the existing Usage Guide once** (scrolled to the
top), non-modally. It is the same guide the tray item opens — no separate intro
variant — so there is one source of truth and the onboarding content grows for
free as feature sections are appended.

"Has the user seen the guide?" is persisted as a **sentinel marker file**
(`~/.dictatem/.usage_guide_seen`), written **only after the guide is actually
shown**. The guide auto-opens iff the marker is absent. The marker is the
single gate; `config.toml` is untouched.

## Considered options

- **Gate on config-file absence** (`is_first_run = not config_path.exists()`,
  captured before `load_config` creates it). Zero new state, but it encodes
  "a config file was once absent", not "the user saw the guide". On macOS,
  granting a permission frequently **relaunches** the daemon; by the next launch
  the config exists, so onboarding is silently skipped. Rejected — the proxy is
  wrong exactly when it matters.
- **A `usage_guide_seen` flag in `config.toml`.** Survives relaunch, but flipping
  it after the guide shows means **rewriting the user's config file**, against
  the deliberate "config is never rewritten by the app" grain
  ([ADR-0009](0009-hardware-mismatch-falls-back-for-the-session.md)), and it adds
  user-facing config surface for a purely internal flag. Rejected.
- **Open immediately when the tray icon appears**, before the permission flow
  settles. Simpler control flow, but on macOS the guide competes with the
  permission dialog on the most fragile launch — risking focus theft or a
  confused grant. Rejected for "after permissions settle".
- **A tray notification instead of a window.** Least intrusive, but weaker
  discoverability and a different surface than the designed guide. Rejected.

## Consequences

- The marker is written *on show*, so the macOS permission-relaunch case is
  self-healing: a launch that defers the guide (because permissions are still
  being granted) leaves the marker absent, and the next clean launch shows it.
- Deleting `~/.dictatem/` (or a fresh reinstall) re-onboards the user. Accepted —
  arguably correct.
- The decision to persist onboarding state **outside** `config.toml` introduces
  Dictatem's first piece of app-owned state under `~/.dictatem/` that is not user
  config; future ephemeral flags have a precedent to follow.
- Onboarding content needs no separate maintenance — it is the Usage Guide, which
  is already kept current and config-accurate.
