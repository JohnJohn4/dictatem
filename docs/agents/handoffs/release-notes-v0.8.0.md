## v0.8.0: faster on work laptops, fully offline, plug-and-play microphones

This release is about speed and robustness, especially on managed work laptops,
where security software scans every new file. Measured on such a laptop (and
checked on an ordinary home PC for no regressions).

### Faster
- **First dictation after installing: ~2 minutes → ~27 seconds** on a work
  laptop. The installer now prepares the speech engine before Dictatem first
  starts ("Preparing the speech engine… please wait"). On a normal PC this
  takes a few seconds.
- **First dictation after a break: ~13 seconds or more → ~1.5 seconds** on a
  work laptop. Where security software is slow to re-check files, Dictatem keeps
  the speech engine loaded (not the model, and no GPU memory) so a break
  doesn't cost you a long wait.
- **Tray appears sooner** on a fresh install (37 s → ~16 s on a work laptop):
  the GPU check no longer loads the whole engine.
- **The pill appears sooner** when you press the hotkey: the audio system is
  ready before your first dictation.

### Works offline
- After the one-time model download at install, **dictation needs no internet
  connection**. Loading the model no longer checks Hugging Face each time.

### Microphones
- **Plug in a headset and it's used from your next dictation.** No restart
  needed.
- New **Microphone** menu in the tray (Windows): pick *System default* or any
  connected microphone. Your choice is remembered.
- If your chosen microphone is unplugged, Dictatem uses the system default and
  **switches back automatically** when it's plugged in again.

### Simpler tray
- **Start/Stop recording** and **Preload model** are gone. The hotkey is the
  way to dictate (clicking the tray moved focus away from where your text
  should go). They come back automatically if no hotkey is available.
- **Unload model** stays, for freeing GPU memory before other AI work.

### Under the hood
- About **440 MB smaller** install (only the Qt parts Dictatem uses).
- Hotkey presses, startup phases and model-load steps are logged (never your
  words), so problems are easier to diagnose.
- The installer stops with a clear error if installing fails, instead of
  carrying on, and repairs an environment left broken by an interrupted
  install.
- New `[startup]` settings: `prewarm_engine = true` and
  `resident_engine = "auto"` (`"on"` / `"off"` to force).

### Updating
Use **Check for updates…** in the tray. The first update from v0.7.0 switches
Dictatem's Qt package once, and prepares the speech engine before restarting.
On a work laptop that can take a few minutes.
