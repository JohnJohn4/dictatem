# Application icon is the static full-colour brand; tray rendering is separate

The full-colour waveform art (`src/dictatem/assets/icon.png`) is reserved for
the **application icon** — the taskbar button, alt-tab thumbnail, and window
chrome. It is wired via `QApplication.setWindowIcon` (and the parent widget's
window icon) from the multi-resolution `app.ico` so Windows picks the crispest
embedded resolution. The master art ships inside the package and is loaded at
runtime through `importlib.resources` (`dictatem.assets.asset_path`), never the
repo-root file.

The system **Tray Icon** is a *separate* concern. It stays the small
state-driven glyph (idle / recording / error) and is not the full-colour brand.
Theme-adaptive monochrome tray rendering — tinting the brand to match a light or
dark taskbar — is owned by a later slice
([#38](https://github.com/JohnJohn4/dictatem/issues/38)) and is deliberately out
of scope here.

## Considered Options

- **Use the full-colour waveform directly as the tray icon.** The art is a
  dark, near-black waveform on white. Keyed to transparency it renders as dark
  bars, which vanish against a dark Windows taskbar and carries no idle /
  recording / error state. The tray's job is at-a-glance status, not branding.
- **Generate one icon and reuse it everywhere.** Conflates two audiences: the
  application icon wants the crisp full-colour brand at large sizes (taskbar,
  alt-tab), while the tray wants a tiny, theme-aware, state-carrying glyph.
  Coupling them forces every tray-rendering change to relitigate the brand art.
- **Key the white background by exact `(255,255,255)` match.** The master art is
  anti-aliased: edge pixels fade through near-white values toward the baked-in
  white background. An exact match leaves those edge pixels opaque, producing a
  pale halo box around the artwork.

Keying by a near-white luminance threshold (every RGB channel `>= 240`) was
chosen so the anti-aliased fringe is removed cleanly while the near-black bars
(`~44,43,48`) stay fully opaque. The application icon and the tray icon are kept
as independent outputs so each can evolve without disturbing the other.

## Consequences

- The master art is full-colour with a baked-in white background. The dev-only
  `scripts/gen_icons.py` (Pillow, `dev` dependency group only — never runtime)
  keys the white out and writes the committed cross-platform set into
  `src/dictatem/assets/`: a multi-resolution `app.ico` (16, 24, 32, 48, 64, 128,
  256), an `app.icns` (16–1024 incl. @2x), and PNGs (16, 32, 48, 128, 256, 512,
  1024). Regenerate with `uv run python scripts/gen_icons.py`.
- The white-keying is a pure function (`key_white_to_transparent`) so it is unit
  tested directly: a white pixel becomes transparent, a near-white edge pixel
  becomes transparent, and a near-black bar pixel stays opaque.
- `QtTrayIcon.__init__` sets the application/window icon from `app.ico` but does
  **not** change how the state-driven tray glyph is drawn. Tray theme-tinting
  remains untouched for #38.
- Hatch packages the assets into the wheel automatically because they live under
  the `src/dictatem` package directory; no force-include is needed.
