# Mouse buttons are trigger inputs in the Hotkey Combo

> Extends [ADR-0010](0010-hotkey-modifiers-are-configurable.md) and
> [ADR-0018](0018-cross-platform-input-and-foreground-neutral-identities.md):
> the configurable trigger vocabulary grows from keyboard modifiers to include a
> mouse button, still resolved to platform-neutral `Key` identities.

Users want to arm dictation with a mouse button — today they must map a mouse
button to a key combo in their mouse vendor's software (the
`project_mouse_button` want). Both competitors (Wispr Flow, superwhisper) accept
mouse buttons as first-class dictation triggers. This ADR brings the capability
into Dictatem without splitting the hotkey model in two.

## Decision

**A mouse button is just another neutral identity in the same combo.** The
[Hotkey Combo](../../CONTEXT.md#hotkey-combo) is generalised from "a set of
modifier keys" to "a set of **trigger inputs**" — modifier keys and/or one mouse
button. The pure `HotkeyClassifier` is unchanged in shape: it already reasons
about `Key` identities grouped into modifier groups and fires
[Tap](../../CONTEXT.md#tap)/[Hold](../../CONTEXT.md#hold) on press/release
timing. Mouse buttons add new `Key` identities (`MOUSE_4`, `MOUSE_5`,
`MOUSE_MIDDLE`) and a matching `_MODIFIER_MAP` entry, and each platform grows a
**mouse hook** (Windows `WH_MOUSE_LL`; macOS `CGEventTap` `otherMouse*`) whose
pure native-code→`Key` table sits beside the existing keyboard keymap.

**Config surface stays `[hotkey].modifiers`.** The field accepts mouse-button
names alongside modifier names — `["ctrl", "mouse4"]` or `["mouse4"]` standalone
— so existing configs are untouched and there is no migration. The field name is
a back-compat serialisation detail, like `win` (see ADR-0018); the domain term
is "trigger inputs".

**The vocabulary is a curated allow-list.** Only `{win, meta, alt, ctrl, shift,
mouse4, mouse5, middle}` are accepted; `config.py` rejects anything else and
falls back to the default, exactly as ADR-0010 already does for modifiers.
`mouse4`/`mouse5` are the two side buttons (Windows X1/X2; macOS `buttonNumber`
3/4); `middle` is the wheel click (Windows middle button; macOS `buttonNumber`
2). Left and right click are never accepted — they are primary interaction.

**A trigger button is conditionally suppressed.** Unlike modifier keys (which
always pass through, being harmless to leak), a mouse button usually has an
existing OS action (Mouse4 = browser-back). The hook **suppresses the button
event iff the press completes/sustains the configured combo**: a standalone
`["mouse4"]` press is always suppressed; in `["ctrl", "mouse4"]` the button is
suppressed only while Ctrl is held, so a bare Mouse4 still navigates back. The
matching button-up is suppressed whenever its down was, to keep the down/up pair
balanced for downstream apps. This reuses the classifier's existing per-event
`HookDecision` (`SUPPRESS`/`PASS_THROUGH`) path.

## Considered options

- **A separate trigger rail.** Keep the Hotkey Combo as keyboard-only and add a
  distinct `[hotkey].mouse_button` arming path with its own tap/hold handling.
  Rejected: two parallel arming mechanisms duplicate the tap/hold timing logic
  and the "standalone or combined" model (`Ctrl+Mouse4`) only falls out cleanly
  when the button lives in the *same* set as the modifiers.
- **Suppress the trigger button unconditionally.** Simplest rule, but a combined
  `["ctrl", "mouse4"]` config would then kill bare-Mouse4's normal function even
  with no Ctrl held — surprising collateral. Rejected for conditional suppression.
- **Never suppress (always pass through).** Simplest hook, no down/up pairing to
  track, but standalone Mouse4-as-push-to-talk would *also* fire browser-back on
  every press — unacceptable for the headline use case. Rejected.
- **Support Wispr's full Mouse6–10 range.** Those buttons are not in the standard
  OS hook message set (Windows exposes only X1/X2 via `WH_MOUSE_LL`); they need
  Raw Input or vendor drivers, which are not portable. Rejected for v1 in favour
  of the three buttons both platforms deliver natively.
- **A config-editing settings UI for bindings.** Both competitors ship one. It
  fights the thin uv-tool install (ADR-0011/0015) and the curated-allow-list
  stance; discoverability is served by the [Usage Guide](../../CONTEXT.md#usage-guide)
  reflecting the live combo instead. Rejected.

## Consequences

- The classifier stays pure and fully unit-tested, including the new mouse
  identities and the conditional-suppression decision; only the live mouse hook
  is manual-QA, consistent with how native adapters are treated (PRD #51).
- Both the Windows and (future) macOS paths are exercised by the same neutral
  classifier, so the bulk of the design is regression-tested on Windows/CI before
  any mouse-specific macOS hardware testing.
- Mouse buttons that **only report clicks, not sustained holds** (some vendor
  mice — noted by superwhisper) degrade gracefully: a click is a fast down/up, so
  the timing classifier sees a [Tap](../../CONTEXT.md#tap) and toggles. Hold /
  push-to-talk simply won't engage on such hardware; the Usage Guide should say
  so rather than imply every mouse can push-to-talk.
- Configuring a mouse button as a trigger **costs that button its normal action**
  while it is triggering. Because only non-primary buttons are allowed and
  suppression is conditional, the cost is bounded and opt-in.
- The field name `[hotkey].modifiers` now slightly under-describes its contents
  (it can hold a mouse button). Accepted as the price of zero-migration
  back-compat, mirroring the permanent `win` alias.
