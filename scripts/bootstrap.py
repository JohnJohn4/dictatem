"""Bootstrap proof-of-life: load model, record 5s, transcribe, print.

This script is Windows-only and requires the [runtime] optional dependencies.
It validates that the GPU, faster-whisper, and audio capture work end-to-end.

Usage (Windows only, after ``uv sync --extra runtime``):
    python scripts/bootstrap.py
"""

from __future__ import annotations

import sys


def main() -> None:
    if sys.platform != "win32":
        print("bootstrap.py is a Windows-only sanity check.")
        print("It requires a GPU, microphone, and the [runtime] extras.")
        sys.exit(1)

    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel

    sample_rate = 16_000
    duration_s = 5

    print("Loading large-v3-turbo on GPU...")
    model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
    print("Model loaded.")

    print(f"Recording {duration_s}s of audio — speak now...")
    audio = sd.rec(
        int(sample_rate * duration_s),
        samplerate=sample_rate,
        channels=1,
        dtype=np.float32,
    )
    sd.wait()
    audio = audio.squeeze()
    print("Recording complete.")

    print("Transcribing...")
    segments, _info = model.transcribe(audio, vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments)

    if text.strip():
        print(f"Transcription: {text}")
    else:
        print("(No speech detected)")


if __name__ == "__main__":
    main()
