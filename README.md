# dictatem

Local GPU-powered voice dictation for Windows 11. Press a global hotkey, speak, and your words are transcribed and pasted into whatever window has focus — instantly, offline, with no cloud dependency.

## Features

- **Global hotkey** — Win+Alt activates recording from any window
- **Two recording modes** — Push-to-talk (hold) or toggle (tap to start/stop, auto-stops after silence)
- **GPU-accelerated transcription** — Faster-Whisper + CUDA for sub-realtime performance
- **Smart paste** — Saves and restores clipboard content and window focus around each paste
- **System tray** — Idle/recording/error status icons; menu items to preload or unload the model on demand
- **Overlay UI** — Pill that appears in the corner of the active monitor while recording, with an animated waveform proportional to mic level
- **Fully offline** — All inference runs locally; the only network calls are the one-off model download on first use
- **Trigger Words** — Say `"summarize"` (or your own custom prompt) right after a dictation paste, and dictatem rewrites the just-pasted text in place via a local Ollama model
- **TOML config** — Tune model, hotkey, audio, overlay, paste, and startup behaviour

## Requirements

- Windows 11
- Python 3.11+
- NVIDIA GPU with CUDA support
- [`uv`](https://docs.astral.sh/uv/) (fast Python package manager)
- [Ollama](https://ollama.com) — optional, only for [Trigger Words](#trigger-words); see [Ollama / Transform setup](#ollama--transform-setup)

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

```powershell
uv run python -m dictatem
```

The daemon starts in the system tray — look for the dictatem icon in the bottom-right of the taskbar. If the icon appears, it's running.

| Action | Hotkey |
|---|---|
| Push-to-talk | Hold Win+Alt |
| Toggle record | Tap Win+Alt |
| Stop toggle recording | Tap Win+Alt again |
| Cancel recording | Press Esc |

Transcribed text is pasted automatically into the focused window.

### Tray menu

Right-click the tray icon for: Start/Stop Recording, **Preload Model** (load Whisper into GPU memory ahead of time so the first dictation is fast), **Unload Model** (free the ~3 GB of GPU memory), Show Log, Restart, Quit. The model also auto-unloads after the configured idle period.

## Configuration

On first launch, a default config is written to `~/.dictatem/config.toml`. Edit it to customise behaviour:

```toml
[hotkey]
modifiers = ["win", "alt"]
tap_threshold_ms = 200          # Below this = toggle tap; above = push-to-talk hold

[model]
name = "large-v3-turbo"
compute_type = "float16"
vad_filter = true
idle_unload_minutes = 30        # Free GPU VRAM when idle for this long
min_transcription_chars = 3     # Below this, treat the result as empty

[paste]
trailing_space = true
strip_newlines = true
clipboard_retry_attempts = 5
clipboard_retry_delay_ms = 10

[audio]
sample_rate = 16000

[behaviour]
silence_timeout_s = 60          # Auto-stop toggle recording after this much silence
max_recording_seconds = 300     # Hard cap on recording length regardless of audio activity

[overlay]
position = "bottom-right"
fade_in_ms = 100
fade_out_ms = 400

[startup]
autostart = true
preload_model = false           # Load the model on daemon startup vs lazily on first use

[logging]
level = "info"

[transform]
enabled = true                  # Master switch for Trigger Words (local-LLM rewrites)
model_name = "gemma4:e4b"       # Ollama model tag; must match `ollama list`
base_url = "http://localhost:11434"
timeout_s = 30                  # Per-request Ollama timeout
last_paste_ttl_s = 300          # How long a Last Paste stays eligible for a Trigger Fire
```

## Ollama / Transform setup

[Trigger Words](#trigger-words) run a local [Ollama](https://ollama.com) model. **This feature is off until you set Ollama up yourself** — dictatem talks to a running Ollama but never installs it, starts it, or pulls models on your behalf (see [ADR-0008](docs/adr/0008-dictatem-does-not-manage-ollama-lifecycle.md)). The manual steps:

1. **Install Ollama** — download it from [ollama.com](https://ollama.com) and run the installer.
2. **Start the Ollama server** — `ollama serve` (the desktop app starts it for you). It listens on `http://localhost:11434` by default, matching `[transform].base_url`.
3. **Pull the configured model** — `ollama pull gemma4:e4b` (or whatever you set in `[transform].model_name`). Confirm it's present with `ollama list`.

Trigger Words are enabled by default in config (`[transform].enabled = true`), but they only fire once all three steps are done. Until then, firing a trigger leaves your document untouched and surfaces a message telling you which step is missing:

| What's wrong | Message |
|---|---|
| Ollama not installed (no `ollama` on PATH) | Points you to this setup section |
| Ollama installed but server not running | Start Ollama, then try again |
| Server running but model not pulled | Run `ollama pull <model>` |

## Trigger Words

A Trigger Word is a single utterance that rewrites the previously-pasted dictation in place instead of being pasted as-is. After any normal dictation paste, say one trigger (e.g. `"summarize"`) within the configured TTL — dictatem deletes the just-pasted text and replaces it with the output of a local [Ollama](https://ollama.com) model run with that trigger's prompt.

Requires Ollama running locally with the configured model pulled — see [Ollama / Transform setup](#ollama--transform-setup) above (`ollama pull gemma4:e4b` by default). If Ollama is offline or the call fails, the document is left untouched and the overlay flashes a message telling you which step is missing.

### Custom triggers

Prompts live as markdown files in `~/.dictatem/prompts/`, created on first daemon start. Each file declares its aliases in YAML-style frontmatter; the body is the system prompt sent to Ollama:

```markdown
---
aliases: [expand, expound]
---
You expand terse notes into full prose. Preserve every fact. Output only the expanded text.
```

Drop a new `.md` file into the folder and restart the daemon to register the new trigger. Edits to existing files survive upgrades — the bootstrap only copies in files that don't already exist. Aliases are matched case-insensitively with trailing punctuation stripped, so `"Expand."` fires the same trigger as `"expand"`.

Safety rails: a Trigger Fire only runs if (a) the focused window is still the same one you pasted into and (b) the paste is younger than `last_paste_ttl_s`. Switching windows or waiting too long discards the trigger silently.

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
├── transform/           # Trigger Words: detector, Ollama backend, prompt-file loader
├── default_prompts/     # Bundled prompt files copied to ~/.dictatem/prompts/ on first run
├── paste/               # Clipboard save/restore, keystroke simulation
├── overlay/             # Qt animated pill widget
└── tray/                # Qt system tray icon and menu
```

## License

MIT
