# The tray is hotkey-first, drawn as a native Windows menu, and Dictatem has a Start-menu entry

> Refines [ADR-0006](0006-tray-icon-is-static-brand-not-state.md) (the
> [Tray Icon](../../CONTEXT.md#tray-icon) stays static brand) and
> [ADR-0025](0025-cold-start-load-on-arm-fetch-on-first-run.md) (load on arm).
> Shipped in v0.8.0 (#296), v0.8.1 (#301) and v0.8.3 (#305).

Owner QA on a managed work laptop (2026-11-02 to 2026-11-04) surfaced four
problems with the tray:

- **Start/Stop recording in the tray defeated itself.** Clicking the tray
  takes focus from the window the dictation should paste into.
- **Preload model was redundant.** The model loads when a dictation is armed
  (ADR-0025), and `[startup] preload_model` covers "always warm".
- **The Qt menu didn't behave like a Windows tray menu.** Left-click did
  nothing. With the Usage Guide open, an outside click didn't dismiss the
  menu (it stayed until the guide closed). The hidden-icons (`^`) flyout
  closed as soon as the mouse moved onto the menu. A Qt popup is just a
  window to the shell, which doesn't know a notification-area menu is open.
- **Quit was a dead end.** There was no discoverable way to start Dictatem
  again; only Win+R → `dictatem` or signing in again.

## Decision

1. **Hotkey-first tray.** The menu has no **Preload model** item. **Start /
   Stop recording** are shown only when no global hotkey is live (no hook
   adapter, or macOS Input Monitoring denied), because then they are the only
   way to record. **Unload model** stays, for freeing GPU memory before other
   AI work.
2. **A native Windows menu.** On Windows the menu is shown with
   `TrackPopupMenuEx` on left- *or* right-click: `SetForegroundWindow` on the
   owner first, `TPM_RETURNCMD`, then `WM_NULL`. This is the documented
   notification-area pattern. The Qt `QAction`s remain the single source of
   truth for labels, visibility, enablement, checks and the Microphone submenu.
   A pure planner (`dictatem.tray.native_menu`) snapshots them into a tidy,
   numbered plan, and the chosen `QAction` is triggered. macOS keeps Qt's
   status-item menu, which is already native there.
3. **A Start-menu entry.** `install.ps1` writes a per-user
   `Start Menu\Programs\Dictatem.lnk` (no admin) to the windowless
   `dictatem.exe` launcher, with the app icon. It is rewritten on every
   install/update (so **Check for updates** adds it to existing installs) and
   is best-effort. `dictatem --uninstall` removes it.

## Consequences

- The menu behaves like every other tray app: the flyout stays open, outside
  clicks dismiss it, and the arrow keys and Esc work. While it's open, the OS
  menu loop keeps dispatching messages, so Qt timers and the hotkey keep
  working (owner-verified).
- The native menu uses Windows' light menu theme regardless of app theme
  (unchanged in practice: the Qt menu was light too).
- Users who Quit can search "Dictatem" in Start. The README documents pinning
  the icon next to the clock.
