# dictatem

Local GPU-powered voice dictation for Windows 11. Press a global hotkey, speak, and your words are transcribed and pasted into whatever window has focus — instantly, offline, with no cloud dependency.

## Features

- **Global hotkey** — Win+Alt activates recording from any window
- **Two recording modes** — Push-to-talk (hold) or toggle (tap to start/stop, auto-stops after silence)
- **GPU-accelerated transcription** — Faster-Whisper + CUDA for sub-realtime performance
- **Smart paste** — Saves and restores clipboard content and window focus around each paste
- **System tray** — Static brand icon, rendered theme-adaptive monochrome so it stays visible on light or dark taskbars; recording state lives on the overlay's status dot, not the tray. Menu items to preload or unload the model on demand
- **Overlay UI** — Pill that appears in the corner of the active monitor while recording, with an animated waveform proportional to mic level
- **Fully offline** — All inference runs locally; the only network calls are the one-off model download on first use
- **Trigger Words** — Say `"summarize"` (or your own custom prompt) right after a dictation paste, and dictatem rewrites the just-pasted text in place via a local Ollama model
- **TOML config** — Tune model, hotkey, audio, overlay, paste, and startup behaviour

## Requirements

- Windows 11
- Python 3.11+
- x64 CPU, ~8 GB RAM (minimum — CPU-only works using the `base` Whisper model)
- NVIDIA GPU with CUDA support — optional, recommended for larger models and sub-realtime speed
- [`uv`](https://docs.astral.sh/uv/) (fast Python package manager)
- [Ollama](https://ollama.com) — optional, only for [Trigger Words](#trigger-words); see [Ollama / Transform setup](#ollama--transform-setup)

## Installation

### Install (recommended)

Run this in PowerShell. It installs [`uv`](https://docs.astral.sh/uv/) if needed, auto-detects whether you have an NVIDIA GPU (picking the CUDA or CPU-lean dependency set accordingly), installs Dictatem **pinned to the v0.2.0 release**, and launches it to the system tray:

```powershell
irm https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.2.0/install.ps1 | iex
```

Piping a script from the internet into `iex` runs it immediately. If you'd rather read it first, open [that URL](https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.2.0/install.ps1) in your browser and run it once you're satisfied.

**Forcing CPU or GPU.** The script auto-detects an NVIDIA GPU; to override, set `DICTATEM_GPU` before running — `$env:DICTATEM_GPU='cpu'` (CPU-lean) or `$env:DICTATEM_GPU='gpu'` (CUDA). This only chooses the *dependency set*, not the runtime device. On a machine that has an NVIDIA GPU, Dictatem still transcribes on the GPU by default — so forcing `cpu` there installs the lean set but the daemon will still try CUDA and fail to load the model (the CUDA libraries aren't installed). Force `cpu` only on a genuinely GPU-less machine, or also set `device = "cpu"` in your config.

**Updating.** Re-run the one-liner with a newer version tag in the URL (e.g. `.../v0.2.1/install.ps1`); see the [latest release](https://github.com/JohnJohn4/dictatem/releases/latest) for the current tag.

The script never installs or starts Ollama and never downloads a Whisper model. The model lazy-downloads on first dictation, so your **first dictation after launch** (or after the idle-unload timer frees VRAM) pauses a few seconds while the model loads — subsequent dictations are immediate. [Trigger Words](#trigger-words) stay off until you set Ollama up yourself ([Ollama / Transform setup](#ollama--transform-setup)).

### Developer install (from a clone)

For hacking on Dictatem, install from a checkout instead of the pinned release:

```powershell
git clone https://github.com/JohnJohn4/dictatem
cd dictatem
```

**CPU-only (no NVIDIA GPU)** — installs the CPU-lean set of dependencies (~200 MB, no CUDA download):

```powershell
uv sync --extra runtime
```

**NVIDIA GPU users** — adds the ~2 GB CUDA libraries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) for GPU-accelerated transcription:

```powershell
uv sync --extra runtime-gpu
```

If you have an NVIDIA GPU and want the fastest transcription, use `runtime-gpu`. If you are on a CPU-only machine or want a lighter install, use `runtime`.

### Uninstalling

Dictatem owns its start-at-login entry, so removing it cleanly is a two-step process — a bare `uv tool uninstall` would orphan that entry. **Quit Dictatem from the tray first** (right-click the tray icon → Quit), then:

```powershell
dictatem --uninstall        # step 1: removes the autostart entry (a dialog confirms and shows step 2)
uv tool uninstall dictatem  # step 2: removes the tool (dismiss the step 1 dialog first)
```

Quitting first matters: while the daemon is running its files are in use, so `uv tool uninstall` can otherwise fail with `Access is denied`. `dictatem --uninstall` runs windowless, so it confirms step 1 in a pop-up dialog rather than the terminal. Your config under `~/.dictatem` is left untouched. (A future release will stop the daemon automatically so this is just two lines — issue #69.)

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

All lines should print without errors. For the CUDA device count:

- **CPU-only install** (`runtime`): `CUDA devices: 0` is expected and fine — transcription runs on CPU.
- **GPU install** (`runtime-gpu`): `CUDA devices: 1` (or more) means GPU acceleration is active.

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

If you installed with `uv tool install` (see [Installation](#installation)), launch the daemon with the `dictatem` command — it runs windowless, with no console pop:

```powershell
dictatem
```

From a development checkout (`uv sync`), the module form also works:

```powershell
uv run python -m dictatem
```

The daemon starts in the system tray — look for the dictatem icon in the bottom-right of the taskbar. If the icon appears, it's running.

| Action | Hotkey |
|---|---|
| Push-to-talk | Hold Win+Alt (default; see `[hotkey].modifiers`) |
| Toggle record | Tap Win+Alt (default; see `[hotkey].modifiers`) |
| Stop toggle recording | Tap Win+Alt again |
| Cancel recording | Press Esc |

Transcribed text is pasted automatically into the focused window.

### Tray menu

Right-click the tray icon for: Start/Stop Recording, **Preload Model** (load Whisper into GPU memory ahead of time so the first dictation is fast), **Unload Model** (free the ~3 GB of GPU memory), Show Log, Restart, Quit. The model also auto-unloads after the configured idle period.

## Configuration

On first launch, a default config is written to `~/.dictatem/config.toml`. Edit it to customise behaviour:

```toml
[hotkey]
modifiers = ["win", "alt"]      # Modifier set for the combo; supported: win, alt, ctrl, shift
tap_threshold_ms = 200          # Below this = toggle tap; above = push-to-talk hold

[model]
name = "large-v3-turbo"
compute_type = "float16"
device = "cuda"                 # cuda or cpu; auto-resolved on first run by Hardware Tier
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

Trigger Words are enabled by default in config (`[transform].enabled = true`), but they only fire once all three steps are done. Until then, firing a trigger leaves your document untouched and surfaces a message telling you what's wrong:

| What's wrong | Message |
|---|---|
| Ollama unreachable at `base_url` (not running, not installed, or wrong URL) | Names `base_url`; says to make sure Ollama is running and points to this setup section |
| Server running but model not pulled | Run `ollama pull <model>` |

dictatem diagnoses this from the network response, not from a local `ollama` binary — so a server running in WSL, a container, or on another host (reachable via `[transform].base_url`) is handled correctly.

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
├── tray/                # Qt system tray icon and menu
└── assets/              # Brand art + generated application icon set (.ico/.icns/.png)
```

### Regenerating the application icon

The full-colour waveform brand is the application/window icon. The master art
lives at `src/dictatem/assets/icon.png` (opaque, white background baked in). To
regenerate the committed cross-platform icon set (multi-resolution `.ico`,
`.icns`, and the PNG sizes) with the white background keyed out to transparency:

```powershell
uv run python scripts/gen_icons.py
```

## License

MIT
