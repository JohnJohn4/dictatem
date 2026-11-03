## v0.8.2: no more surprise dictations from Alt shortcuts

### Fixed
- **Alt+Enter in Excel (or any Alt shortcut) no longer starts a dictation by
  surprise.** After locking the laptop with **Win+L** (or releasing a key while
  an admin window had focus), Dictatem could miss the Win key being let go and
  keep thinking it was held. The next Alt press then looked like the Win+Alt
  hotkey. Dictatem now checks with Windows that both keys are really held
  before starting.

### Updating
Use **Check for updates…** in the tray.
