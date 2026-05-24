# Tray icon is static brand identity, not a state indicator

Earlier, the system [Tray Icon](../../CONTEXT.md#tray-icon) encoded recording
state by colour (grey idle / green recording / red error), generated as
procedurally-drawn circles. We replaced it with a single static brand glyph
that does **not** change with state. Recording state already lives on the
[Status Dot](../../CONTEXT.md#status-dot) of the [Overlay Pill](../../CONTEXT.md#overlay-pill)
(red recording / amber transcribing, outline vs filled for Hold vs Tap), so a
colour-coded tray icon was redundant for the common case and unlike how most
tray apps behave. The accepted trade-off: if the user looks at the tray while
recording (with the overlay not in view), the tray gives no state signal.

The glyph is rendered **theme-adaptive monochrome** in the tray (light on dark
taskbars, dark on light) so it stays visible — Windows does not auto-invert
tray icons, and the source art is near-black. This is a visibility adaptation
to the OS theme, not state encoding. The full-colour art is reserved for the
application icon (`.ico`/`.icns`), which appears on varied backgrounds.

## Consequences

- The README feature line "Idle/recording/error status icons" no longer
  describes the tray; it must be updated to point at the Status Dot.
- Tray rendering reacts to OS light/dark theme changes at runtime (Qt
  `colorSchemeChanged`); the app icon does not.
