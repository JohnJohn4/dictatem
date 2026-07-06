# Developing dictatem

Everything you need to hack on Dictatem from a clone. For installing the released
app, see the [README](../README.md).

## Install from a clone

```powershell
git clone https://github.com/JohnJohn4/dictatem
cd dictatem
```

Pick the dependency set that matches your hardware:

```powershell
uv sync --extra runtime       # CPU-lean (~200 MB, no CUDA) — any machine
uv sync --extra runtime-gpu   # adds the ~2 GB CUDA libraries for GPU transcription
```

Use `runtime-gpu` on an NVIDIA machine for the fastest transcription; use
`runtime` on a CPU-only machine or when you want a lighter install.

Run the daemon from the checkout:

```powershell
uv run python -m dictatem
```

## Verify the setup

Confirm every dependency is wired up correctly:

```powershell
uv run python -c "
import numpy; print('numpy:', numpy.__version__)
import faster_whisper; print('faster-whisper:', faster_whisper.__version__)
import sounddevice as sd; print('sounddevice:', len(sd.query_devices()), 'devices')
from PySide6.QtWidgets import QApplication; print('PySide6: ok')
import win32clipboard; print('pywin32: ok')
import ctranslate2; print('CUDA devices:', ctranslate2.get_cuda_device_count())
"
```

All lines should print without errors. For the CUDA device count:

- **CPU-only install** (`runtime`): `CUDA devices: 0` is expected — transcription runs on CPU.
- **GPU install** (`runtime-gpu`): `CUDA devices: 1` (or more) means GPU acceleration is active.

### End-to-end test (mic + transcription)

Records 5 seconds of audio and transcribes it — speak clearly while it runs:

```powershell
uv run python scripts/bootstrap.py
```

Expected output ends with `Transcription: <your words here>`. If you see
`(No speech detected)`, check your default microphone in the OS sound settings.

## Dev workflow

```powershell
uv sync --group dev          # install dev dependencies

uv run pytest tests/         # run tests
uv run ruff check src/       # lint
uv run pyright src/          # type-check
```

## Architecture

The codebase is structured around three principles:

- **Protocol-driven adapters** — every OS-dependent operation (clipboard,
  keyboard, audio, transcription) is a Protocol in `src/dictatem/interfaces.py`.
  The daemon accepts these adapters at construction time; tests inject fakes from
  `tests/fakes/`.
- **Pure-logic state machines** — recording mode, overlay animation, and tray
  icon state are each modelled as explicit state machines with injected clocks.
  No sleeps in tests.
- **Lazy lifecycle management** — the Whisper model loads when a dictation is
  *armed* (so the load overlaps speech, [ADR-0025](adr/0025-cold-start-load-on-arm-fetch-on-first-run.md)),
  is fetched to disk once on first run, and auto-unloads after idle. GPU OOM is
  caught, the cache cleared, and the transcription retried once before surfacing
  an error.

```
src/dictatem/
├── __main__.py          # Entry point
├── daemon.py            # DaemonCore: event dispatcher
├── state.py             # Recording state machine
├── config.py            # TOML config loading
├── interfaces.py        # Protocol definitions
├── audio/               # Buffer, silence detection, sounddevice + native mac capture
├── hotkey/              # Keyboard/mouse hooks, tap/hold classifier
├── transcribe/          # Faster-Whisper adapter, model lifecycle
├── transform/           # Trigger Words: detector, Ollama backend, prompt-file loader
├── default_prompts/     # Bundled prompt files copied to ~/.dictatem/prompts/ on first run
├── paste/               # Clipboard save/restore, keystroke simulation
├── overlay/             # Qt animated pill widget
├── tray/                # Qt system tray icon, menu, and Usage Guide
└── assets/              # Brand art + generated application icon set (.ico/.icns/.png)
```

The domain vocabulary lives in [`CONTEXT.md`](../CONTEXT.md); the decisions
behind the design live in [`docs/adr/`](adr/).

### Regenerating the application icon

The full-colour waveform brand is the application/window icon. The master art
lives at `src/dictatem/assets/icon.png` (opaque, white background baked in). To
regenerate the committed cross-platform icon set (multi-resolution `.ico`,
`.icns`, and the PNG sizes) with the white background keyed out to transparency:

```powershell
uv run python scripts/gen_icons.py
```
