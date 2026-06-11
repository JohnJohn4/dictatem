# The Usage Guide is a single in-app window reflecting live config

The tray "How to use Dictatem…" item opens the
[Usage Guide](../../CONTEXT.md#usage-guide) — a read-only, offline, in-app
window (a `QTextBrowser` hosting generated HTML) — rather than linking out to
the README/docs on the web. We chose this because the guide can reflect the
user's **live configuration** — their actual
[Hotkey Combo](../../CONTEXT.md#hotkey-combo) and configured
[Trigger Words](../../CONTEXT.md#trigger-word) — which a static page cannot, and
because a single guide that grows by appending one section per feature keeps the
tray menu lean instead of accreting a help item per feature.

## Considered options

- **Link the tray item to the README/docs on the web** (reusing the
  `QDesktopServices.openUrl` pattern that `Show Log` uses). Richer — it can carry
  README screenshots — and a single source of truth, but it can only ever show
  the *default* `Win+Alt` chord and generic examples, is wrong for anyone who
  rebound their modifiers (ADR-0010) or named their own trigger words, requires
  internet, and bounces the user into a browser.
- **A help item per feature.** Contextual, but proliferates tray items as
  features land — directly against the goal of a leaner menu that prompted this
  rework.
- **A one-shot message box.** Fine for the hotkey alone, but cannot scale to the
  multi-section guide (dictating, trigger words, first-use) without a redesign.

## Consequences

- The guide and the README will carry overlapping usage prose; we accept minor
  drift for the sake of offline, config-accurate, in-app help.
- README screenshots live only in the README, not the in-app guide (the guide is
  text + the live config it reflects).
- The pure HTML/text builders stay unit-tested and reuse `format_hotkey()`; only
  the window hosting stays in the manual-QA Qt adapter (PRD #51 convention).
