## v0.8.4: fixes and a friendlier README

### Fixed
- **Mac: a stuck ⌘ or ⌥ no longer starts a dictation.** If macOS missed a key
  release (Secure Keyboard Entry in Terminal, or locking the screen), a later
  lone ⌥ or ⌘ press could start a dictation. Dictatem now checks which keys are
  really held down (the Mac version of the v0.8.2 Windows fix).
- **Mac: updating keeps the Apple GPU engine.** Updating used to reinstall the
  slower CPU engine on Macs using the Apple GPU engine. It's now kept, and
  `DICTATEM_APPLE_GPU=0` still turns it off.
- **Config-problem notifications fit on screen.** A bad setting in
  `config.toml` used to give a notification cut off mid-sentence. It's now a
  short summary; the full detail is in `daemon.log`.

### Changed
- **The README puts install first,** with pictures of the dictation pill in each
  state and per-platform notes on choosing a microphone.
- **Dictatem — free from Matavex.** A small credit line in the tray's version
  line, the Usage Guide and the README.

### Updating
Use **Check for updates…** in the tray.
