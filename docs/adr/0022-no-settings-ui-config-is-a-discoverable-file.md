# No settings UI — config is a discoverable file

> Relates to [ADR-0010](0010-hotkey-modifiers-are-configurable.md) (configurable
> hotkey), [ADR-0011](0011-install-via-thin-uv-tool-script.md) (thin install),
> and [ADR-0019](0019-usage-guide-is-an-in-app-window-reflecting-live-config.md)
> (the read-only Usage Guide).

Both competitors ship a settings window with point-and-click shortcut binding.
Scanning them raised the question for Dictatem: do we build a config-editing
settings UI? This ADR records that we deliberately do **not**, and what we do
instead.

## Decision

Dictatem has **no settings UI and no free-form key binding**. Configuration is a
hand-edited file (`~/.dictatem/config.toml`), and the trigger vocabulary is a
**curated allow-list** — `{win/meta, alt, ctrl, shift, mouse4, mouse5, middle}` —
validated on load with fallback to the default (the mechanism ADR-0010 already
established for modifiers, extended to mouse buttons by
[ADR-0020](0020-mouse-buttons-are-trigger-inputs.md)).

To keep that file **discoverable** without building UI, two thin affordances are
added:

- A tray **"Open config file…"** item that opens `config.toml` in the OS default
  editor (reusing the `QDesktopServices.openUrl` / open-default pattern that the
  "Show Log" item already uses — no new UI, just an open).
- A **"Changing your hotkey"** section in the [Usage Guide](../../CONTEXT.md#usage-guide)
  that shows the live [Hotkey Combo](../../CONTEXT.md#hotkey-combo), names the
  file and the `[hotkey].modifiers` key, lists the vetted vocabulary
  (standalone or combined), and notes that a daemon restart applies changes.

The guiding principle is **discoverability over configurability**: opinionated,
low-collision defaults plus a config-accurate guide, not "bind anything".

## Considered options

- **Build a settings window with a hotkey-capture control.** Matches the
  competitors and is the most approachable for non-technical users. Rejected: it
  fights the thin uv-tool install (no bundled heavy UI — ADR-0011/0015), and
  broad rebinding invites the very collision problem the curated allow-list
  avoids — both competitors must publish long "reserved/unsupported shortcut"
  lists precisely because they allow free-form binding.
- **Curated config, but no in-app discoverability** (document the file only in
  the README). Leanest, but a user mid-session asking "how do I change this?" has
  no in-app answer. Rejected for the two thin affordances above.
- **Open-config item, but no Guide section** (or vice versa). The item alone
  drops the user into a TOML file with no explanation of the allowed names; the
  section alone leaves them hunting for the file path. Kept both — they are
  cheap and complementary.

## Consequences

- The audience for editing the hotkey is inherently a power user (editing TOML is
  itself technical); this is an escape hatch, not a headline, consistent with the
  curated-configurability stance.
- The tray "Open config file…" item slightly re-grows the menu that the #112–114
  rework trimmed. Accepted as a deliberate trade for genuine discoverability of
  the escape hatch; it opens a file rather than adding a control surface, so the
  no-settings-UI line still holds.
- Dictatem will never compete on "configure anything"; it competes on defaults +
  config-accurate in-app help. A future settings UI would be a reversal of this
  ADR, not an extension of it.
