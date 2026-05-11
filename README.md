# dictatem

Local GPU-powered voice dictation for Windows 11. Press a global hotkey, speak, and your words are transcribed and pasted into whatever window has focus — instantly, offline, with no cloud dependency.

> **Status:** Core pipeline (audio capture, GPU transcription, paste) is implemented and tested. The full daemon wiring (`_start_windows_daemon`) is not yet complete — `python -m dictatem` exits immediately. Use the [bootstrap script](#verify-the-setup) to confirm your environment works end-to-end.

## Features

- **Global hotkey** — Ctrl+Win activates recording from any window
- **Two recording modes** — Push-to-talk (hold) or toggle (tap to start/stop, auto-stops after silence)
- **GPU-accelerated transcription** — Faster-Whisper + CUDA for sub-realtime performance
- **Smart paste** — Saves and restores clipboard content and window focus around each paste
- **System tray** — Idle/recording/error status icons with context menu
- **Overlay UI** — Animated pill with waveform visualization while recording
- **Fully offline** — No network calls; all inference runs locally
- **TOML config** — Tune model, hotkey, audio, overlay, and paste behaviour

## Requirements

- Windows 11
- Python 3.11+
- NVIDIA GPU with CUDA support
- [`uv`](https://docs.astral.sh/uv/) (fast Python package manager)

## Installation

```powershell
git clone https://github.com/JohnJohn4/dictatem
cd dictatem
uv sync --extra runtime
```

## Verify the setup

Before running, confirm all dependencies are wired up correctly:

```powershell
uv run python -c "
import numpy; print('numpy:', numpy.__version__)

import faster_whisper; print('faster-whisper:', faster_whisper.__version__)

import sounddevice as sd
devices = sd.query_devices()
print('sounddevice:', len(devices), 'audio devices found')

from PySide6.QtWidgets import QApplication; print('PySide6: ok')

import win32clipboard; print('pywin32: ok')

import ctranslate2
print('CUDA devices:', ctranslate2.get_cuda_device_count())
"
```

All lines should print without errors, and CUDA devices should be `>= 1`.

### End-to-end test (GPU + mic + transcription)

This records 5 seconds of audio and transcribes it:

```powershell
uv run python scripts/bootstrap.py
```

Speak clearly while it records. Expected output:

```
Loading large-v3-turbo on GPU...
Model loaded.
Recording 5s of audio — speak now...
Recording complete.
Transcribing...
Transcription: <your words here>
```

If you see `(No speech detected)`, check your default microphone in Windows sound settings.

## Running

> The full daemon (`python -m dictatem`) is not yet implemented — see status note above. Once complete, run:

```powershell
uv run python -m dictatem
```

The daemon starts in the system tray. Look for the dictatem icon in the bottom-right of the taskbar.

| Action | Hotkey |
|---|---|
| Push-to-talk | Hold Ctrl+Win |
| Toggle record | Tap Ctrl+Win |
| Stop toggle recording | Tap Ctrl+Win again |

Transcribed text is pasted automatically into the focused window.

## Configuration

On first launch, a default config is written to `~/.dictatem/config.toml`. Edit it to customise behaviour:

```toml
[hotkey]
modifiers = ["ctrl", "win"]
tap_threshold_ms = 200          # Below this = toggle tap; above = push-to-talk hold

[model]
name = "large-v3-turbo"
compute_type = "float16"
vad_filter = true
unload_after_idle_minutes = 30  # Free GPU VRAM when idle

[paste]
trailing_space = true
strip_trailing_newlines = true
clipboard_retries = 5

[audio]
sample_rate = 16000

[behaviour]
silence_timeout_s = 60          # Auto-stop toggle recording after this much silence

[overlay]
position = "bottom-right"
```

## Development

```powershell
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest tests/

# Lint and type-check
uv run ruff check src/
uv run pyright src/
```

## Architecture

The codebase is structured around three principles:

**Protocol-driven adapters** — Every OS-dependent operation (clipboard, keyboard, audio, transcription) is defined as a Protocol in `src/dictatem/interfaces.py`. The daemon accepts these adapters at construction time; tests inject fakes from `tests/fakes/`.

**Pure-logic state machines** — Recording mode, overlay animation, and tray icon state are each modelled as explicit state machines with injected clocks. No sleeps in tests.

**Lazy lifecycle management** — The Whisper model loads on first transcription and auto-unloads after idle. GPU OOM is caught, cache is cleared, and the transcription is retried once before surfacing an error to the user.

```
src/dictatem/
├── __main__.py          # Entry point
├── daemon.py            # DaemonCore: event dispatcher
├── state.py             # Recording state machine
├── config.py            # TOML config loading
├── interfaces.py        # Protocol definitions
├── audio/               # Buffer, silence detection, sounddevice adapter
├── hotkey/              # Windows keyboard hook, tap/hold classifier
├── transcribe/          # Faster-Whisper adapter, model lifecycle
├── paste/               # Clipboard save/restore, keystroke simulation
├── overlay/             # Qt animated pill widget
└── tray/                # Qt system tray icon and menu
```

## License

MIT
