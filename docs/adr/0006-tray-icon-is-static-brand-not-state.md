# Tray icon is static brand identity, not a state indicator

Earlier the system [Tray Icon](../../CONTEXT.md#tray-icon) encoded recording
state by colour (grey idle / green recording / red error), drawn as procedural
circles. We are replacing it with the static waveform brand: the Tray Icon no
longer carries state — recording state lives on the
[Status Dot](../../CONTEXT.md#status-dot) of the
[Overlay Pill](../../CONTEXT.md#overlay-pill) (red recording / amber
transcribing, outline vs filled for [Hold](../../CONTEXT.md#hold) vs
[Tap](../../CONTEXT.md#tap)). The full-colour art is reserved for the
**application icon**; the **Tray Icon** is rendered theme-adaptive monochrome
(light on dark taskbars, dark on light) so the near-black art stays visible —
Windows does not invert tray icons.

The work is split across two slices: the application icon plus cross-platform
icon generation, and the theme-adaptive monochrome tray rendering that drops the
state colours. Until the tray-rendering slice lands, the tray still draws the
legacy state glyph.

## Considered options

- **Use the full-colour waveform directly as the tray icon.** The dark,
  near-black art vanishes against a dark taskbar and carries no idle / recording
  / error state; the tray's job is at-a-glance status, not branding.
- **One icon reused everywhere.** Conflates two audiences: the application icon
  wants the crisp full-colour brand at large sizes (taskbar, alt-tab), while the
  tray wants a tiny, theme-aware glyph. Coupling them forces every tray change to
  relitigate the brand art.
- **Key the white background by exact `(255,255,255)` match.** The master art is
  anti-aliased, so edge pixels fade through near-white toward the baked-in white
  background; an exact match leaves a pale halo box. Keying by a near-white
  luminance threshold removes the fringe cleanly while the near-black bars stay
  opaque.

## Consequences

- The README feature line "Idle/recording/error status icons" no longer
  describes the tray and must point at the Status Dot.
- A dev-only generation script (Pillow, dev-dependency group only — never
  runtime) keys the white out and emits the committed cross-platform icon set
  (multi-resolution `.ico`, `.icns`, and PNG sizes); the white-keying is a pure,
  unit-tested function.
- Tray rendering reacts to OS light/dark theme changes at runtime (Qt
  `colorSchemeChanged`); the application icon does not.
