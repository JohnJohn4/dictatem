## Launch release

The first release for the public. It brings a refreshed look, a lot of reliability work, smarter Trigger Words, and language settings. Windows is fully tested; macOS is in beta.

### New look
- **Usage Guide** redesigned: your hotkey drawn as keycaps, a legend for the pill's colours, and light/dark themes that follow Windows.
- **Recording pill** is now a proper capsule with smoother bars. A moving wave shows while it's working, so it never looks frozen.
- **Tray menu** uses the native Windows 11 style, with grouped items and sentence-case labels.
- Notifications now show as **Dictatem** with its icon, not "Python".

### Reliability
- **Pastes land reliably with Win+Alt.** Fixed a race where a quick tap-to-stop could leave the app's menu bar focused and swallow the paste (#177). Dictatem also waits for you to let go of the hotkey before pasting.
- **Your clipboard is kept:** screenshots, copied files and rich text survive a dictation (previously only text did). Dictations still never appear in Win+V history.
- **Esc during a slow transcription** can no longer let the cancelled result paste later.
- **Config mistakes are reported, not destructive:** a bad value or broken `config.toml` shows one notification. Dictatem uses the default and never overwrites your file.
- **Pressing the hotkey while it's busy** shows "Still working — Esc cancels" instead of seeming to do nothing.
- A **"Saved — say paste"** pill colour now shows when a dictation is held for recovery, so it no longer looks like an error.
- **Tray Restart** works, so config edits apply without quitting.
- **Clearer model-load error messages,** a safer idle unload, lighter work per tick, and keyboard-hook failures are now reported instead of silently leaving you without a hotkey.
- **Windows updater now asks first:** "Install Dictatem vX?", with *Not now* as the default.

### Trigger Words
- **Short commands are heard more reliably:** sound-alike matching catches near-misses like "haste" → paste. An unsure match flashes **say again** instead of guessing.
- **Your own words for paste:** `[trigger_words].paste_aliases = ["pasta"]`.
- **Startup warning** when two of your Trigger Words sound alike, plus guidance on choosing good ones.
- Text replaced by a Trigger Word is typed at a steady pace, so slower apps keep up.

### Language
- **English by default.** Short phrases are no longer misheard as French or Greek.
- **Pin any language** (`language = "zh"`), **auto-detect** (`language = "auto"`), or set a **preferred set** (`languages = ["en", "zh"]`). When unsure, it falls back to your last confident language rather than guessing.

### macOS (beta)
- **Smoother first run:** the installer shows progress, permission dialogs are simpler, and a missing permission is reported when you use Dictatem instead of failing silently.
- **Check for updates** works on macOS, showing the update command to copy.
- **Better accuracy on Apple Silicon:** it now uses the `small` speech model. An **Apple GPU (MLX)** engine is available as an opt-in beta: install with `… | DICTATEM_APPLE_GPU=1 sh`.

### Privacy
- Dictated text is no longer written to the log. A warning appears if the Trigger Word server address is set to something other than this computer. Control characters are stripped from pasted text.

### Known issues
- Trigger Words that replace text can come out garbled in **Windows 11 Notepad** (#278). Regular dictation works there, and Trigger Words work in other editors and browsers.
- macOS permission prompts still say `python3.12` until signed builds ship (#91).

**Updating:** on Windows, use tray → **Check for updates…**. On macOS, use **Check for Updates…** in the menu-bar menu and paste the command it shows, or re-run the README one-liner, now pinned to `v0.7.0`.
